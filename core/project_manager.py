"""
core/project_manager.py — Manages persistent application state.

Handles:
- Project registry (``projects.json``): installed project metadata
- User configuration (``config.json``): install path, theme
- API credentials (``.env`` via python-dotenv, with config.json fallback)
- AI plan cache (``data/plans/``)
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path

from core.models import InstallationPlan
from core.paths import get_app_dir, get_data_dir

logger = logging.getLogger(__name__)

DATA_DIR = get_data_dir()
PROJECTS_FILE = os.path.join(DATA_DIR, "projects.json")
CONFIG_FILE = os.path.join(DATA_DIR, "config.json")
PLANS_DIR = os.path.join(DATA_DIR, "plans")


# ---------------------------------------------------------------------------
# JSON Helpers
# ---------------------------------------------------------------------------

def _read_json(filepath: str, default: dict | list) -> dict | list:
    """Read and parse a JSON file, returning *default* on any failure.

    Args:
        filepath: Absolute path to the JSON file.
        default: Value to return if the file is missing or unparseable.
    """
    if not os.path.isfile(filepath):
        return default.copy() if isinstance(default, dict) else list(default)
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as exc:
        logger.warning("Failed to read %s: %s", filepath, exc)
        return default.copy() if isinstance(default, dict) else list(default)


def _write_json(filepath: str, data: dict | list) -> None:
    """Atomically write *data* as pretty-printed JSON.

    Args:
        filepath: Absolute path to the target file.
        data: Serialisable data to write.
    """
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Project Registry
# ---------------------------------------------------------------------------

def get_all_projects() -> list[dict]:
    """Return the list of all registered projects."""
    data = _read_json(PROJECTS_FILE, {"projects": []})
    if isinstance(data, dict):
        return data.get("projects", [])
    return []


def add_project(metadata: dict) -> None:
    """Add or replace a project in the registry.

    If a project with the same ``id`` already exists it is replaced.

    Args:
        metadata: Project metadata dict (must contain an ``id`` key).
    """
    data = _read_json(PROJECTS_FILE, {"projects": []})
    if not isinstance(data, dict):
        data = {"projects": []}
    projects: list[dict] = data.get("projects", [])
    projects = [p for p in projects if p.get("id") != metadata.get("id")]
    projects.append(metadata)
    data["projects"] = projects
    _write_json(PROJECTS_FILE, data)


def update_project_status(
    project_id: str,
    status: str,
    failed_at_step: int | None = None,
) -> None:
    """Update the status of a registered project.

    Args:
        project_id: The project identifier.
        status: New status string (e.g. ``"installed"``, ``"partial"``).
        failed_at_step: Optional step id where failure occurred.
    """
    data = _read_json(PROJECTS_FILE, {"projects": []})
    if not isinstance(data, dict):
        return
    for project in data.get("projects", []):
        if project.get("id") == project_id:
            project["status"] = status
            if failed_at_step is not None:
                project["failed_at_step"] = failed_at_step
            elif "failed_at_step" in project:
                del project["failed_at_step"]
            break
    _write_json(PROJECTS_FILE, data)


def update_project_field(project_id: str, field: str, value: object) -> None:
    """Update a single field on a registered project.

    Args:
        project_id: The project identifier.
        field: The field name to set.
        value: The new value.
    """
    data = _read_json(PROJECTS_FILE, {"projects": []})
    if not isinstance(data, dict):
        return
    for project in data.get("projects", []):
        if project.get("id") == project_id:
            project[field] = value
            break
    _write_json(PROJECTS_FILE, data)


def remove_project(project_id: str) -> None:
    """Remove a project from the registry by id.

    Args:
        project_id: The project identifier to remove.
    """
    data = _read_json(PROJECTS_FILE, {"projects": []})
    if not isinstance(data, dict):
        return
    data["projects"] = [
        p for p in data.get("projects", []) if p.get("id") != project_id
    ]
    _write_json(PROJECTS_FILE, data)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def _read_config() -> dict:
    """Read the application configuration file."""
    data = _read_json(CONFIG_FILE, {
        "last_install_path": None,
        "theme": "dark",
    })
    return data if isinstance(data, dict) else {"last_install_path": None, "theme": "dark"}


def _write_config(config: dict) -> None:
    """Write the application configuration file."""
    _write_json(CONFIG_FILE, config)


def get_install_path() -> str:
    """Return the last-used install path, or a sensible default."""
    config = _read_config()
    path = config.get("last_install_path")
    if path:
        return str(path)
    return os.path.join(os.path.expanduser("~"), "GitInstaller")


def set_install_path(path: str) -> None:
    """Persist the install path to config.

    Args:
        path: Absolute path to the install directory.
    """
    config = _read_config()
    config["last_install_path"] = path
    _write_config(config)


def get_theme() -> str:
    """Return the current UI theme name (``"dark"`` or ``"light"``)."""
    config = _read_config()
    return str(config.get("theme", "dark"))


def set_theme(theme: str) -> None:
    """Persist the UI theme preference.

    Args:
        theme: Theme name (``"dark"`` or ``"light"``).
    """
    config = _read_config()
    config["theme"] = theme
    _write_config(config)


# ---------------------------------------------------------------------------
# API Key (stored in .env via python-dotenv, with config.json fallback)
# ---------------------------------------------------------------------------

def _get_env_path() -> str:
    """Return the path to the ``.env`` file next to the application."""
    return os.path.join(get_app_dir(), ".env")


def get_api_key() -> str:
    """Return the OpenRouter API key, or an empty string if not set."""
    try:
        import dotenv
        dotenv.load_dotenv(_get_env_path())
        return os.environ.get("OPENROUTER_API_KEY", "")
    except ImportError:
        logger.debug("python-dotenv not available, falling back to config.json")
        config = _read_config()
        return str(config.get("openrouter_api_key", ""))


def set_api_key(key: str) -> None:
    """Persist the OpenRouter API key.

    Tries ``.env`` via python-dotenv first; falls back to ``config.json``.

    Args:
        key: The API key string.
    """
    try:
        import dotenv
        env_path = _get_env_path()
        Path(env_path).touch(exist_ok=True)
        dotenv.set_key(env_path, "OPENROUTER_API_KEY", key)
        os.environ["OPENROUTER_API_KEY"] = key
    except ImportError:
        logger.debug("python-dotenv not available, saving API key to config.json")
        config = _read_config()
        config["openrouter_api_key"] = key
        _write_config(config)


# ---------------------------------------------------------------------------
# GitHub Token (stored in .env via python-dotenv, with config.json fallback)
# ---------------------------------------------------------------------------

def get_github_token() -> str:
    """Return the GitHub personal access token, or an empty string if not set."""
    try:
        import dotenv
        dotenv.load_dotenv(_get_env_path())
        return os.environ.get("GITHUB_TOKEN", "")
    except ImportError:
        logger.debug("python-dotenv not available, falling back to config.json")
        config = _read_config()
        return str(config.get("github_token", ""))


def set_github_token(token: str) -> None:
    """Persist the GitHub personal access token.

    Tries ``.env`` via python-dotenv first; falls back to ``config.json``.

    Args:
        token: The GitHub token string.
    """
    try:
        import dotenv
        env_path = _get_env_path()
        Path(env_path).touch(exist_ok=True)
        dotenv.set_key(env_path, "GITHUB_TOKEN", token)
        os.environ["GITHUB_TOKEN"] = token
    except ImportError:
        logger.debug("python-dotenv not available, saving GitHub token to config.json")
        config = _read_config()
        config["github_token"] = token
        _write_config(config)


# ---------------------------------------------------------------------------
# Plan Cache
# ---------------------------------------------------------------------------

def save_plan(project_id: str, plan: InstallationPlan) -> None:
    """Cache an AI-generated installation plan to disk.

    Args:
        project_id: The project identifier (used as filename).
        plan: The plan dict to cache.
    """
    os.makedirs(PLANS_DIR, exist_ok=True)
    plan_data = {
        "plan": plan,
        "cached_at": datetime.now().isoformat(),
    }
    filepath = os.path.join(PLANS_DIR, f"{project_id}.json")
    _write_json(filepath, plan_data)


def load_plan(project_id: str) -> dict | None:
    """Load a cached installation plan from disk.

    Args:
        project_id: The project identifier.

    Returns:
        The cached plan data dict, or ``None`` if not found.
    """
    filepath = os.path.join(PLANS_DIR, f"{project_id}.json")
    if not os.path.isfile(filepath):
        return None
    data = _read_json(filepath, {})
    if isinstance(data, dict) and "plan" in data:
        return data
    return None
