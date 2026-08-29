#!/usr/bin/env bash
# =============================================================================
# setup-submodules.sh — Hermes Agent Aizen Version: Tier 1 Submodule Setup
#
# Adds curated Git submodules for the Aizen Version ecosystem.
# Run from the project root: bash scripts/setup-submodules.sh
# =============================================================================

set -euo pipefail

SUBMODULES_DIR="vendor"

echo "╔══════════════════════════════════════════════════════════╗"
echo "║  Hermes Agent — Aizen Version: Submodule Setup          ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""

mkdir -p "$SUBMODULES_DIR"

# ---- Tier 1: Core Integrations ----
echo "📦 Tier 1: Core Integrations"
echo "──────────────────────────────"

# code-server (VS Code in browser) — Docker sidecar
if [ ! -d "$SUBMODULES_DIR/code-server" ]; then
  echo "  ⚡ Adding code-server (VS Code in browser)..."
  git submodule add --depth 1 https://github.com/coder/code-server.git "$SUBMODULES_DIR/code-server"
else
  echo "  ✓ code-server already added"
fi

# MCP servers (pre-built Model Context Protocol integrations)
if [ ! -d "$SUBMODULES_DIR/mcp-servers" ]; then
  echo "  ⚡ Adding MCP servers..."
  git submodule add --depth 1 https://github.com/modelcontextprotocol/servers.git "$SUBMODULES_DIR/mcp-servers"
else
  echo "  ✓ mcp-servers already added"
fi

# xterm.js (terminal emulator — already a dep, add for addon access)
if [ ! -d "$SUBMODULES_DIR/xterm.js" ]; then
  echo "  ⚡ Adding xterm.js..."
  git submodule add --depth 1 https://github.com/xtermjs/xterm.js.git "$SUBMODULES_DIR/xterm.js"
else
  echo "  ✓ xterm.js already added"
fi

# JSON Crack (data visualization)
if [ ! -d "$SUBMODULES_DIR/jsoncrack" ]; then
  echo "  ⚡ Adding JSON Crack (data viz)..."
  git submodule add --depth 1 https://github.com/AykutSarac/jsoncrack.com.git "$SUBMODULES_DIR/jsoncrack"
else
  echo "  ✓ jsoncrack already added"
fi

echo ""

# ---- Tier 2: Reference Architecture (sparse clone for patterns) ----
echo "📚 Tier 2: Reference Architecture"
echo "──────────────────────────────────"

# Open WebUI (RAG pipeline, model management UI)
if [ ! -d "$SUBMODULES_DIR/open-webui" ]; then
  echo "  ⚡ Adding Open WebUI (RAG reference)..."
  git submodule add --depth 1 https://github.com/open-webui/open-webui.git "$SUBMODULES_DIR/open-webui"
else
  echo "  ✓ open-webui already added"
fi

# Lobe Chat (plugin architecture, model routing)
if [ ! -d "$SUBMODULES_DIR/lobe-chat" ]; then
  echo "  ⚡ Adding Lobe Chat (plugin arch reference)..."
  git submodule add --depth 1 https://github.com/lobehub/lobe-chat.git "$SUBMODULES_DIR/lobe-chat"
else
  echo "  ✓ lobe-chat already added"
fi

# Block Suite (collaborative editing)
if [ ! -d "$SUBMODULES_DIR/blocksuite" ]; then
  echo "  ⚡ Adding BlockSuite (collab editing)..."
  git submodule add --depth 1 https://github.com/toeverything/blocksuite.git "$SUBMODULES_DIR/blocksuite"
else
  echo "  ✓ blocksuite already added"
fi

echo ""

# ---- Tier 3: Specialized Tools ----
echo "🔧 Tier 3: Specialized Tools"
echo "──────────────────────────────"

# Goose (agent orchestration patterns)
if [ ! -d "$SUBMODULES_DIR/goose" ]; then
  echo "  ⚡ Adding Goose (agent orchestration)..."
  git submodule add --depth 1 https://github.com/block/goose.git "$SUBMODULES_DIR/goose"
else
  echo "  ✓ goose already added"
fi

# CrewAI (multi-agent patterns)
if [ ! -d "$SUBMODULES_DIR/crewai" ]; then
  echo "  ⚡ Adding CrewAI (multi-agent patterns)..."
  git submodule add --depth 1 https://github.com/crewAIInc/crewAI.git "$SUBMODULES_DIR/crewai"
else
  echo "  ✓ crewai already added"
fi

# Dify (workflow builder patterns)
if [ ! -d "$SUBMODULES_DIR/dify" ]; then
  echo "  ⚡ Adding Dify (workflow builder)..."
  git submodule add --depth 1 https://github.com/langgenius/dify.git "$SUBMODULES_DIR/dify"
else
  echo "  ✓ dify already added"
fi

echo ""
echo "════════════════════════════════════════"
echo "  ✅ All submodules configured!"
echo "  Run: git submodule update --init --recursive"
echo "════════════════════════════════════════"
