"""
core/project_manager.py — Manages persistent application state.

Handles:
- Project registry (``projects.json``): installed project metadata
- User configuration (``config.json``): install path, theme
- API credentials (``.env`` via python-dotenv)
- AI plan cache (``data/plans/``)
- Installation progress persistence (``data/plans/{id}_progress.json``)
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
from datetime import datetime
from pathlib import Path

from core.models import InstallationPlan
from core.paths import get_app_dir, get_data_dir

logger = logging.getLogger(__name__)

DATA_DIR = get_data_dir()
PROJECTS_FILE = os.path.join(DATA_DIR, "projects.json")
CONFIG_FILE = os.path.join(DATA_DIR, "config.json")
PLANS_DIR = os.path.join(DATA_DIR, "plans")

# Module-level lock protecting all file I/O so concurrent threads can't corrupt data
_file_lock = threading.Lock()


# ---------------------------------------------------------------------------
# JSON Helpers (always called under _file_lock)
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
    """Atomically write *data* as pretty-printed JSON via temp-file rename.

    Using ``os.replace`` ensures the write is atomic: the file is either
    fully written or untouched, never corrupted mid-write.

    Args:
        filepath: Absolute path to the target file.
        data: Serialisable data to write.
    """
    dirpath = os.path.dirname(filepath)
    os.makedirs(dirpath, exist_ok=True)

    # Write to a temp file in the same directory so os.replace is atomic
    fd, tmp_path = tempfile.mkstemp(dir=dirpath, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        os.replace(tmp_path, filepath)
    except Exception:
        # Clean up temp file on failure
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


# ---------------------------------------------------------------------------
# Project Registry
# ---------------------------------------------------------------------------

def get_all_projects() -> list[dict]:
    """Return the list of all registered projects."""
    with _file_lock:
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
    with _file_lock:
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
    with _file_lock:
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
    with _file_lock:
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
    with _file_lock:
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
    with _file_lock:
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
    with _file_lock:
        config = _read_config()
        config["last_install_path"] = path
        _write_config(config)


def get_theme() -> str:
    """Return the current UI theme name (``"dark"`` or ``"light"``)."""
    with _file_lock:
        config = _read_config()
    return str(config.get("theme", "dark"))


def set_theme(theme: str) -> None:
    """Persist the UI theme preference.

    Args:
        theme: Theme name (``"dark"`` or ``"light"``).
    """
    with _file_lock:
        config = _read_config()
        config["theme"] = theme
        _write_config(config)


# ---------------------------------------------------------------------------
# API Key (stored in .env via python-dotenv — no config.json fallback)
# ---------------------------------------------------------------------------

def _get_env_path() -> str:
    """Return the path to the ``.env`` file next to the application."""
    return os.path.join(get_app_dir(), ".env")


def get_api_key() -> str:
    """Return the OpenRouter API key, or an empty string if not set."""
    import dotenv
    dotenv.load_dotenv(_get_env_path(), override=True)
    return os.environ.get("OPENROUTER_API_KEY", "")


def set_api_key(key: str) -> None:
    """Persist the OpenRouter API key to the ``.env`` file.

    Args:
        key: The API key string.
    """
    import dotenv
    env_path = _get_env_path()
    Path(env_path).touch(exist_ok=True)
    dotenv.set_key(env_path, "OPENROUTER_API_KEY", key)
    os.environ["OPENROUTER_API_KEY"] = key


# ---------------------------------------------------------------------------
# GitHub Token (stored in .env via python-dotenv)
# ---------------------------------------------------------------------------

def get_github_token() -> str:
    """Return the GitHub personal access token, or an empty string if not set."""
    import dotenv
    dotenv.load_dotenv(_get_env_path(), override=True)
    return os.environ.get("GITHUB_TOKEN", "")


def set_github_token(token: str) -> None:
    """Persist the GitHub personal access token to the ``.env`` file.

    Args:
        token: The GitHub token string.
    """
    import dotenv
    env_path = _get_env_path()
    Path(env_path).touch(exist_ok=True)
    dotenv.set_key(env_path, "GITHUB_TOKEN", token)
    os.environ["GITHUB_TOKEN"] = token


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
    with _file_lock:
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
    with _file_lock:
        data = _read_json(filepath, {})
    if isinstance(data, dict) and "plan" in data:
        return data
    return None


def clear_plan(project_id: str) -> None:
    """Remove a cached plan from disk.

    Args:
        project_id: The project identifier.
    """
    filepath = os.path.join(PLANS_DIR, f"{project_id}.json")
    with _file_lock:
        if os.path.isfile(filepath):
            try:
                os.unlink(filepath)
            except OSError as exc:
                logger.warning("Failed to delete plan cache %s: %s", filepath, exc)


# ---------------------------------------------------------------------------
# Installation Progress Persistence
# ---------------------------------------------------------------------------

def save_progress(project_id: str, last_completed_step: int) -> None:
    """Persist the last successfully completed installation step.

    Called after each step completes so the installation can be resumed
    after a crash or forced close.

    Args:
        project_id: The project identifier.
        last_completed_step: The ``id`` of the last step that completed successfully.
    """
    os.makedirs(PLANS_DIR, exist_ok=True)
    progress_data = {
        "last_completed_step": last_completed_step,
        "saved_at": datetime.now().isoformat(),
    }
    filepath = os.path.join(PLANS_DIR, f"{project_id}_progress.json")
    with _file_lock:
        _write_json(filepath, progress_data)


def load_progress(project_id: str) -> int | None:
    """Load the last completed step for a project installation.

    Args:
        project_id: The project identifier.

    Returns:
        The step id of the last completed step, or ``None`` if no progress saved.
    """
    filepath = os.path.join(PLANS_DIR, f"{project_id}_progress.json")
    if not os.path.isfile(filepath):
        return None
    with _file_lock:
        data = _read_json(filepath, {})
    if isinstance(data, dict):
        val = data.get("last_completed_step")
        return int(val) if val is not None else None
    return None


def clear_progress(project_id: str) -> None:
    """Remove saved installation progress for a project.

    Args:
        project_id: The project identifier.
    """
    filepath = os.path.join(PLANS_DIR, f"{project_id}_progress.json")
    with _file_lock:
        if os.path.isfile(filepath):
            try:
                os.unlink(filepath)
            except OSError as exc:
                logger.warning("Failed to delete progress file %s: %s", filepath, exc)
