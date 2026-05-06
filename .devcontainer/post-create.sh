#!/bin/bash
# Runs after the container is created
set -e

echo "🔧 Setting up Lens development environment..."

# Install Python dependencies
pip install -r requirements.txt
pip install -e .

# Create local .env if it doesn't exist
if [ ! -f .env ]; then
  cp .env.example .env
  echo "📝 Created .env from .env.example"
  echo "   Add your ANTHROPIC_API_KEY to .env or GitHub Codespace secrets"
fi

# Create local SQLite database directory
mkdir -p data
echo "💾 Created data/ directory for SQLite"

# Verify Claude Code is available
if command -v claude &> /dev/null; then
  echo "✅ Claude Code is available"
else
  echo "📦 Installing Claude Code..."
  npm install -g @anthropic-ai/claude-code
fi

echo ""
echo "✅ Lens dev environment ready!"
echo ""
echo "Quick start:"
echo "  lens research 'your topic'     ← run from CLI"
echo "  uvicorn lens.web.app:app --reload  ← start web UI"
echo "  claude                          ← open Claude Code"
echo ""
