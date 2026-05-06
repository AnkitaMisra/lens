# Contributing to Lens

Thanks for your interest in contributing! Lens is built in public and welcomes all contributions.

## Quickest way to start — GitHub Codespace

No local setup required. Just:

1. Fork the repo on GitHub
2. Click **Code → Codespaces → Create codespace on main**
3. Wait ~2 minutes for the environment to build
4. You're ready — Python 3.11, all dependencies, Claude Code installed

**Add your API key:**
- Go to `github.com/settings/codespaces`
- Click **New secret**
- Name: `ANTHROPIC_API_KEY`
- Value: your key from `console.anthropic.com`
- Select the Lens repo

## Local setup

```bash
git clone https://github.com/yourusername/lens
cd lens
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
cp .env.example .env
# Add your ANTHROPIC_API_KEY to .env
```

## Running Lens

```bash
# CLI
lens research "impact of LLMs on software engineering"

# Web UI
uvicorn lens.web.app:app --reload
# Open http://localhost:8000

# Claude Code
claude
```

## Project structure

```
lens/
├── coordinator.py      ← hub — orchestrates all agents (Domain 1)
├── agents/
│   ├── search_agent.py
│   ├── document_agent.py
│   ├── analyser_agent.py
│   └── writer_agent.py
├── session_store.py    ← SQLite persistence + resumption (Domain 5)
├── mcp_server.py       ← 6 workspace MCP tools (Domain 4)
├── schemas.py          ← Pydantic models + validation (Domain 3)
├── hooks.py            ← pre/post tool intercepts (Domain 1)
├── cli.py              ← Click CLI entry point
└── web/                ← FastAPI + HTMX (Phase 2)
```

## How to contribute

1. Check open issues for good first tasks
2. Read `docs/architecture.md` before making structural changes
3. Run tests: `pytest`
4. Open a PR — all contributions welcome

## Code standards

- Python 3.11+ with type hints on all public functions
- Pydantic for all data models
- async/await for all I/O — httpx not requests
- pytest for all tests — mock all external calls
- Black for formatting, ruff for linting
- Google-style docstrings

## Questions?

Open an issue or start a discussion. Building in public means building together.
