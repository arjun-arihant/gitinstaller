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

- **`app.py`** exposes a Python API to JavaScript via `pywebview`. The `API` class methods are callable from the frontend.
- **`core/platform_utils.py`** handles cross-platform abstractions (Windows/macOS/Linux detection, script extensions `.bat`/`.sh`, venv paths).
- **`core/executor.py`** manages subprocess execution with job objects on Windows for proper process tree termination.
- **Generated WebUIs** use Gradio with theme values from `data/design.md`.

## Code Style

- Uses **pyright** for type checking (configured for Python 3.11, Windows).
- Custom exceptions defined in each module (e.g., `RepoNotFoundError`, `GitHubRateLimitError`, `NetworkError`, `AnalysisError`).
- JSON files use 4-space indentation with `ensure_ascii=False`.
