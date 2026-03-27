# GitInstaller

A CLI tool that takes a GitHub repo URL and installs it autonomously. An LLM agent analyzes the project, figures out what kind of repo it is, and installs all dependencies — no input required.

```
gitinstaller.bat install https://github.com/user/repo   (Windows)
./gitinstaller.sh install https://github.com/user/repo  (Linux/macOS)
```

## How It Works

1. Downloads the repo as a ZIP (no git required)
2. Downloads a bundled Python if the project needs it (no system Python required)
3. An LLM agent reads the project files, determines the project type, and installs dependencies
4. **Hardware-aware:** detects NVIDIA/AMD GPUs and installs the GPU-accelerated variant of dependencies when available (e.g. CUDA torch, requirements-gpu.txt)
5. **Auto WebUI:** if the project has no UI, generates a minimal `webui.py` using Gradio so you can interact with it immediately
6. Finishes with a summary of what was installed and how to run the project

The LLM decides what to do. The tool just executes. It handles Python projects (requirements.txt, pyproject.toml, setup.py), Node.js projects (package.json), and more.

## Quick Start — Works on a Brand New PC

### Windows (no prerequisites required)

```bat
git clone https://github.com/arjun-arihant/gitinstaller.git
cd gitinstaller
setup.bat
```

`setup.bat` automatically downloads a portable Node.js if it isn't installed, then installs npm dependencies. You only need to run it once.

Then create a `.env` file:
```
OPENROUTER_API_KEY=your-key-here
```

And run:
```bat
gitinstaller.bat install https://github.com/owner/repo
```

### Linux / macOS (no prerequisites required)

```bash
git clone https://github.com/arjun-arihant/gitinstaller.git
cd gitinstaller
chmod +x setup.sh gitinstaller.sh
./setup.sh
```

Then create a `.env` file:
```
OPENROUTER_API_KEY=your-key-here
```

And run:
```bash
./gitinstaller.sh install https://github.com/owner/repo
```

## If You Already Have Node.js Installed

You can still use the setup scripts (they'll skip the download), or use the classic workflow:

```bash
npm install
cp .env.example .env
# edit .env and set OPENROUTER_API_KEY
node index.js install https://github.com/owner/repo
```

## OpenRouter API Key

Get a free key at [openrouter.ai](https://openrouter.ai). The tool uses `xiaomi/mimo-v2-flash` which is one of the cheapest available models.

## What Gets Downloaded Automatically

| Dependency | When | Where Cached |
|---|---|---|
| Portable Node.js 22 LTS | On first `setup.bat`/`setup.sh` run if Node.js not in PATH | `.gitinstaller/node/` |
| Portable Python 3.12 | When installing a Python project | `.gitinstaller/python/` |

Both are cached after the first download. The `.gitinstaller/` directory is gitignored.

## Installed Projects

Projects land in `./installations/{repo-name}/`.

## Requirements

- **Windows:** Windows 10 or newer (PowerShell is used for the bootstrapper)
- **Linux/macOS:** `curl` or `wget` must be available (almost always pre-installed)
- No Node.js, Python, git, or other tools required — they are all handled automatically

## Constraints

- Max 40 LLM tool calls per install (prevents runaway loops)
- 5-minute timeout per command
- All operations stay inside the project directory — no writes outside it
- Blocked commands: `rm`, `sudo`, `curl | bash`, and other destructive patterns
