"""
core/project_manager.py — Reads/writes projects.json, manages install state and config
"""

import os
import json

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(APP_DIR, "data")
PROJECTS_FILE = os.path.join(DATA_DIR, "projects.json")
CONFIG_FILE = os.path.join(DATA_DIR, "config.json")


def _read_json(filepath: str, default: dict) -> dict:
    """Read a JSON file, returning default if it doesn't exist or is invalid."""
    if not os.path.isfile(filepath):
        return default.copy()
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return default.copy()


def _write_json(filepath: str, data: dict):
    """Write data to a JSON file."""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


# --- Project Registry ---

def get_all_projects() -> list:
    """Return all projects from registry."""
    data = _read_json(PROJECTS_FILE, {"projects": []})
    return data.get("projects", [])


def add_project(metadata: dict):
    """Add a new project entry, save to JSON."""
    data = _read_json(PROJECTS_FILE, {"projects": []})
    projects = data.get("projects", [])

    # Remove existing entry with the same id if present
    projects = [p for p in projects if p.get("id") != metadata.get("id")]
    projects.append(metadata)

    data["projects"] = projects
    _write_json(PROJECTS_FILE, data)


def update_project_status(project_id: str, status: str):
    """Update status field of a project."""
    data = _read_json(PROJECTS_FILE, {"projects": []})
    for project in data.get("projects", []):
        if project.get("id") == project_id:
            project["status"] = status
            break
    _write_json(PROJECTS_FILE, data)


def remove_project(project_id: str):
    """Remove a project from registry (does not delete files)."""
    data = _read_json(PROJECTS_FILE, {"projects": []})
    data["projects"] = [
        p for p in data.get("projects", []) if p.get("id") != project_id
    ]
    _write_json(PROJECTS_FILE, data)


# --- Config ---

def _read_config() -> dict:
    """Read config.json (for non-sensitive data)."""
    return _read_json(CONFIG_FILE, {
        "last_install_path": None,
    })


def _write_config(config: dict):
    """Write config.json."""
    _write_json(CONFIG_FILE, config)


def get_install_path() -> str:
    """Read last used install path from config.json, default to ~/GitInstaller."""
    config = _read_config()
    path = config.get("last_install_path")
    if path:
        return path
    return os.path.join(os.path.expanduser("~"), "GitInstaller")


def set_install_path(path: str):
    """Save install path to config.json."""
    config = _read_config()
    config["last_install_path"] = path
    _write_config(config)


def get_api_key():
    """Read OpenRouter API key from .env."""
    try:
        import dotenv
        env_path = os.path.join(APP_DIR, ".env")
        dotenv.load_dotenv(env_path)
        return os.environ.get("OPENROUTER_API_KEY", "")
    except ImportError:
        # Fallback to reading config if dotenv isn't installed during setup
        config = _read_config()
        return config.get("openrouter_api_key", "")


def set_api_key(key: str):
    """Save OpenRouter API key to .env."""
    try:
        import dotenv
        env_path = os.path.join(APP_DIR, ".env")
        if not os.path.exists(env_path):
            open(env_path, 'a').close()
        dotenv.set_key(env_path, "OPENROUTER_API_KEY", key)
        # We also set it in os.environ immediately so it's active
        os.environ["OPENROUTER_API_KEY"] = key
    except ImportError:
        pass
