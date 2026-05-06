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

## Prerequisites

Before using Lens you need:

**1. An Anthropic API key (required)**

Lens calls the Claude API to power its research agents. You need your own API key:

1. Go to **[console.anthropic.com](https://console.anthropic.com)**
2. Sign in or create a free account
3. Click **API Keys** → **Create Key**
4. Copy your key — you only see it once

New accounts get **$5 free credits** — enough for 25–50 research sessions.

Add it to your `.env` file:
```bash
cp .env.example .env
# Edit .env and set ANTHROPIC_API_KEY=your_key_here
```

Or export it in your terminal:
```bash
export ANTHROPIC_API_KEY=sk-ant-api03-your-key-here
```

**2. Python 3.11+**
```bash
python3 --version  # must be 3.11 or higher
```

Install via Homebrew on Mac: `brew install python@3.11`

**3. Optional — Search API key for web search**

Lens uses the Brave Search API for web research. Without it, the search agent returns a placeholder. Add to `.env`:
```bash
SEARCH_API_KEY=your_brave_search_key
```

Get a free key at **[brave.com/search/api](https://brave.com/search/api)** — free tier includes 2,000 queries/month.

---

## Quick start

```bash
# Clone
git clone https://github.com/AnkitaMisra/lens
cd lens

# Install
python3 -m venv .venv
source .venv/bin/activate  # Mac/Linux
pip install -r requirements.txt
pip install -e .

# Configure
cp .env.example .env
# Edit .env — add your ANTHROPIC_API_KEY

# Create data directory
mkdir -p data

# Run your first research session
lens research "what is model context protocol"
```

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

## CLI commands

```bash
# Research a topic
lens research "impact of LLMs on software engineering"

# Research within a specific project
lens research "AI safety approaches" --project your-project-id

# Resume an interrupted session
lens research "climate tech" --resume your-session-id

# Save report to a file
lens research "quantum computing" --output report.md

# List all sessions
lens sessions

# Create a new project
lens new "My Research Project"
```

---

## Features

- **Persistent workspaces** — projects save every source, finding, and decision
- **Parallel research** — multiple agents work simultaneously across sources
- **Session continuity** — resume any project exactly where you left off
- **Structured output** — reports, not transcripts. Shareable with anyone
- **Source provenance** — every claim traces back to its source
- **CLI** — full terminal access for developers
- **Web UI** — coming in Phase 2
- **MCP integration** — connect your own tools and data sources

---

## Who it's for

**Developers** — preserve investigation context across sessions. Debug a complex issue over days without losing your trail. Evaluate libraries and keep the rationale.

**Product managers** — build competitor research that persists and grows. Every update adds to the project rather than starting over.

**Analysts** — synthesise sources at scale. Process more than one context window can hold. Output structured reports ready to share.

**Researchers** — accumulate knowledge across sessions. Every source cited, every finding traceable.

---

## Why not just use Claude?

Claude is exceptional at answering questions. Lens is built for something different — accumulating and organising work over time.

**Use Claude when:** you need a quick answer, a one-off summary, or help with a single task.

**Use Lens when:** you're doing multi-session research, processing more sources than one context window can hold, or need output you can share and build on.

They complement each other. Lens uses Claude under the hood.

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
| CLI | `lens/cli.py` | Click CLI entry point |

Every architectural decision is documented in [`docs/architecture.md`](docs/architecture.md).

---

## Roadmap

**Phase 1 — Core pipeline** ✅ *complete*
- [x] Coordinator + 4 specialist agents
- [x] Session state with SQLite persistence
- [x] CLI interface
- [x] Markdown report output
- [x] MCP server with 6 workspace tools

**Phase 2 — Web UI** *(in progress)*
- [ ] FastAPI backend
- [ ] Project workspace UI
- [ ] Source upload (PDF, URL, text)
- [ ] Report viewer and export

**Phase 3 — Integrations**
- [ ] Google Drive MCP
- [ ] Notion export
- [ ] Obsidian vault sync

**Phase 4 — Collaboration**
- [ ] Shared workspaces
- [ ] Team annotations
- [ ] Review and approval flow

---

## Contributing

Read [CONTRIBUTING.md](CONTRIBUTING.md) for setup instructions.

Quickest way to start — open a GitHub Codespace:
1. Fork the repo
2. Click **Code → Codespaces → Create codespace on main**
3. Add your `ANTHROPIC_API_KEY` at `github.com/settings/codespaces`
4. You're ready — no local setup needed

---

## Stack

- **Python 3.11+**
- **Anthropic Claude API** — powers all research agents
- **FastAPI** — web backend (Phase 2)
- **SQLite** — session and workspace persistence
- **Pydantic** — schema validation
- **Click** — CLI
- **MCP** — tool integration

---

## License

MIT — free to use, modify, and distribute.

---

*Built in public. Follow the journey on [LinkedIn](https://linkedin.com/in/ankitamisra).*
