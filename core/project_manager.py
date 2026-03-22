"""
core/project_manager.py — Reads/writes projects.json, manages install state, config, and plan cache
"""

import os
import json
from datetime import datetime

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(APP_DIR, "data")
PROJECTS_FILE = os.path.join(DATA_DIR, "projects.json")
CONFIG_FILE = os.path.join(DATA_DIR, "config.json")
PLANS_DIR = os.path.join(DATA_DIR, "plans")


def _read_json(filepath, default):
    if not os.path.isfile(filepath):
        return default.copy() if isinstance(default, dict) else default
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return default.copy() if isinstance(default, dict) else default


def _write_json(filepath, data):
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


# --- Project Registry ---

def get_all_projects():
    data = _read_json(PROJECTS_FILE, {"projects": []})
    return data.get("projects", [])


def add_project(metadata):
    data = _read_json(PROJECTS_FILE, {"projects": []})
    projects = data.get("projects", [])
    projects = [p for p in projects if p.get("id") != metadata.get("id")]
    projects.append(metadata)
    data["projects"] = projects
    _write_json(PROJECTS_FILE, data)


def update_project_status(project_id, status, failed_at_step=None):
    data = _read_json(PROJECTS_FILE, {"projects": []})
    for project in data.get("projects", []):
        if project.get("id") == project_id:
            project["status"] = status
            if failed_at_step is not None:
                project["failed_at_step"] = failed_at_step
            elif "failed_at_step" in project:
                del project["failed_at_step"]
            break
    _write_json(PROJECTS_FILE, data)


def update_project_field(project_id, field, value):
    data = _read_json(PROJECTS_FILE, {"projects": []})
    for project in data.get("projects", []):
        if project.get("id") == project_id:
            project[field] = value
            break
    _write_json(PROJECTS_FILE, data)


def remove_project(project_id):
    data = _read_json(PROJECTS_FILE, {"projects": []})
    data["projects"] = [
        p for p in data.get("projects", []) if p.get("id") != project_id
    ]
    _write_json(PROJECTS_FILE, data)


# --- Config ---

def _read_config():
    return _read_json(CONFIG_FILE, {
        "last_install_path": None,
        "theme": "dark",
    })


def _write_config(config):
    _write_json(CONFIG_FILE, config)


def get_install_path():
    config = _read_config()
    path = config.get("last_install_path")
    if path:
        return path
    return os.path.join(os.path.expanduser("~"), "GitInstaller")


def set_install_path(path):
    config = _read_config()
    config["last_install_path"] = path
    _write_config(config)


def get_theme():
    config = _read_config()
    return config.get("theme", "dark")


def set_theme(theme):
    config = _read_config()
    config["theme"] = theme
    _write_config(config)


# --- API Key (in .env) ---

def get_api_key():
    try:
        import dotenv
        env_path = os.path.join(APP_DIR, ".env")
        dotenv.load_dotenv(env_path)
        return os.environ.get("OPENROUTER_API_KEY", "")
    except ImportError:
        config = _read_config()
        return config.get("openrouter_api_key", "")


def set_api_key(key):
    try:
        import dotenv
        env_path = os.path.join(APP_DIR, ".env")
        if not os.path.exists(env_path):
            open(env_path, 'a').close()
        dotenv.set_key(env_path, "OPENROUTER_API_KEY", key)
        os.environ["OPENROUTER_API_KEY"] = key
    except ImportError:
        pass


# --- GitHub Token (in .env) ---

def get_github_token():
    try:
        import dotenv
        env_path = os.path.join(APP_DIR, ".env")
        dotenv.load_dotenv(env_path)
        return os.environ.get("GITHUB_TOKEN", "")
    except ImportError:
        return ""


def set_github_token(token):
    try:
        import dotenv
        env_path = os.path.join(APP_DIR, ".env")
        if not os.path.exists(env_path):
            open(env_path, 'a').close()
        dotenv.set_key(env_path, "GITHUB_TOKEN", token)
        os.environ["GITHUB_TOKEN"] = token
    except ImportError:
        pass


# --- Plan Cache ---

def save_plan(project_id, plan):
    os.makedirs(PLANS_DIR, exist_ok=True)
    plan_data = {
        "plan": plan,
        "cached_at": datetime.now().isoformat(),
    }
    filepath = os.path.join(PLANS_DIR, f"{project_id}.json")
    _write_json(filepath, plan_data)


def load_plan(project_id):
    filepath = os.path.join(PLANS_DIR, f"{project_id}.json")
    if not os.path.isfile(filepath):
        return None
    data = _read_json(filepath, {})
    if data and "plan" in data:
        return data
    return None
