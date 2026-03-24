"""
core/executor.py — Runs installation steps sequentially using subprocess.

Supports:
- Cancel (via ``threading.Event``)
- Retry from a specific step
- Skip individual steps
- Cross-platform execution via ``core.platform_utils``
- Windows Job Objects for proper process tree termination
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
import threading
from typing import Callable

from core.models import InstallationPlan
from core.paths import get_bundled_dir
from core.platform_utils import (
    assign_to_job,
    build_env,
    close_job_object,
    create_job_object,
    get_popen_kwargs,
    get_venv_scripts_dir,
    is_windows,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Bundled Runtime Discovery
# ---------------------------------------------------------------------------

def _get_bundled_python() -> str:
    """Locate the bundled Python executable, falling back to system Python.

    Returns:
        Absolute path to a usable Python interpreter.

    Raises:
        RuntimeError: If no Python interpreter can be found in a frozen build.
    """
    bundled_dir = get_bundled_dir()
    if is_windows():
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
        raise RuntimeError(
            "Bundled Python not found, and system Python not found in PATH!"
        )
    return sys.executable


def _get_bundled_git_dir() -> str:
    """Locate the bundled Git directory containing the ``git`` executable.

    On Windows, MinGit places ``git.exe`` in the ``cmd/`` subdirectory rather
    than ``bin/``.  The function checks platform-appropriate paths.

    Returns:
        Absolute path to the bundled Git executable directory, or empty string
        if not found.
    """
    git_base = os.path.join(get_bundled_dir(), "git")

    if is_windows():
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


def _get_bundled_node_dir() -> str:
    """Locate the bundled Node.js directory, falling back to system Node.

    Returns:
        Absolute path to a Node.js directory, or empty string if not found.
    """
    bundled_dir = get_bundled_dir()
    if is_windows():
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


# ---------------------------------------------------------------------------
# Single Command Execution
# ---------------------------------------------------------------------------

def _run_single_command(
    command: str,
    cwd: str,
    env: dict[str, str],
    job: object | None,
    on_output: Callable[[str], None],
    cancel_event: threading.Event | None = None,
) -> tuple[int, list[str]]:
    """Run a single shell command and stream output line by line.

    Args:
        command: The shell command string to execute.
        cwd: Working directory for the command.
        env: Environment variables dict.
        job: Windows Job Object handle (or ``None``).
        on_output: Callback invoked with each output line.
        cancel_event: Optional event that, when set, cancels execution.

    Returns:
        A ``(returncode, output_lines)`` tuple. Return code ``-999`` indicates
        cancellation.
    """
    output_lines: list[str] = []

    try:
        popen_kwargs = get_popen_kwargs()
        proc = subprocess.Popen(
            command,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=env,
            shell=True,
            **popen_kwargs,
        )

        if is_windows() and job:
            try:
                handle = int(proc._handle)  # type: ignore[attr-defined]
                assign_to_job(job, handle)
            except Exception:
                logger.debug("Failed to assign process to job object", exc_info=True)

        for line in proc.stdout:  # type: ignore[union-attr]
            if cancel_event and cancel_event.is_set():
                from core.platform_utils import kill_process_tree
                kill_process_tree(proc)
                return -999, ["Installation cancelled by user."]

            line = line.rstrip("\n").rstrip("\r")
            output_lines.append(line)
            on_output(f"{line}\n")

        proc.wait()
        return proc.returncode or 0, output_lines

    except FileNotFoundError as exc:
        error_msg = f"Command not found: {exc}"
        on_output(f"{error_msg}\n")
        return 1, [error_msg]
    except Exception as exc:
        error_msg = str(exc)
        on_output(f"{error_msg}\n")
        return 1, [error_msg]


# ---------------------------------------------------------------------------
# Command Helpers
# ---------------------------------------------------------------------------

def _fix_git_clone_command(command: str, project_dir: str) -> str:
    """Append the target directory to a ``git clone`` command if missing.

    Args:
        command: The raw git clone command string.
        project_dir: The desired clone target directory.

    Returns:
        The command with the target directory appended.
    """
    parts = command.strip().split()
    if "clone" in parts:
        clone_idx = parts.index("clone")
        non_flag_args = [p for p in parts[clone_idx + 1:] if not p.startswith("-")]
        if len(non_flag_args) <= 1:
            command = f'{command.rstrip()} "{project_dir}"'
    return command


def _split_chained_commands(command: str) -> list[str]:
    """Split a ``&&``-chained command string into individual commands.

    Respects quoted strings so that ``&&`` inside quotes is not treated as a
    separator.

    Args:
        command: The potentially chained command string.

    Returns:
        A list of individual command strings.
    """
    parts: list[str] = []
    current: list[str] = []
    in_quote: str | None = None
    i = 0
    while i < len(command):
        ch = command[i]
        if ch in ('"', "'") and in_quote is None:
            in_quote = ch
            current.append(ch)
        elif ch == in_quote:
            in_quote = None
            current.append(ch)
        elif ch == "&" and i + 1 < len(command) and command[i + 1] == "&" and in_quote is None:
            parts.append("".join(current).strip())
            current = []
            i += 2
            continue
        else:
            current.append(ch)
        i += 1
    remainder = "".join(current).strip()
    if remainder:
        parts.append(remainder)
    return [p for p in parts if p]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def execute_steps(
    plan: InstallationPlan,
    project_dir: str,
    clone_url: str,
    on_output: Callable[[str], None],
    on_step_start: Callable[[int, str], None],
    on_step_done: Callable[[int, bool], None],
    on_error: Callable[[int, str], None],
    cancel_event: threading.Event | None = None,
    resume_from_step: int | None = None,
    skip_step_ids: set[int] | None = None,
) -> bool:
    """Execute installation steps sequentially.

    Args:
        plan: The installation plan dict (must contain a ``steps`` list).
        project_dir: Absolute path to the target project directory.
        clone_url: The git clone URL.
        on_output: Callback for streaming terminal output lines.
        on_step_start: Callback ``(step_id, description)`` when a step begins.
        on_step_done: Callback ``(step_id, success)`` when a step completes.
        on_error: Callback ``(step_id, error_message)`` when a step fails.
        cancel_event: Optional event to signal cancellation.
        resume_from_step: If set, skip all steps before this step id.
        skip_step_ids: Set of step ids to skip entirely.

    Returns:
        ``True`` if all steps succeeded, ``False`` otherwise.
    """
    steps = plan.get("steps", [])
    if not steps:
        on_output("No installation steps found in the plan.\n")
        return False

    skip_step_ids = skip_step_ids or set()
    job = create_job_object()

    bundled_python_dir = os.path.dirname(_get_bundled_python())
    bundled_git_dir = _get_bundled_git_dir()
    bundled_node_dir = _get_bundled_node_dir()

    # MinGit on Windows also needs mingw64/bin/ and mingw64/libexec/git-core/
    extra_git_dirs: list[str] = []
    if bundled_git_dir and is_windows():
        git_base = os.path.join(get_bundled_dir(), "git")
        for sub in ("mingw64\\bin", "mingw64\\libexec\\git-core", "usr\\bin"):
            candidate = os.path.join(git_base, sub)
            if os.path.isdir(candidate) and candidate != bundled_git_dir:
                extra_git_dirs.append(candidate)

    env = build_env(project_dir, bundled_python_dir, bundled_git_dir, bundled_node_dir)

    # Append extra MinGit paths right after the primary git dir
    if extra_git_dirs:
        sep = ";" if is_windows() else ":"
        current_path = env.get("PATH", "")
        git_extras = sep.join(extra_git_dirs)
        # Insert after bundled_git_dir but before system PATH
        if bundled_git_dir and bundled_git_dir in current_path:
            env["PATH"] = current_path.replace(
                bundled_git_dir,
                f"{bundled_git_dir}{sep}{git_extras}",
            )
        else:
            env["PATH"] = f"{git_extras}{sep}{current_path}"
    all_success = True
    reached_resume_point = resume_from_step is None

    for step in steps:
        step_id: int = step.get("id", 0)
        step_type: str = step.get("type", "custom")
        description: str = step.get("description", "Running command...")
        command: str = step.get("command", "")

        # Skip steps before resume point
        if not reached_resume_point:
            if step_id == resume_from_step:
                reached_resume_point = True
            else:
                continue

        # Skip explicitly skipped steps
        if step_id in skip_step_ids:
            on_step_start(step_id, description)
            on_output("[Skipped by user]\n")
            on_step_done(step_id, True)
            continue

        # Check cancel
        if cancel_event and cancel_event.is_set():
            on_output("Installation cancelled.\n")
            break

        on_step_start(step_id, description)

        # --- Special handling: copy_env ---
        if step_type == "copy_env":
            try:
                src = os.path.join(project_dir, ".env.example")
                if not os.path.isfile(src):
                    src = os.path.join(project_dir, ".env.sample")
                dst = os.path.join(project_dir, ".env")
                if os.path.isfile(src):
                    shutil.copy(src, dst)
                    on_output(f"Copied {os.path.basename(src)} -> .env\n")
                    on_step_done(step_id, True)
                else:
                    on_output("No .env.example or .env.sample found, skipping.\n")
                    on_step_done(step_id, True)
            except Exception as exc:
                on_error(step_id, str(exc))
                on_step_done(step_id, False)
                all_success = False
            continue

        # --- Substitute placeholders ---
        command = command.replace("{project_dir}", project_dir)

        # --- Special handling: venv_create ---
        if step_type == "venv_create":
            python_exe = _get_bundled_python()
            venv_path = os.path.join(project_dir, ".venv")
            on_output(f'$ "{python_exe}" -m venv ".venv"\n')
            try:
                proc = subprocess.run(
                    [python_exe, "-m", "venv", venv_path],
                    cwd=project_dir, capture_output=True, text=True, env=env,
                )
                if proc.returncode != 0:
                    on_error(step_id, f"Exit code {proc.returncode}\n{proc.stderr}")
                    on_step_done(step_id, False)
                    all_success = False
                else:
                    on_step_done(step_id, True)
            except Exception as exc:
                on_error(step_id, str(exc))
                on_step_done(step_id, False)
                all_success = False

            if not all_success:
                break
            continue

        # --- Special handling: git_clone ---
        if step_type == "git_clone":
            command = _fix_git_clone_command(f'git clone "{clone_url}"', project_dir)
            cwd = os.path.dirname(project_dir)
            os.makedirs(cwd, exist_ok=True)
        else:
            cwd = project_dir
            os.makedirs(cwd, exist_ok=True)

        # --- Resolve .venv paths ---
        scripts_dir = get_venv_scripts_dir()
        if is_windows():
            if ".venv\\Scripts\\" in command or ".venv/Scripts/" in command:
                venv_scripts = os.path.join(project_dir, ".venv", scripts_dir)
                command = command.replace(".venv\\Scripts\\", f"{venv_scripts}\\")
                command = command.replace(".venv/Scripts/", f"{venv_scripts}/")
        else:
            if ".venv/bin/" in command:
                venv_scripts = os.path.join(project_dir, ".venv", scripts_dir)
                command = command.replace(".venv/bin/", f"{venv_scripts}/")

        # --- Handle chained commands (&&) ---
        sub_commands = _split_chained_commands(command)

        step_failed = False
        for sub_cmd in sub_commands:
            sub_cmd = sub_cmd.strip()
            if not sub_cmd:
                continue

            if sub_cmd.lower().startswith("cd "):
                on_output("[Skipping cd, using project dir as cwd]\n")
                continue

            on_output(f"$ {sub_cmd}\n")

            returncode, output_lines = _run_single_command(
                sub_cmd, cwd, env, job, on_output, cancel_event,
            )

            if cancel_event and cancel_event.is_set():
                on_error(step_id, "Cancelled by user")
                all_success = False
                step_failed = True
                break

            if returncode != 0:
                error_tail = "\n".join(output_lines[-20:])
                on_error(step_id, f"Exit code {returncode}\n{error_tail}")
                all_success = False
                step_failed = True
                break

        if not step_failed:
            on_step_done(step_id, True)
        else:
            on_step_done(step_id, False)
            break

    close_job_object(job)
    return all_success
