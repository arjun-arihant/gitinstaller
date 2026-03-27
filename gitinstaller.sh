#!/usr/bin/env bash
set -euo pipefail

BASE_DIR="$(cd "$(dirname "$0")" && pwd)"
NODE_DIR="$BASE_DIR/.gitinstaller/node"
NODE_BIN="$NODE_DIR/bin/node"

# -------- Locate Node.js --------
if [ -x "$NODE_BIN" ]; then
  # Use portable Node.js — prepend its bin dir to PATH so npm/npx are found
  export PATH="$NODE_DIR/bin:$PATH"
  NODE="$NODE_BIN"
elif command -v node &>/dev/null; then
  NODE="node"
else
  echo
  echo "[ERROR] Node.js is not installed and no portable Node.js was found."
  echo "        Please run ./setup.sh first to install Node.js automatically."
  echo
  exit 1
fi

exec "$NODE" "$BASE_DIR/index.js" "$@"
