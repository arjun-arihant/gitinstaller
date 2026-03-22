"""
core/paths.py — Centralized path resolution for both development and PyInstaller frozen builds.

In development mode, all paths resolve relative to the project root (parent of this file's directory).
In PyInstaller --onefile mode:
  - Read-only bundled resources (frontend/, data/design.md, core/) are extracted to a temp dir (sys._MEIPASS).
  - Writable state files (config.json, projects.json, plans/) and user-provided bundled runtimes
    resolve relative to the directory where the executable actually lives.
"""

from __future__ import annotations

import os
import sys


def is_frozen() -> bool:
    """Return True if running inside a PyInstaller bundle (--onefile or --onedir)."""
    return getattr(sys, "frozen", False)


def is_onefile() -> bool:
    """Return True if running a PyInstaller --onefile bundle.

    In onefile mode, bundled resources are extracted to a temp directory
    (``sys._MEIPASS``) and the executable lives in a separate directory.
    In onedir mode, the executable lives next to the bundled resources.
    """
    return is_frozen() and hasattr(sys, "_MEIPASS")


def get_app_dir() -> str:
    """Return the application root directory.

    In development: the project root (parent of the ``core/`` package).
    In frozen mode: the directory containing the executable.
    """
    if is_frozen():
        # sys.executable is the path to the .exe
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def get_resource_dir() -> str:
    """Return the directory containing read-only bundled resources.

    In development: same as ``get_app_dir()``.
    In frozen mode: the PyInstaller extraction directory (``sys._MEIPASS``).
    """
    if is_frozen():
        return getattr(sys, "_MEIPASS", get_app_dir())
    return get_app_dir()


def get_data_dir() -> str:
    """Return the writable ``data/`` directory for config, projects, and plan cache.

    Always resolves relative to ``get_app_dir()`` so that state persists across runs.
    Creates the directory if it does not exist.
    """
    data_dir = os.path.join(get_app_dir(), "data")
    os.makedirs(data_dir, exist_ok=True)
    return data_dir


def get_design_spec_path() -> str:
    """Return the path to ``data/design.md``.

    In frozen mode this is inside the extraction directory (read-only).
    In development mode it is in the project ``data/`` folder.
    """
    return os.path.join(get_resource_dir(), "data", "design.md")


def get_frontend_dir() -> str:
    """Return the path to the ``frontend/`` directory containing HTML/CSS/JS.

    In frozen mode this is inside the extraction directory.
    """
    return os.path.join(get_resource_dir(), "frontend")


def get_bundled_dir() -> str:
    """Return the ``bundled/`` directory where portable runtimes may be placed.

    Always resolves relative to ``get_app_dir()`` (next to the executable),
    since users place runtimes there after installation.
    """
    return os.path.join(get_app_dir(), "bundled")
