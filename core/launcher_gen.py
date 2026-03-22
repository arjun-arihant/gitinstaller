"""
core/launcher_gen.py — Generates launch.bat for installed projects
"""

import os


def _clean_launch_command(command: str, project_dir: str) -> str:
    """Clean up the launch command from AI output."""
    # Substitute any leftover {project_dir} placeholders
    command = command.replace("{project_dir}", project_dir)

    # Remove leading 'cd ... &&' patterns — launch.bat already cd's
    if "&&" in command:
        parts = command.split("&&")
        # Drop any cd commands
        cleaned = []
        for part in parts:
            p = part.strip()
            if p.lower().startswith("cd "):
                continue
            cleaned.append(p)
        command = " && ".join(cleaned) if cleaned else command

    # Resolve relative .venv paths to be relative (they already are in the bat context)
    # No need to make them absolute since the bat file cd's to the project dir

    return command.strip()


def generate_launcher(project_dir: str, plan: dict) -> str:
    """
    Generate a launch.bat file in the project directory.
    Returns the full path to the generated launch.bat.
    """
    repo_name = os.path.basename(project_dir)
    launch_command = plan.get("launch_command", "echo No launch command configured")
    project_type = plan.get("project_type", "unknown")

    launch_command = _clean_launch_command(launch_command, project_dir)

    if project_type == "node":
        bat_content = f"""@echo off
cd /d "%~dp0"
echo Starting {repo_name}...
{launch_command}
pause
"""
    else:
        bat_content = f"""@echo off
cd /d "%~dp0"
call .venv\\Scripts\\activate.bat 2>nul
echo Starting {repo_name}...
{launch_command}
pause
"""

    bat_path = os.path.join(project_dir, "launch.bat")
    with open(bat_path, "w", encoding="utf-8") as f:
        f.write(bat_content)

    return bat_path


def generate_webui_launcher(project_dir: str) -> str:
    """
    Generate a launch_webui.bat file that starts the Gradio web UI.
    Returns the full path to the generated bat file.
    """
    repo_name = os.path.basename(project_dir)

    bat_content = f"""@echo off
cd /d "%~dp0"
call .venv\\Scripts\\activate.bat 2>nul
echo Starting {repo_name} Web UI...
.venv\\Scripts\\python.exe webui.py
pause
"""

    bat_path = os.path.join(project_dir, "launch_webui.bat")
    with open(bat_path, "w", encoding="utf-8") as f:
        f.write(bat_content)

    return bat_path
