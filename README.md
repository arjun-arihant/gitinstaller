<div align="center">

<img src="https://raw.githubusercontent.com/arjun-arihant/gitinstaller/main/frontend/icon.png" width="100" />

# GitInstaller

**The easiest way to run AI-generated web interfaces for any open-source project.**

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Build & Release](https://github.com/arjun-arihant/gitinstaller/actions/workflows/build.yml/badge.svg)](https://github.com/arjun-arihant/gitinstaller/actions/workflows/build.yml)

</div>

GitInstaller bridges the gap between complex open-source repositories and non-technical users. It automatically clones repositories, analyzes their architecture using Claude AI, sets up necessary virtual environments, installs dependencies, and generates a fully functional **Gradio Web UI** tailored exactly to that project's specific needs.

## 🚀 Quick Start

Get running in less than 5 minutes.

### 1. Download the App
Download the latest standalone executable for your operating system (Windows, macOS, or Linux) from the [Releases page](https://github.com/arjun-arihant/gitinstaller/releases).

### 2. Configure API Keys
When you launch the app for the first time, you'll need to provide an **OpenRouter API Key** (for Claude 3.5 Sonnet analysis) and a **GitHub Personal Access Token** (for fetching private repositories and avoiding rate limits).

### 3. Install a Project
1. Paste a GitHub URL (e.g., `https://github.com/user/repo`).
2. Click **Install to GitInstaller**.
3. Review the AI-generated execution plan. You can edit, retry, or skip steps as needed.
4. Click **Start Execution**. Grab a coffee while GitInstaller handles cloning, environments, and dependencies.
5. Once complete, click **Launch WebUI** to interact with the project!

---

## ✨ Key Features

- **🧠 Auto-Generated Web UIs**: Uses Claude 3.5 Sonnet to understand undocumented repos and generate standard Python Gradio interfaces.
- **⚡ Portable Architecture**: Create isolated virtual environments for every project. Optionally drop portable `python/`, `node/`, and `git/` folders into `bundled/` to avoid polluting your system.
- **🎨 Universal Theming**: All generated Web UIs strictly follow the `data/design.md` visual guidelines for a cohesive, branded experience.
- **🔄 Interactive Planning**: Review, modify, or cancel the AI's step-by-step installation plan before running it.
- **🍎 Cross-Platform**: Natively runs on Windows, macOS, and Linux with full system tray integration.
- **🔒 Private Repo Support**: Seamlessly clone and analyze private GitHub repositories.

---

## 🛠 Developer Guide

Are you an AI agent or a developer looking to contribute to GitInstaller? Here are the rules of the road.

### Core Commands

Make sure you have Python 3.11+ installed.

```bash
# Clone the repository
git clone https://github.com/arjun-arihant/gitinstaller.git
cd gitinstaller

# Create virtual environment and install dependencies
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Run the application locally
python app.py
```

### Type Checking & Linting

We enforce strict type checking across the codebase.

```bash
# Run the pyright type checker (configured in pyrightconfig.json)
pyright
```

### Building the Executables

We use PyInstaller to build cross-platform binaries. This is fully automated via GitHub Actions on every tag push (see `.github/workflows/build.yml`). If you need to build locally, look at the exact pyinstaller flags used in the workflow file.

---

## 🏗 Architecture & Patterns

When modifying the codebase, adhere to these project-specific structural patterns (documented in `AGENTS.md`):

### Theming System
- **`data/design.md`**: This is the drop-in replaceable design spec. All generated Gradio WebUIs pull their theme values from here. Swap this file out to instantly change the appearance of all future generated interfaces.

### State & Caching
- **AI Plan Caching**: Project plans are cached in the `data/plans/` directory to save API costs. Delete a plan file to force re-analysis.
- **App State Files**: User configurations and the installed project registry are stored locally in `data/config.json` and `data/projects.json` (these are `.gitignore`d).

### Runtimes
- **Bundled Runtimes**: To make GitInstaller fully portable, you can place portable runtime binaries in `bundled/python/`, `bundled/git/`, and `bundled/node/`. The app will automatically prefer these over system PATH bins.

### Core Modules
- **`app.py`**: The main entry point. Exposes a Python API to JavaScript via `pywebview`.
- **`core/platform_utils.py`**: Handles cross-platform abstractions (OS detection, appropriate script generation `.bat` vs `.sh`, venv pathing).
- **`core/executor.py`**: Manages subprocess execution. On Windows, it binds spawned child processes to job objects to ensure proper process tree termination.
- **Custom Exceptions**: Always use the defined domain exceptions (e.g., `RepoNotFoundError`, `GitHubRateLimitError`) rather than generic exceptions.

---

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.
