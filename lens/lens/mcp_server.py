"""
mcp_server.py — Lens MCP Server
CCA Domain 4: Tool design & MCP integration

6 workspace tools exposed as MCP primitives.
Agents call these instead of accessing the database directly.

Tools (actions with side effects):
  web_search      — search the public web
  read_document   — fetch and extract document content
  save_finding    — persist a finding to the workspace
  write_report    — save the final report

Resources (read-only, no side effects):
  get_project     — read project state
  search_findings — search existing findings

Every tool returns structured errors with errorCategory
and isRetryable so agents can reason about failures.
"""

import json
import os
from uuid import uuid4

import httpx
import structlog
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import (
    CallToolResult,
    ListToolsResult,
    TextContent,
    Tool,
)

from lens.session_store import SessionStore

log = structlog.get_logger(__name__)

# Initialise server and store
app = Server("lens-workspace")
store = SessionStore(db_path=os.getenv("LENS_DB_PATH", "./data/lens.db"))


def error_response(
    category: str,
    message: str,
    is_retryable: bool,
    retry_after_seconds: int | None = None,
) -> CallToolResult:
    """
    Structured error response — agents can reason about these.
    Raw exception strings give agents nothing to act on.
    errorCategory tells the agent what went wrong.
    isRetryable tells the agent whether to retry or escalate.
    """
    error = {
        "error": True,
        "errorCategory": category,
        "isRetryable": is_retryable,
        "message": message,
    }
    if retry_after_seconds:
        error["retryAfterSeconds"] = retry_after_seconds

    return CallToolResult(
        content=[TextContent(type="text", text=json.dumps(error))]
    )


# ─── Tool definitions ─────────────────────────────────────────────

