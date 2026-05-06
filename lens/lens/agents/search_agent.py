"""
search_agent.py — Lens Search Agent
Responsibility: Web discovery only — no analysis, no writing

Receives a search query from the coordinator.
Returns structured SearchAgentOutput validated against schema.
Does NOT validate sources, read full pages, or save findings.
That's the Document Agent's job.
"""

import anthropic
import structlog
from pydantic import ValidationError

from lens.schemas import SearchAgentOutput, SearchResult

log = structlog.get_logger(__name__)

SYSTEM_PROMPT = """You are a web research specialist. Your only job is to search
for relevant sources on a given topic and return structured results.

You must call the web_search tool with the provided query.
After receiving results, return them in this exact JSON structure:

{
  "query": "the search query used",
  "results": [
    {
      "title": "page title",
      "url": "full URL",
      "snippet": "2-3 sentence description",
      "published_date": "ISO date or null if unknown",
      "credibility_signal": "brief note on source credibility or null"
    }
  ],
  "total_found": number
}

Return ONLY the JSON. No explanation. No preamble."""


class SearchAgent:
    """
    Web discovery agent.

    Scoped tools: web_search only.
    Cannot write, save, or modify anything.
    Returns validated SearchAgentOutput.
    """

    def __init__(self):
        self.client = anthropic.Anthropic()
        self.tools = [
            {
                "name": "web_search",
                "type": "web_search_20250305",
            }
        ]

    async def run(self, task: str | dict) -> dict:
        """
        Search the web for the given query.

        Args:
            task: Either a query string or a dict with
                  'original_task' and 'retry_feedback' keys

        Returns:
            Validated SearchAgentOutput as dict

        Raises:
            ValidationError: If output doesn't match schema
        """
        # Handle retry with feedback
        if isinstance(task, dict) and "retry_feedback" in task:
            query = task["original_task"]
            feedback = task["retry_feedback"]
            user_message = f"Query: {query}\n\nFeedback from previous attempt: {feedback}"
        else:
            query = task
            user_message = f"Query: {query}"

        log.info("search_agent_running", query=query)

        response = self.client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2000,
            system=SYSTEM_PROMPT,
            tools=self.tools,
            messages=[{"role": "user", "content": user_message}],
        )

        # Extract text response
        text_content = ""
        for block in response.content:
            if hasattr(block, "text"):
                text_content = block.text
                break

        # Parse and validate against schema
        import json
        try:
            raw = json.loads(text_content)
            output = SearchAgentOutput(**raw)
            log.info(
                "search_agent_complete",
                query=query,
                result_count=len(output.results),
            )
            return output.model_dump()
        except (json.JSONDecodeError, ValidationError) as e:
            log.warning("search_agent_parse_failed", error=str(e))
            # Return minimal valid structure on parse failure
            return SearchAgentOutput(
                query=query,
                results=[],
                total_found=0,
            ).model_dump()
