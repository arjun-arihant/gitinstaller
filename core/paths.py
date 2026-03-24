"""
core/paths.py — Centralized path resolution for both development and PyInstaller frozen builds.

In development mode, all paths resolve relative to the project root (parent of this file's directory).
In PyInstaller --onefile mode:
  - Read-only bundled resources (frontend/, data/design.md, core/) are extracted to a temp dir (sys._MEIPASS).
  - Writable state files (config.json, projects.json, plans/) and user-provided bundled runtimes
    resolve relative to the directory where the executable actually lives.
"""

from __future__ import annotations

import logging
import os
import shutil
import sys

logger = logging.getLogger(__name__)


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
    """Return the ``bundled/`` directory for portable runtimes.

    Checks embedded location first (sys._MEIPASS), then falls back to
    external location (next to executable). This allows runtimes to be
    either bundled into the .exe or placed in a folder next to it.

    Returns:
        Path to the bundled/ directory.
    """
    # First check if bundled runtimes are embedded in the executable
    embedded = os.path.join(get_resource_dir(), "bundled")
    if os.path.isdir(embedded):
        return embedded
    # Fall back to external location (next to executable)
    return os.path.join(get_app_dir(), "bundled")


def get_bundled_python_path() -> str:
    """Locate the bundled Python executable, falling back to system Python.

    Returns:
        Absolute path to a usable Python interpreter.

    Raises:
        RuntimeError: If no Python interpreter can be found in a frozen build.
    """
    bundled_dir = get_bundled_dir()
    if sys.platform == "win32":
        bundled = os.path.join(bundled_dir, "python", "python.exe")
    else:
        bundled = os.path.join(bundled_dir, "python", "bin", "python3")

    if os.path.isfile(bundled):
        return bundled

    logger.warning("Bundled Python not found at %s, using system Python", bundled)

    if getattr(sys, "frozen", False):
        sys_python = shutil.which("python3") or shutil.which("python")
        if sys_python:
            return sys_python
        raise RuntimeError("Bundled Python not found, and system Python not found in PATH!")
    return sys.executable


def get_bundled_git_path() -> str:
    """Locate the bundled Git directory containing the ``git`` executable.

    Returns:
        Absolute path to the bundled Git executable directory, or empty string
        if not found.
    """
    git_base = os.path.join(get_bundled_dir(), "git")

    if sys.platform == "win32":
        # MinGit uses cmd/ for the main git.exe
        candidates = [
            os.path.join(git_base, "cmd"),
            os.path.join(git_base, "mingw64", "bin"),
            os.path.join(git_base, "bin"),
        ]
    else:
        candidates = [
            os.path.join(git_base, "bin"),
        ]

    for candidate in candidates:
        if os.path.isdir(candidate):
            return candidate

    logger.warning("Bundled Git not found under %s, using system Git", git_base)
    return ""


def get_bundled_node_path() -> str:
    """Locate the bundled Node.js directory, falling back to system Node.

    Returns:
        Absolute path to a Node.js directory, or empty string if not found.
    """
    bundled_dir = get_bundled_dir()
    if sys.platform == "win32":
        bundled = os.path.join(bundled_dir, "node")
    else:
        bundled = os.path.join(bundled_dir, "node", "bin")

    if os.path.isdir(bundled):
        return bundled

    # Fall back to system node
    node_path = shutil.which("node")
    if node_path:
        return os.path.dirname(node_path)
    return ""
