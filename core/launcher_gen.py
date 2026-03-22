"""
core/launcher_gen.py — Generates cross-platform launch scripts for installed projects.

Creates ``.bat`` (Windows) or ``.sh`` (Unix) scripts that activate the project's
virtual environment and run the launch command.
"""

from __future__ import annotations

import os
import stat

from core.platform_utils import get_script_extension, get_venv_scripts_dir, is_windows


# ---------------------------------------------------------------------------
# Internal Helpers
# ---------------------------------------------------------------------------

def _clean_launch_command(command: str, project_dir: str) -> str:
    """Clean a launch command by resolving placeholders and stripping ``cd`` chains.

    Args:
        command: The raw launch command from the plan.
        project_dir: Absolute path to the project directory.

    Returns:
        The cleaned command string.
    """
    command = command.replace("{project_dir}", project_dir)
    if "&&" in command:
        parts = command.split("&&")
        cleaned = [p.strip() for p in parts if not p.strip().lower().startswith("cd ")]
        command = " && ".join(cleaned) if cleaned else command
    return command.strip()


def _make_executable(path: str) -> None:
    """Set the executable permission bit on a file (Unix only).

    Args:
        path: Absolute path to the file.
    """
    if not is_windows():
        st = os.stat(path)
        os.chmod(path, st.st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_launcher(project_dir: str, plan: dict) -> str:
    """Generate a launch script for an installed project.

    Creates a ``.bat`` or ``.sh`` script in the project directory that
    activates the venv (for Python projects) and runs the launch command.

    Args:
        project_dir: Absolute path to the project directory.
        plan: The installation plan dict.

    Returns:
        Absolute path to the generated launch script.
    """
    repo_name = os.path.basename(project_dir)
    launch_command = plan.get("launch_command", "echo No launch command configured")
    project_type = plan.get("project_type", "unknown")
    launch_command = _clean_launch_command(launch_command, project_dir)
    ext = get_script_extension()

    if is_windows():
        if project_type == "node":
            content = f"""@echo off
cd /d "%~dp0"
echo Starting {repo_name}...
{launch_command}
pause
"""
        else:
            content = f"""@echo off
cd /d "%~dp0"
call .venv\\Scripts\\activate.bat 2>nul
echo Starting {repo_name}...
{launch_command}
pause
"""
    else:
        if project_type == "node":
            content = f"""#!/bin/bash
cd "$(dirname "$0")"
echo "Starting {repo_name}..."
{launch_command}
"""
        else:
            content = f"""#!/bin/bash
cd "$(dirname "$0")"
source .venv/bin/activate 2>/dev/null
echo "Starting {repo_name}..."
{launch_command}
"""

    script_path = os.path.join(project_dir, f"launch{ext}")
    with open(script_path, "w", encoding="utf-8") as f:
        f.write(content)
    _make_executable(script_path)

    return script_path


def generate_webui_launcher(project_dir: str) -> str:
    """Generate a WebUI launch script for an installed project.

    Creates a ``.bat`` or ``.sh`` script that activates the venv and runs
    ``webui.py`` with browser auto-open instructions.

    Args:
        project_dir: Absolute path to the project directory.

    Returns:
        Absolute path to the generated WebUI launch script.
    """
    repo_name = os.path.basename(project_dir)
    ext = get_script_extension()
    scripts_dir = get_venv_scripts_dir()

    if is_windows():
        content = f"""@echo off
cd /d "%~dp0"
call .venv\\Scripts\\activate.bat 2>nul
echo Starting {repo_name} Web UI...
echo.
echo The WebUI will open in your browser automatically.
echo If it doesn't, visit: http://127.0.0.1:7860
echo.
.venv\\Scripts\\python.exe webui.py
pause
"""
    else:
        content = f"""#!/bin/bash
cd "$(dirname "$0")"
source .venv/bin/activate 2>/dev/null
echo "Starting {repo_name} Web UI..."
echo ""
echo "The WebUI will open in your browser automatically."
echo "If it doesn't, visit: http://127.0.0.1:7860"
echo ""
# Open browser after brief delay
(sleep 2 && python -m webbrowser http://127.0.0.1:7860) &
.venv/{scripts_dir}/python webui.py
"""

    script_path = os.path.join(project_dir, f"launch_webui{ext}")
    with open(script_path, "w", encoding="utf-8") as f:
        f.write(content)
    _make_executable(script_path)

    return script_path
