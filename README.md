# GitInstaller

[![Node.js](https://img.shields.io/badge/Node.js-%3E%3D18.0-brightgreen)](https://nodejs.org)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey)](#prerequisites)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](#license)
[![ESM](https://img.shields.io/badge/ESM-only-blue)](https://nodejs.org/api/esm.html)

A CLI tool that takes a GitHub repository URL and autonomously installs it. An LLM-powered agent analyzes the project structure, determines dependencies, and executes the full install — no manual input required.

```bash
gitinstaller.bat install https://github.com/user/repo   # Windows
./gitinstaller.sh install https://github.com/user/repo   # Linux/macOS
```

## Table of Contents

- [How It Works](#how-it-works)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
  - [Windows](#windows)
  - [Linux / macOS](#linux--macos)
  - [If You Already Have Node.js](#if-you-already-have-nodejs)
- [Quick Start](#quick-start)
- [Usage](#usage)
  - [CLI Reference](#cli-reference)
  - [Code Examples](#code-examples)
- [Configuration](#configuration)
  - [Environment Variables](#environment-variables)
  - [Auto-Downloaded Dependencies](#auto-downloaded-dependencies)
  - [Installed Project Location](#installed-project-location)
- [Development](#development)
  - [Running Locally](#running-locally)
  - [Continuous Integration](#continuous-integration)
  - [Contributing](#contributing)
- [Security](#security)
- [Troubleshooting](#troubleshooting)
- [FAQ](#faq)
- [Accessibility and Localization](#accessibility-and-localization)
- [Changelog](#changelog)
- [Roadmap](#roadmap)
- [Support](#support)
- [License](#license)

## How It Works

1. **Download** — fetches the repository as a ZIP archive (no `git` required)
2. **Bundled Python** — downloads a portable Python if the project needs it (no system Python required)
3. **LLM analysis** — an LLM agent reads project files, determines the project type, and executes the correct install steps
4. **Hardware-aware** — detects NVIDIA/AMD GPUs and installs the GPU-accelerated variant when available (e.g. CUDA PyTorch, `requirements-gpu.txt`)
5. **Auto WebUI** — if the project has no UI, generates a minimal `webui.py` using Gradio so you can interact with it immediately
6. **Summary** — finishes with a report of what was installed and how to run the project

The agent handles Python projects (`requirements.txt`, `pyproject.toml`, `setup.py`), Node.js projects (`package.json`), and more.

## Prerequisites

| Platform | Requirement |
|----------|-------------|
| **Windows** | Windows 10 or newer (PowerShell is used for bootstrapping) |
| **Linux / macOS** | `curl` or `wget` must be available (almost always pre-installed) |

> **No Node.js, Python, git, or other tools required** — they are all downloaded and managed automatically on first run.

## Installation

### Windows

```bat
git clone https://github.com/arjun-arihant/gitinstaller.git
cd gitinstaller
setup.bat
```

`setup.bat` automatically downloads a portable Node.js if it is not already installed, then runs `npm install`. You only need to run it once.

### Linux / macOS

```bash
git clone https://github.com/arjun-arihant/gitinstaller.git
cd gitinstaller
chmod +x setup.sh gitinstaller.sh
./setup.sh
```

`setup.sh` automatically downloads a portable Node.js if it is not already installed, then runs `npm install`.

### If You Already Have Node.js

You can use the setup scripts (they will skip the download) or use the classic workflow:

```bash
npm install
cp .env.example .env
# edit .env and set OPENROUTER_API_KEY
node index.js install https://github.com/owner/repo
```

## Quick Start

After installation and creating a `.env` file:

```bash
# Windows
gitinstaller.bat install https://github.com/KittenML/KittenTTS

# Linux/macOS
./gitinstaller.sh install https://github.com/KittenML/KittenTTS
```

The LLM agent will analyze the repository, install dependencies, detect your GPU if present, and generate a WebUI if the project has none. The installed project is placed in `./installations/{repo-name}/`.

## Usage

### CLI Reference

```
gitinstaller install <github-repo-url>
```

| Command | Description |
|---------|-------------|
| `install <url>` | Download, analyze, and install a GitHub repository |

The tool exposes no other commands. The install session has a **hard cap of 40 LLM tool calls** and a **5-minute timeout per spawned command** to prevent runaway loops.

#### Available Agent Tools

The LLM agent can use these tools during installation:

| Tool | Description |
|------|-------------|
| `list_directory` | List directory contents with file sizes |
| `read_file` | Read a file (capped at 200 lines by default) |
| `write_file` | Write or create a file (creates parent directories) |
| `run_command` | Execute a command with arguments (returns stdout, stderr, exit code) |
| `report_progress` | Log a progress update to the user |
| `finish` | Signal that installation is complete |

### Code Examples

**Install a Python project with GPU detection:**

```bash
gitinstaller.bat install https://github.com/user/my-ml-project
# Agent detects NVIDIA GPU, installs PyTorch with CUDA, writes webui.py
```

**Install a Node.js project:**

```bash
./gitinstaller.sh install https://github.com/user/my-node-app
# Agent runs npm install, reports setup instructions
```

## Configuration

### Environment Variables

Create a `.env` file in the project root (use `.env.example` as a template):

```env
OPENROUTER_API_KEY=sk-or-v1-xxxxxxxxxxxxxxxxxxxxxxxx
```

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENROUTER_API_KEY` | Yes | API key from [openrouter.ai](https://openrouter.ai). Used to call the LLM model. |

The `.env` file is loaded manually by `index.js` (no `dotenv` dependency). If `OPENROUTER_API_KEY` is already set in the environment, the `.env` file is not required.

The tool uses the `xiaomi/mimo-v2-flash` model via OpenRouter, one of the cheapest available options.

### Auto-Downloaded Dependencies

| Dependency | When | Cached Location |
|------------|------|-----------------|
| Portable Node.js 22 LTS | First `setup.bat` / `setup.sh` run (if Node.js not in PATH) | `.gitinstaller/node/` |
| Portable Python 3.12 | When installing a Python project | `.gitinstaller/python/` |

Both are cached after the first download. The `.gitinstaller/` directory is gitignored.

### Installed Project Location

Installed projects are placed in `./installations/{repo-name}/`.

## Development

### Project Structure

```
index.js          CLI entry point, .env loading, orchestration
src/agent.js      Agentic loop — calls LLM, dispatches tools, manages message history
src/llm.js        OpenRouter API client
src/tools.js      6 tool implementations + OpenAI function-calling schemas
src/prompt.js     System prompt template (install workflow, hardware detection, WebUI generation)
src/github.js     ZIP download + extraction
src/python.js     python-build-standalone download, caching, venv helpers
src/security.js   Path sandboxing + command blocklist
src/logger.js     Shared spinner-safe logging
```

### Running Locally

```bash
npm install
cp .env.example .env
# Set OPENROUTER_API_KEY in .env
node index.js install https://github.com/owner/repo
```

### Dependencies

Only three runtime dependencies:

| Package | Purpose |
|---------|---------|
| `adm-zip` | ZIP archive extraction |
| `chalk` | Terminal output coloring |
| `ora` | Terminal spinners |

No new runtime dependencies should be added.

### Testing

There are no automated tests in this project. Verification is done manually by running `node index.js install` against a known repository and confirming the expected behavior.

### Continuous Integration

A GitHub Actions workflow for linting and validation:

```yaml
# .github/workflows/ci.yml
name: CI
on: [push, pull_request]
jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 22
      - run: npm install
      - run: node --check index.js
      - run: node --check src/agent.js
      - run: node --check src/llm.js
      - run: node --check src/tools.js
```

### Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/my-feature`)
3. Make your changes
4. Verify by running the installer against a test repository
5. Open a pull request

Please keep changes focused. The codebase follows ESM conventions (`"type": "module"` in `package.json`) — use `import`/`export` everywhere.

## Security

- **Path sandboxing** — `validatePath` ensures all file operations stay inside the project directory. No writes are permitted outside the target project.
- **Command blocklist** — `validateCommand` blocks destructive commands (`rm -rf /`, `sudo`, `curl | bash`, etc.) and shell injection patterns.
- **Command execution** — `run_command` uses `spawn` with `shell: false` on Linux/macOS and `shell: true` on Windows (required for `.cmd` scripts). The blocklist guards against injection when `shell: true` is active.

Do not expose `OPENROUTER_API_KEY` in logs, commits, or public repositories.

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `Cannot find package 'chalk'` | Run `setup.bat` or `npm install` — `node_modules` is missing |
| `node_modules` path error with spaces in directory | Ensure you are running from the project root where `package.json` exists |
| `npm install` fails during setup | Check your internet connection and firewall/proxy settings |
| LLM repeatedly fails to install | The project may require manual intervention; check the agent's tool call history |
| `OPENROUTER_API_KEY not set` | Create a `.env` file in the project root with `OPENROUTER_API_KEY=<your-key>` |
| Python download fails | Ensure `curl` or `wget` is available on Linux/macOS, or PowerShell is available on Windows |

## FAQ

**Does this require git to be installed?**
No. The tool downloads repositories as ZIP archives via HTTPS. Git is never required.

**Where are installed projects stored?**
In `./installations/{repo-name}/` relative to the gitinstaller project root.

**Can I use a different LLM model?**
The model is hardcoded to `xiaomi/mimo-v2-flash` in `src/llm.js`. You can edit this file to use any model available on OpenRouter.

**What happens if the LLM makes a mistake?**
The tool has a 40-call cap and a 5-minute command timeout. If the agent enters a loop or the install fails, it will stop and report the issue. The installed project directory can be safely deleted and retried.

**Does this work offline?**
No. It requires internet access to download the repository ZIP, call the OpenRouter API, and (for Python projects) download portable Python.

## Accessibility and Localization

The terminal output uses ANSI color codes via `chalk`. If your terminal does not support ANSI colors, the output remains readable — colors are used for emphasis only, not to convey critical information.

The tool currently supports English output only. Localization contributions are welcome.

## Changelog

### v1.0.0 — Initial Release

- LLM-powered agentic installation loop
- Portable Node.js and Python auto-download
- GPU detection (NVIDIA `nvidia-smi`, AMD `rocm-smi`)
- Auto WebUI generation with Gradio
- Path sandboxing and command blocklist
- Windows, Linux, and macOS support

## Roadmap

- [ ] Support for additional repository hosting platforms (GitLab, Bitbucket)
- [ ] Configurable LLM model selection via CLI flag
- [ ] Parallel installation of multiple repositories
- [ ] Dry-run mode (analyze without installing)
- [ ] Exportable installation logs

## Support

- **Issues:** [github.com/arjun-arihant/gitinstaller/issues](https://github.com/arjun-arihant/gitinstaller/issues)

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.