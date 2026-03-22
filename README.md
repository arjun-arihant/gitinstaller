# GitInstaller

**GitInstaller** is a powerful desktop application built with Python and `pywebview` designed to fully automate the deployment of complex GitHub repositories. By reading repository documentation and leveraging advanced LLMs via OpenRouter, GitInstaller generates precise execution plans, safely creates virtual environments, installs dependencies, and automatically generates interactive Web UIs.

![GitInstaller](https://img.shields.io/badge/Status-Active-brightgreen) ![Python](https://img.shields.io/badge/Python-3.10%2B-blue)

## Features

- 🧠 **AI-Powered Execution Plans:** Connects to OpenRouter (defaulting to the highly efficient `MiMo-v2-flash` model) to read the target repository's `README.md` and `INSTALL.md`, extracting exact step-by-step shell commands.
- 🛡️ **Isolated Execution Environment:** Commands are run in a sequence via `subprocess` managed by Windows Job Objects (`core/executor.py`).
- 🐍 **Smart Environment Generation:** Automatically forces the strict creation of Python Virtual Environments (`venv`) to ensure dependencies are sandboxed.
- 🎨 **Automatic UI Generation:** By analyzing the project files (e.g. checking for `flask`, `streamlit`, `django`), if GitInstaller detects a CLI or library tool, it automatically leverages the LLM backend to draft and install a functional Gradio UI (`webui.py`).
- 🚀 **Click-to-Launch:** Automatically injects Windows batch scripts (`launch.bat` and `launch_webui.bat`) configured with localized `.venv\Scripts` `$PATH` settings for smooth developer handoff.

## Installation & Setup

1. **Clone the Repository:**
   ```bash
   git clone https://github.com/yourusername/GitInstaller.git
   cd GitInstaller
   ```

2. **Install Dependencies:**
   Ensure you have Python 3.10+ installed, then run:
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure API Keys:**
   - Copy `.env.example` to `.env` inside the root directory.
   - Insert your OpenRouter API Key into the `.env` file or configure it natively within the application Settings menu.

4. **Run the Application:**
   ```bash
   python app.py
   ```

## Standalone Deployment (Bundling Dependencies)

To protect installations from system Python namespace collisions, GitInstaller supports using bundled executables for completely isolated standalone execution:

1. **Python:** Download the Python Windows NuGet Package (e.g. 3.11.9) and extract its `tools/` folder contents directly into `bundled/python/`. The `core/executor.py` backend will prioritize this `python.exe` over system defaults to securely generate `venv`s.
2. **Git:** Download PortableGit for Windows and extract it into `bundled/git/`. GitInstaller will detect `bundled/git/bin/git.exe` in its sub-shell environment variables.

*Note: Bundled binaries are tracked under `.gitignore` to prevent tracking massive file blobs, however the shell directory structures are maintained by `.gitkeep`.*