@app.list_tools()
async def list_tools() -> ListToolsResult:
    return ListToolsResult(tools=[

        Tool(
            name="web_search",
            description="""Search the public web for recent information on a topic.

Use this when you need current information not in training data,
or when the user asks about recent events, news, or live data.

Returns: list of up to 10 results, each with:
- title: page title
- url: source URL
- snippet: 2-3 sentence summary
- published_date: ISO date string or null

Does NOT: search internal databases, fetch full page content.
Use read_document to get full content from a URL.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query — 3-8 words works best",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Number of results to return (1-10, default 5)",
                        "default": 5,
                    },
                },
                "required": ["query"],
            },
        ),

        Tool(
            name="read_document",
            description="""Fetch and extract content from a URL or uploaded document.

Use this after web_search to get full content from promising URLs.
Returns structured content with title, summary, and extracted claims.

Caches by content — same document is never fetched twice.

Does NOT: search for new URLs. Use web_search to discover URLs first.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "Direct URL to fetch (must start with https://)",
                    },
                    "project_id": {
                        "type": "string",
                        "description": "Project ID for caching",
                    },
                },
                "required": ["url", "project_id"],
            },
        ),

        Tool(
            name="save_finding",
            description="""Save a research finding to the project workspace.

Use after extracting a specific citable claim from a source.
Findings persist across sessions and appear in future search_findings.

Returns the finding_id for cross-referencing.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_id": {"type": "string"},
                    "session_id": {"type": "string"},
                    "source_agent": {
                        "type": "string",
                        "description": "Which agent found this: SearchAgent|DocumentAgent|AnalyserAgent",
                    },
                    "claim": {
                        "type": "string",
                        "description": "The specific finding or claim",
                    },
                    "confidence": {
                        "type": "string",
                        "enum": ["high", "medium", "low"],
                    },
                    "source_url": {
                        "type": "string",
                        "description": "Source URL — null for internally derived findings",
                    },
                    "contradicts_id": {
                        "type": "string",
                        "description": "ID of a finding this contradicts — null if no conflict",
                    },
                },
                "required": [
                    "project_id", "session_id",
                    "source_agent", "claim", "confidence"
                ],
            },
        ),

        Tool(
            name="write_report",
            description="""Save the completed research report to the workspace.

Use as the final step of every research session.
The report is saved permanently and can be retrieved or shared.

Returns report_id.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_id": {"type": "string"},
                    "session_id": {"type": "string"},
                    "title": {"type": "string"},
                    "content_md": {
                        "type": "string",
                        "description": "Full report in Markdown with citation links",
                    },
                    "finding_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "IDs of findings cited in this report",
                    },
                },
                "required": [
                    "project_id", "session_id",
                    "title", "content_md", "finding_ids"
                ],
            },
        ),

        Tool(
            name="get_project",
            description="""Read current project state — name, status, finding count, last session.

Use at the start of every session to understand what has already been done.
Read-only — no side effects. Always safe to call.

Returns project metadata and recent activity summary.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_id": {"type": "string"},
                },
                "required": ["project_id"],
            },
        ),

        Tool(
            name="search_findings",
            description="""Search existing findings in the project by keyword.

Use before researching a topic to check what's already known.
Prevents duplicate research across sessions.

Returns matching findings with their provenance (source_agent, source_url, confidence).""",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_id": {"type": "string"},
                    "query": {
                        "type": "string",
                        "description": "Keywords to search in existing findings",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max results to return (default 10)",
                        "default": 10,
                    },
                },
                "required": ["project_id", "query"],
            },
        ),

    ])


# ─── Tool implementations ─────────────────────────────────────────

@app.call_tool()
async def call_tool(name: str, arguments: dict) -> CallToolResult:
    """Route tool calls to their implementations."""

    try:
        if name == "web_search":
            return await _web_search(arguments)
        elif name == "read_document":
            return await _read_document(arguments)
        elif name == "save_finding":
            return await _save_finding(arguments)
        elif name == "write_report":
            return await _write_report(arguments)
        elif name == "get_project":
            return await _get_project(arguments)
        elif name == "search_findings":
            return await _search_findings(arguments)
        else:
            return error_response(
                category="invalid_input",
                message=f"Unknown tool: {name}",
                is_retryable=False,
            )

    except Exception as e:
        log.error("tool_error", tool=name, error=str(e))
        return error_response(
            category="service_unavailable",
            message=f"Tool {name} failed: {str(e)}",
            is_retryable=True,
            retry_after_seconds=5,
        )


async def _web_search(args: dict) -> CallToolResult:
    """Search the web via Anthropic's web search capability."""
    query = args.get("query", "")
    max_results = args.get("max_results", 5)

    if not query.strip():
        return error_response(
            category="invalid_input",
            message="Query cannot be empty",
            is_retryable=False,
        )

    log.info("web_search", query=query)

    # Use httpx to call a search API
    # In production — wire to Brave Search, Tavily, or similar
    # For now returns a structured placeholder
    try:
        results = {
            "query": query,
            "results": [],
            "total_found": 0,
            "note": "Configure SEARCH_API_KEY in .env to enable live search",
        }

        search_api_key = os.getenv("SEARCH_API_KEY")
        if search_api_key:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    "https://api.search.brave.com/res/v1/web/search",
                    params={"q": query, "count": max_results},
                    headers={"X-Subscription-Token": search_api_key},
                    timeout=10.0,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    results["results"] = [
                        {
                            "title": r.get("title", ""),
                            "url": r.get("url", ""),
                            "snippet": r.get("description", ""),
                            "published_date": r.get("age"),
                            "credibility_signal": None,
                        }
                        for r in data.get("web", {}).get("results", [])
                    ]
                    results["total_found"] = len(results["results"])
                    del results["note"]
                elif resp.status_code == 429:
                    return error_response(
                        category="rate_limit",
                        message="Search API rate limit reached",
                        is_retryable=True,
                        retry_after_seconds=30,
                    )

        return CallToolResult(
            content=[TextContent(type="text", text=json.dumps(results))]
        )

    except httpx.TimeoutException:
        return error_response(
            category="service_unavailable",
            message="Search API timed out",
            is_retryable=True,
            retry_after_seconds=10,
        )


async def _read_document(args: dict) -> CallToolResult:
    """Fetch document content from a URL."""
    url = args.get("url", "")
    project_id = args.get("project_id", "")

    if not url.startswith("https://"):
        return error_response(
            category="invalid_input",
            message="URL must start with https://",
            is_retryable=False,
        )

    log.info("read_document", url=url)

    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            resp = await client.get(
                url,
                headers={"User-Agent": "Lens Research Agent 0.1"},
                timeout=15.0,
            )

            if resp.status_code == 404:
                return error_response(
                    category="not_found",
                    message=f"Document not found: {url}",
                    is_retryable=False,
                )
            elif resp.status_code == 401 or resp.status_code == 403:
                return error_response(
                    category="auth_error",
                    message=f"Access denied to: {url}",
                    is_retryable=False,
                )
            elif resp.status_code == 429:
                return error_response(
                    category="rate_limit",
                    message="Rate limited by source",
                    is_retryable=True,
                    retry_after_seconds=30,
                )

            # Return raw content — agents extract structure
            content = {
                "url": url,
                "status_code": resp.status_code,
                "content_type": resp.headers.get("content-type", ""),
                "text": resp.text[:10000],  # Limit to 10k chars
                "truncated": len(resp.text) > 10000,
            }

            return CallToolResult(
                content=[TextContent(type="text", text=json.dumps(content))]
            )

    except httpx.TimeoutException:
        return error_response(
            category="service_unavailable",
            message=f"Timed out fetching: {url}",
            is_retryable=True,
            retry_after_seconds=10,
        )


async def _save_finding(args: dict) -> CallToolResult:
    """Save a research finding to the database."""
    try:
        finding_id = await store.save_finding(
            project_id=args["project_id"],
            session_id=args["session_id"],
            source_agent=args["source_agent"],
            claim=args["claim"],
            confidence=args["confidence"],
            source_url=args.get("source_url"),
            contradicts_id=args.get("contradicts_id"),
        )

        return CallToolResult(
            content=[TextContent(
                type="text",
                text=json.dumps({"finding_id": finding_id, "saved": True})
            )]
        )

    except KeyError as e:
        return error_response(
            category="invalid_input",
            message=f"Missing required field: {e}",
            is_retryable=False,
        )


async def _write_report(args: dict) -> CallToolResult:
    """Save the final report to the database."""
    try:
        report_id = await store.save_report(
            project_id=args["project_id"],
            session_id=args["session_id"],
            title=args["title"],
            content_md=args["content_md"],
            finding_ids=args.get("finding_ids", []),
        )

        return CallToolResult(
            content=[TextContent(
                type="text",
                text=json.dumps({"report_id": report_id, "saved": True})
            )]
        )

    except KeyError as e:
        return error_response(
            category="invalid_input",
            message=f"Missing required field: {e}",
            is_retryable=False,
        )


async def _get_project(args: dict) -> CallToolResult:
    """Read project state — read-only Resource primitive."""
    project_id = args.get("project_id", "")

    try:
        project = store.db["projects"].get(project_id)
        sessions = await store.get_project_sessions(project_id)
        findings = await store.get_project_findings(project_id, limit=5)

        result = {
            "id": project["id"],
            "name": project["name"],
            "description": project["description"],
            "status": project["status"],
            "session_count": len(sessions),
            "finding_count": len(
                list(store.db["findings"].rows_where(
                    "project_id = ?", [project_id]
                ))
            ),
            "recent_sessions": [
                {
                    "id": s["id"],
                    "status": s["status"],
                    "step": s["current_step"],
                    "goal": s["goal"][:80],
                }
                for s in sessions[:3]
            ],
            "recent_findings": [
                {
                    "claim": f["claim"][:100],
                    "confidence": f["confidence"],
                    "source_agent": f["source_agent"],
                }
                for f in findings
            ],
        }

        return CallToolResult(
            content=[TextContent(type="text", text=json.dumps(result))]
        )

    except Exception:
        return error_response(
            category="not_found",
            message=f"Project not found: {project_id}",
            is_retryable=False,
        )


async def _search_findings(args: dict) -> CallToolResult:
    """Search findings by keyword — read-only Resource primitive."""
    project_id = args.get("project_id", "")
    query = args.get("query", "").lower()
    limit = args.get("limit", 10)

    all_findings = await store.get_project_findings(project_id, limit=200)

    # Simple keyword search — Phase 3 adds vector embeddings
    matches = [
        f for f in all_findings
        if query in f["claim"].lower()
        or (f.get("source_url") and query in f["source_url"].lower())
    ][:limit]

    return CallToolResult(
        content=[TextContent(
            type="text",
            text=json.dumps({
                "query": query,
                "matches": matches,
                "total_matches": len(matches),
            })
        )]
    )


async def main():
    """Run the MCP server over stdio."""
    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options(),
        )


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
