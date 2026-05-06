# Lens

> Your work deserves to persist.

Lens is an open source AI research workspace. Drop in URLs, PDFs, and topics — multiple agents process them in parallel, every finding is saved, and your projects build on each other over time.

Not a chatbot. A workspace.

---

## The problem

You use Claude for research. You get great answers. You close the tab.

Next week you start over.

Claude's memory remembers **you** — your name, your style, your preferences.  
It doesn't remember your **work** — your sources, your findings, your decisions.

This is true whether you're a developer tracing a complex bug across dozens of threads and docs, a PM doing competitor research, or an analyst synthesising a market landscape. The work disappears. You rebuild it from scratch. Every time.

Lens fixes this.

---

## What Lens does differently

| Claude in a chat tab | Lens |
|---|---|
| One context window | Parallel agents across unlimited sources |
| Session ends, work disappears | Every finding saved to your project |
| Start from scratch next session | Picks up exactly where you left off |
| Chat transcript | Shareable structured report |
| Memory remembers you | Workspace remembers your work |

---

## How it works

Lens uses a multi-agent architecture where specialist agents work in parallel:

```
Your research question or topic
            ↓
    ┌──────────────────┐
    │   Coordinator    │  decomposes task, delegates, synthesises
    └──────┬───────────┘
           │
    ┌──────┼──────────────┐
    ↓      ↓              ↓
┌──────┐ ┌──────────┐ ┌────────┐
│Search│ │ Document │ │Analyser│
│Agent │ │  Agent   │ │ Agent  │
└──────┘ └──────────┘ └────────┘
    │         │            │
    └─────────┴────────────┘
                ↓
         ┌────────────┐
         │   Writer   │  structured report with citations
         └────────────┘
                ↓
    Saved to your project workspace
    Persistent across sessions
    Shareable with your team
```

Every finding is tagged with its source. Every session continues from the last. Your projects are organised, searchable, and exportable.

---

## Features

- **Persistent workspaces** — projects save every source, finding, and decision
- **Parallel research** — multiple agents work simultaneously across sources
- **Session continuity** — resume any project exactly where you left off
- **Structured output** — reports, not transcripts. Shareable with anyone
- **Source provenance** — every claim traces back to its source
- **Web UI** — clean interface for non-technical users
- **CLI** — full terminal access for developers
- **MCP integration** — connect your own tools and data sources

---

## Who it's for

**Developers** — preserve investigation context across sessions. Debug a complex issue over days without losing your trail. Evaluate libraries and keep the rationale.

**Product managers** — build competitor research that persists and grows. Every update adds to the project rather than starting over.

**Analysts** — synthesise sources at scale. Process more than one context window can hold. Output structured reports ready to share.

**Researchers** — accumulate knowledge across sessions. Every source cited, every finding traceable.

---

## Quick start

```bash
# Clone
git clone https://github.com/yourusername/lens
cd lens

# Install
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Configure
cp .env.example .env
# Add your ANTHROPIC_API_KEY to .env

# Run
python -m lens.cli start

# Or web UI
uvicorn lens.web.app:app --reload
# Open http://localhost:8000
```

---

## Architecture

Lens is built on production-grade patterns from the Claude Agent SDK:

| Component | File | Pattern |
|---|---|---|
| Coordinator | `lens/coordinator.py` | Hub-and-spoke orchestration |
| Agents | `lens/agents/` | Scoped context, parallel execution |
| Session state | `lens/session_store.py` | SQLite persistence, resumption |
| MCP server | `lens/mcp_server.py` | Custom tools for workspace access |
| Schemas | `lens/schemas.py` | Pydantic validation, retry loops |
| Web UI | `lens/web/` | FastAPI + HTMX |

Every architectural decision is documented in [`docs/architecture.md`](docs/architecture.md).

---

## Roadmap

**Phase 1 — Core pipeline** *(in progress)*
- [ ] Coordinator + 4 specialist agents
- [ ] Session state with SQLite persistence
- [ ] Basic CLI interface
- [ ] Markdown report output

**Phase 2 — Web UI**
- [ ] FastAPI backend
- [ ] Project workspace UI
- [ ] Source upload (PDF, URL, text)
- [ ] Report viewer and export

**Phase 3 — MCP + integrations**
- [ ] Custom MCP server
- [ ] Notion export
- [ ] Obsidian export
- [ ] Google Drive integration

**Phase 4 — Collaboration**
- [ ] Shared workspaces
- [ ] Team annotations
- [ ] Comment and review flow

---

## Why not just use Claude?

Claude is exceptional at answering questions. Lens is built for something different — accumulating and organising work over time.

**Use Claude when:** you need a quick answer, a one-off summary, or help with a single task.

**Use Lens when:** you're doing multi-session research, processing more sources than one context window can hold, or need output you can share and build on.

They complement each other. Lens uses Claude under the hood.

---

## Contributing

Lens is early and moving fast. If you want to contribute:

1. Check open issues for good first tasks
2. Read [`docs/architecture.md`](docs/architecture.md) to understand the system
3. Open a PR — all contributions welcome

---

## Stack

- **Python 3.11+**
- **Anthropic Claude Agent SDK**
- **FastAPI** — web backend
- **HTMX** — lightweight frontend
- **SQLite** — session and workspace persistence
- **Pydantic** — schema validation
- **Click** — CLI
- **MCP** — tool integration

---

## License

MIT — free to use, modify, and distribute.

---

*Built in public. Follow the journey on [LinkedIn](https://linkedin.com/in/yourprofile).*
