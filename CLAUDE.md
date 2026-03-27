# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

A CLI tool that autonomously installs GitHub repositories using an LLM agentic loop. The LLM decides what to do; the code just executes tool calls.

```
node index.js install https://github.com/user/repo
```

## Setup

**Fresh PC (no Node.js installed):**
```bash
# Windows
setup.bat

# Linux/macOS
chmod +x setup.sh gitinstaller.sh && ./setup.sh
```

**Already have Node.js:**
```bash
npm install
cp .env.example .env   # then fill in OPENROUTER_API_KEY
```

Node.js and Python are both managed automatically — no prerequisites needed.
- Node.js is downloaded via `setup.bat`/`setup.sh` and cached in `.gitinstaller/node/`.
- Python is downloaded via `python-build-standalone` on first run and cached in `.gitinstaller/python/`.

## Running

```bash
# Windows (works whether Node.js is system-installed or portable)
gitinstaller.bat install https://github.com/owner/repo

# Linux/macOS
./gitinstaller.sh install https://github.com/owner/repo

# Or directly if Node.js is already on PATH
node index.js install https://github.com/owner/repo
```

There are no build steps, no tests, and no lint configuration.

## Architecture

The agentic loop is the core concept: `index.js` bootstraps → downloads the ZIP → ensures Python exists → hands off to `agent.js`, which calls the LLM in a loop until `finish()` is called or the 40-call hard cap is hit.

```
index.js          CLI entry, .env loading, orchestration
src/agent.js      Agentic loop — calls LLM, dispatches tools, manages message history
src/llm.js        OpenRouter API client (model: xiaomi/mimo-v2-flash, temp 0.2)
src/tools.js      6 tool implementations + OpenAI function-calling schemas
src/prompt.js     System prompt template (prescriptive install workflow for a small model, includes hardware detection + WebUI generation)
src/github.js     ZIP download + extraction (strips the {repo}-{branch}/ wrapper)
src/python.js     python-build-standalone download, caching, venv helpers
src/security.js   Path sandboxing (validatePath) + command blocklist (validateCommand)
src/logger.js     Shared spinner-safe log() used by all src/ files
```

### Message loop invariant

The OpenRouter API requires that after any assistant message containing `tool_calls`, all tool results (`role: "tool"`) appear before the next API call. `agent.js` always pushes the full assistant message first, then all tool results, before calling `callLLM` again.

### Tool execution

Tools never throw — they return strings. `run_command` returns `EXIT CODE: N\nSTDOUT: ...\nSTDERR: ...` even on failure. The LLM reads this and adapts.

`finish()` returns a JSON sentinel `{ __finish: true, summary, success }` which `agent.js` detects to exit the loop.

### tar extraction

`python.js` uses a pure-JS tar extractor (`extractTarGz`) based on Node.js built-in `zlib` and manual 512-byte POSIX header parsing. No system `tar` binary is required on any platform. Do not replace this with `spawn("tar", ...)`.

### Security boundaries

`validatePath` ensures all file operations resolve inside the project directory. `validateCommand` blocks a hardcoded list of destructive commands and shell injection patterns. `run_command` uses `spawn` with `shell: false` on Linux/macOS and `shell: true` on Windows (required for `.cmd` scripts like `npm`, `npx`). The command and arg blocklists in `security.js` guard against injection when `shell: true` is active.

## Agent behaviour

### Hardware-aware installation
The prompt instructs the LLM to run `nvidia-smi` / `rocm-smi` before installing ML dependencies. Based on the result it picks the GPU or CPU requirements variant (separate files like `requirements-gpu.txt`, CUDA index URLs, `package[cuda]` extras, etc.).

### WebUI generation
After installation the LLM checks whether the project already has a UI (Gradio, Streamlit, React, etc.). If not, and if the project exposes callable functionality, it installs Gradio and writes a minimal `webui.py` to the project root. The file uses `demo.launch()` with no port overrides. Node.js and pure-library projects are excluded from WebUI generation.

## Key constraints

- **Dependencies:** `adm-zip`, `chalk`, `ora` only. No new runtime deps.
- **ESM only:** `"type": "module"` in package.json — use `import`/`export` everywhere.
- **No system Python:** always use the bundled Python from `ensurePython()` or the venv python from `getVenvPython()`.
- **Tool call cap:** 40 per install session, enforced in `agent.js`.
- **Command timeout:** 5 minutes per `run_command`, via `AbortController`.
