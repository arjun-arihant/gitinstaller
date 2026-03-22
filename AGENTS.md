# AGENTS.md

This file provides guidance to agents when working with code in this repository.

## Commands

- **Run app**: `python app.py`
- **Install deps**: `pip install -r requirements.txt`
- **Type check**: `pyright` (configured in `pyrightconfig.json`, Python 3.11)
- **Build executable**: See `.github/workflows/build.yml` for PyInstaller commands with OS-specific flags

## Project-Specific Patterns

- **`data/design.md`** is a drop-in replaceable design spec - all generated Gradio WebUIs use this theme. Swap the file to change all future generated WebUI appearances.
- **AI plan caching**: Plans are cached in `data/plans/` directory (gitignored). Remove this to force re-analysis.
- **Bundled runtimes**: Place portable Python/Git/Node in `bundled/python/`, `bundled/git/`, `bundled/node/` (directories are gitkeep'd but contents gitignored).
- **App state files** (`data/config.json`, `data/projects.json`) are gitignored - these store user config and installed project registry.

## Architecture

- **`app.py`** exposes a Python API to JavaScript via `pywebview`. The `API` class methods are callable from the frontend. Configures `logging` at startup.
- **`core/paths.py`** centralises all path resolution. Handles both development mode and PyInstaller `--onefile` frozen builds using `sys._MEIPASS` for read-only resources and the executable's directory for writable state.
- **`core/platform_utils.py`** handles cross-platform abstractions (Windows/macOS/Linux detection, script extensions `.bat`/`.sh`, venv paths).
- **`core/executor.py`** manages subprocess execution with job objects on Windows for proper process tree termination.
- **`core/utils.py`** contains shared utility functions (e.g. `strip_code_fences`) used across multiple modules.
- **Generated WebUIs** use Gradio with theme values from `data/design.md`.

## Path Resolution (Frozen vs Development)

All modules use `core/paths.py` for path resolution:
- **`get_app_dir()`** → executable's directory (frozen) or project root (dev)
- **`get_resource_dir()`** → `sys._MEIPASS` (frozen) or project root (dev) — for read-only bundled resources
- **`get_data_dir()`** → writable `data/` directory next to the executable
- **`get_bundled_dir()`** → `bundled/` directory next to the executable
- **`get_frontend_dir()`** → `frontend/` inside the resource directory
- **`get_design_spec_path()`** → `data/design.md` inside the resource directory

## Code Style

- Uses **pyright** for type checking (configured for Python 3.11, Windows).
- All functions have **type hints** on parameters and return types.
- All public functions have **Google-style docstrings**.
- Uses `from __future__ import annotations` for modern type hint syntax.
- Uses the **`logging`** module throughout (no `print()` for diagnostics).
- Custom exceptions defined in each module (e.g., `RepoNotFoundError`, `GitHubRateLimitError`, `NetworkError`, `AnalysisError`).
- JSON files use 4-space indentation with `ensure_ascii=False`.
- All string formatting uses **f-strings** consistently.
