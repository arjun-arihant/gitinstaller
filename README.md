<div align="center">

<img src="https://raw.githubusercontent.com/arjun-arihant/gitinstaller/main/frontend/icon.png" width="100" />

# GitInstaller

**Turn any GitHub repo into a one-click desktop app — no terminal required.**

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Build & Release](https://github.com/arjun-arihant/gitinstaller/actions/workflows/build.yml/badge.svg)](https://github.com/arjun-arihant/gitinstaller/actions/workflows/build.yml)

</div>

GitInstaller is a standalone desktop application that lets anyone install and run open-source projects from GitHub — without ever opening a terminal. It uses AI to analyze a repository, generate a step-by-step installation plan, create an isolated environment, install all dependencies, and optionally build a Gradio Web UI so you can interact with the project through your browser.

Everything runs locally. Git, Python, and Node.js are bundled directly into the executable, so there is nothing else to install.

---

## Download

Go to the [**Releases**](https://github.com/arjun-arihant/gitinstaller/releases) page and download the archive for your operating system:

| OS | File | Notes |
|---|---|---|
| Windows | `GitInstaller-Windows.zip` | Extract folder and run `GitInstaller.exe` |
| macOS | `GitInstaller-macOS.zip` | Extract and see [macOS instructions](#macos-unsigned-app) below |
| Linux | `GitInstaller-Linux.tar.gz` | Extract, `chmod +x GitInstaller`, then run |

### macOS Unsigned App

macOS blocks applications from unidentified developers by default. To run GitInstaller:

1. Download `GitInstaller-macOS.zip` from the Releases page and extract it.
2. Open **Terminal** and navigate to where you extracted the app (`GitInstaller-macOS.app`):
   ```bash
   cd ~/Downloads
   ```
3. Remove the quarantine attribute and make it executable:
   ```bash
   xattr -cr GitInstaller-macOS.app
   ```
4. Run the app:
   ```bash
   open GitInstaller-macOS.app
   ```

Alternatively, if you try to open it by double-clicking and see *"GitInstaller-macOS cannot be opened because it is from an unidentified developer"*, go to **System Settings → Privacy & Security**, scroll down, and click **Open Anyway**.

---

## Getting Started

### 1. Set Up API Keys

On first launch, open **Settings** and add:

- **OpenRouter API Key** — required for AI-powered repository analysis and WebUI generation. Get one at [openrouter.ai](https://openrouter.ai/).
- **GitHub Token** *(optional)* — needed for private repositories and to avoid GitHub API rate limits. Generate one at [github.com/settings/tokens](https://github.com/settings/tokens) with `repo` scope.

> Your GitHub token is stored locally and is **never** sent to the AI model.

### 2. Install a Project

1. Paste a GitHub URL (e.g. `https://github.com/user/repo`) or shorthand (`user/repo`).
2. Click **Install to GitInstaller**.
3. Review the AI-generated installation plan — edit, skip, or reorder steps if needed.
4. Click **Start Execution**. GitInstaller clones the repo, creates an isolated environment, and installs all dependencies.
5. Once complete, click **Launch** or **Launch WebUI** to start the project.
6. Manage installed projects from the list — launch, open folder, update (`git pull`), or uninstall.

---

## How It Works

```
GitHub URL → Fetch Repo Data → AI Analysis → Installation Plan → Review & Approve → Execute → Launch
```

1. **Fetch** — Pulls repository metadata, README, and config files from the GitHub API.
2. **Analyze** — Sends the repo structure to an OpenRouter-hosted model that generates a tailored installation plan (clone, create venv, install deps, configure env, etc.).
3. **Review** — You see every step before anything runs. Edit commands, skip steps, or re-analyze.
4. **Execute** — Runs each step in sequence using the bundled runtimes — no system dependencies needed.
5. **WebUI** — For Python projects without a web interface, GitInstaller generates a Gradio UI so you can interact with the project from your browser.

---

## Features

- **Zero dependencies** — Git, Python, and Node.js are bundled into the executable. Nothing else to install.
- **AI-powered plans** — Understands undocumented repos and produces correct, executable installation steps.
- **Plan review** — Inspect, edit, skip, or cancel steps before and during execution.
- **Project management** — Easily uninstall projects or update them to the latest version (`git pull`).
- **Auto-generated Web UIs** — Creates Gradio interfaces for Python projects that lack a web frontend.
- **Private repo support** — Clone and analyze private GitHub repositories with a personal access token.
- **Isolated environments** — Each project gets its own virtual environment — no system pollution.
- **Plan caching & Progress** — Reuses cached plans to save API calls, and saves progress so installs can be resumed.
- **Robust execution** — Terminal auto-scroll pinning and confirmation dialogs for safe operations.
- **Cross-platform** — Runs on Windows, macOS, and Linux with native look and feel.
- **System tray** — Minimize to tray and keep the app running in the background.
- **Theming** — All generated Web UIs follow the `data/design.md` visual spec for consistent styling.

---

## Development

### Prerequisites

- Python 3.11+
- [pyright](https://github.com/microsoft/pyright) for type checking

### Setup

```bash
git clone https://github.com/arjun-arihant/gitinstaller.git
cd gitinstaller
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### Run

```bash
python app.py
```

### Type Check

```bash
pyright
```

### Build

Cross-platform executables are built automatically via GitHub Actions on every tag push (`v*`). See [`.github/workflows/build.yml`](.github/workflows/build.yml) for the full PyInstaller configuration.

---

## Project Structure

```
app.py                  # Entry point — pywebview API exposed to frontend
core/
├── models.py           # TypedDict definitions (InstallationPlan, RepoData, PlanStep)
├── paths.py            # Path resolution for dev and PyInstaller frozen builds
├── platform_utils.py   # Cross-platform abstractions (OS detection, job objects, env)
├── executor.py         # Step-by-step subprocess execution with cancel/retry/skip
├── github_fetcher.py   # GitHub API client (repo metadata, README, file contents)
├── claude_analyzer.py  # AI analysis via OpenRouter + strict schema validation
├── project_manager.py  # Thread-safe persistent state (atomic file writes)
├── launcher_gen.py     # Launch script generator (.bat / .sh)
├── webui_gen.py        # Gradio WebUI generator with design.md theming
├── utils.py            # Shared utils (e.g. GitHub URL parsing)
└── version.py          # Centralized application version
frontend/               # HTML / CSS / JS served by pywebview
data/
├── design.md           # WebUI visual design spec (drop-in replaceable)
└── plans/              # Cached AI-generated installation plans
bundled/                # Portable runtimes (python/, node/, git/) — auto-detected
```

---

## License

[MIT](LICENSE)
