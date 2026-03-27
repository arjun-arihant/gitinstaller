#!/usr/bin/env bash
set -euo pipefail

echo "============================================"
echo " GitInstaller Setup"
echo "============================================"
echo

BASE_DIR="$(cd "$(dirname "$0")" && pwd)"
GI_DIR="$BASE_DIR/.gitinstaller"
NODE_DIR="$GI_DIR/node"
NODE_VERSION="22.14.0"

# Determine platform / architecture
OS="$(uname -s)"
ARCH="$(uname -m)"

case "$OS" in
  Linux)
    case "$ARCH" in
      x86_64)  NODE_TRIPLE="linux-x64";    NODE_EXT="tar.xz" ;;
      aarch64) NODE_TRIPLE="linux-arm64";  NODE_EXT="tar.xz" ;;
      *) echo "[ERROR] Unsupported Linux arch: $ARCH"; exit 1 ;;
    esac
    ;;
  Darwin)
    case "$ARCH" in
      arm64)  NODE_TRIPLE="darwin-arm64"; NODE_EXT="tar.gz" ;;
      x86_64) NODE_TRIPLE="darwin-x64";  NODE_EXT="tar.gz" ;;
      *) echo "[ERROR] Unsupported macOS arch: $ARCH"; exit 1 ;;
    esac
    ;;
  *)
    echo "[ERROR] Unsupported OS: $OS"
    exit 1
    ;;
esac

NODE_BIN="$NODE_DIR/bin/node"
NODE_ARCHIVE_NAME="node-v${NODE_VERSION}-${NODE_TRIPLE}.${NODE_EXT}"
NODE_URL="https://nodejs.org/dist/v${NODE_VERSION}/${NODE_ARCHIVE_NAME}"

# -------- Check for portable Node.js already installed --------
if [ -x "$NODE_BIN" ]; then
  echo "[OK] Portable Node.js already present at:"
  echo "     $NODE_BIN"
  # Ensure it's on PATH for npm install below
  export PATH="$NODE_DIR/bin:$PATH"
  goto_npm_install=1
else
  goto_npm_install=0
fi

# -------- Check for system Node.js --------
if [ "$goto_npm_install" -eq 0 ] && command -v node &>/dev/null; then
  echo "[OK] System Node.js found in PATH. Skipping download."
  goto_npm_install=1
fi

# -------- Download portable Node.js --------
if [ "$goto_npm_install" -eq 0 ]; then
  echo "[*] Node.js not found. Downloading portable Node.js v${NODE_VERSION}..."
  echo

  mkdir -p "$GI_DIR"
  ARCHIVE_PATH="$GI_DIR/$NODE_ARCHIVE_NAME"

  echo "    Downloading from: $NODE_URL"
  echo "    To: $ARCHIVE_PATH"
  echo

  # Try curl first, then wget
  if command -v curl &>/dev/null; then
    curl -fsSL --progress-bar "$NODE_URL" -o "$ARCHIVE_PATH"
  elif command -v wget &>/dev/null; then
    wget -q --show-progress "$NODE_URL" -O "$ARCHIVE_PATH"
  else
    echo "[ERROR] Neither curl nor wget is available. Cannot download Node.js."
    exit 1
  fi

  echo "[*] Extracting Node.js..."
  TEMP_EXTRACT="$GI_DIR/node_temp"
  mkdir -p "$TEMP_EXTRACT"

  if [ "$NODE_EXT" = "tar.xz" ]; then
    tar -xJf "$ARCHIVE_PATH" -C "$TEMP_EXTRACT"
  else
    tar -xzf "$ARCHIVE_PATH" -C "$TEMP_EXTRACT"
  fi

  # Move extracted folder (node-v{version}-{triple}/) to node/
  EXTRACTED_DIR="$TEMP_EXTRACT/node-v${NODE_VERSION}-${NODE_TRIPLE}"
  if [ ! -d "$EXTRACTED_DIR" ]; then
    # Fallback: find any node-v* directory
    EXTRACTED_DIR="$(find "$TEMP_EXTRACT" -maxdepth 1 -type d -name 'node-v*' | head -1)"
  fi

  if [ -z "$EXTRACTED_DIR" ] || [ ! -d "$EXTRACTED_DIR" ]; then
    echo "[ERROR] Could not find extracted Node.js directory in $TEMP_EXTRACT"
    exit 1
  fi

  mv "$EXTRACTED_DIR" "$NODE_DIR"
  rm -rf "$TEMP_EXTRACT" "$ARCHIVE_PATH"

  if [ ! -x "$NODE_BIN" ]; then
    echo "[ERROR] Node.js extraction succeeded but binary not found at: $NODE_BIN"
    exit 1
  fi

  # Make executable
  chmod +x "$NODE_BIN"
  export PATH="$NODE_DIR/bin:$PATH"

  echo "[OK] Portable Node.js installed to: $NODE_DIR"
  echo
fi

# -------- Install npm dependencies --------
echo "[*] Installing npm dependencies (node_modules)..."
echo

(cd "$BASE_DIR" && npm install)

echo
echo "============================================"
echo " Setup complete!"
echo "============================================"
echo
echo " Usage:"
echo "   ./gitinstaller.sh install https://github.com/owner/repo"
echo
echo " Make sure you have a .env file with your OpenRouter API key."
echo " (Copy .env.example to .env and fill in OPENROUTER_API_KEY)"
echo
