"""
core/executor.py — Runs installation steps sequentially using subprocess
Supports cancel (via threading.Event), retry from step, and skip steps.
Cross-platform via platform_utils.
"""

import os
import sys
import shutil
import subprocess
import threading

from core.platform_utils import (
    is_windows, create_job_object, assign_to_job, close_job_object,
    terminate_job_object, get_popen_kwargs, build_env, get_venv_scripts_dir
)


def _get_app_dir():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _get_bundled_python():
    app_dir = _get_app_dir()
    if is_windows():
        bundled = os.path.join(app_dir, "bundled", "python", "python.exe")
    else:
        bundled = os.path.join(app_dir, "bundled", "python", "bin", "python3")
    if os.path.isfile(bundled):
        return bundled
    print("[WARNING] Bundled Python not found, using system Python")
    if getattr(sys, 'frozen', False):
        sys_python = shutil.which("python3") or shutil.which("python")
        if sys_python:
            return sys_python
        raise RuntimeError("Bundled Python not found, and system Python not found in PATH!")
    return sys.executable


def _get_bundled_git_dir():
    app_dir = _get_app_dir()
    bundled = os.path.join(app_dir, "bundled", "git", "bin")
    if os.path.isdir(bundled):
        return bundled
    print("[WARNING] Bundled Git not found, using system Git")
    return ""


def _get_bundled_node_dir():
    """Locate bundled Node.js or fall back to system Node."""
    app_dir = _get_app_dir()
    if is_windows():
        bundled = os.path.join(app_dir, "bundled", "node")
    else:
        bundled = os.path.join(app_dir, "bundled", "node", "bin")
    if os.path.isdir(bundled):
        return bundled
    # Fall back to system node
    node_path = shutil.which("node")
    if node_path:
        return os.path.dirname(node_path)
    return ""


def _run_single_command(command, cwd, env, job, on_output, cancel_event=None):
    """Run a single shell command and stream output. Returns (returncode, output_lines)."""
    output_lines = []

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
                handle = int(proc._handle)
                assign_to_job(job, handle)
            except Exception:
                pass

        for line in proc.stdout:
            if cancel_event and cancel_event.is_set():
                from core.platform_utils import kill_process_tree
                kill_process_tree(proc)
                return -999, ["Installation cancelled by user."]

            line = line.rstrip("\n").rstrip("\r")
            output_lines.append(line)
            on_output(line + "\n")

        proc.wait()
        return proc.returncode, output_lines

    except FileNotFoundError as e:
        error_msg = f"Command not found: {e}"
        on_output(error_msg + "\n")
        return 1, [error_msg]
    except Exception as e:
        error_msg = str(e)
        on_output(error_msg + "\n")
        return 1, [error_msg]


def _fix_git_clone_command(command, project_dir):
    parts = command.strip().split()
    if "clone" in parts:
        clone_idx = parts.index("clone")
        non_flag_args = [p for p in parts[clone_idx + 1:] if not p.startswith("-")]
        if len(non_flag_args) <= 1:
            command = f'{command.rstrip()} "{project_dir}"'
    return command


def _split_chained_commands(command):
    parts = []
    current = []
    in_quote = None
    i = 0
    while i < len(command):
        ch = command[i]
        if ch in ('"', "'") and in_quote is None:
            in_quote = ch
            current.append(ch)
        elif ch == in_quote:
            in_quote = None
            current.append(ch)
        elif ch == '&' and i + 1 < len(command) and command[i + 1] == '&' and in_quote is None:
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


def execute_steps(plan, project_dir, clone_url, on_output, on_step_start,
                  on_step_done, on_error, cancel_event=None,
                  resume_from_step=None, skip_step_ids=None):
    """
    Execute the installation steps sequentially.
    Returns True if all steps succeeded, False otherwise.

    cancel_event: threading.Event — set to cancel mid-install
    resume_from_step: int — skip steps before this step id
    skip_step_ids: set — step ids to skip entirely
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
    env = build_env(project_dir, bundled_python_dir, bundled_git_dir, bundled_node_dir)
    all_success = True
    reached_resume_point = resume_from_step is None

    for step in steps:
        step_id = step.get("id", 0)
        step_type = step.get("type", "custom")
        description = step.get("description", "Running command...")
        command = step.get("command", "")

        # Skip steps before resume point
        if not reached_resume_point:
            if step_id == resume_from_step:
                reached_resume_point = True
            else:
                continue

        # Skip explicitly skipped steps
        if step_id in skip_step_ids:
            on_step_start(step_id, description)
            on_output(f"[Skipped by user]\n")
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
            except Exception as e:
                on_error(step_id, str(e))
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
                    cwd=project_dir, capture_output=True, text=True, env=env
                )
                if proc.returncode != 0:
                    on_error(step_id, f"Exit code {proc.returncode}\n{proc.stderr}")
                    all_success = False
                else:
                    on_step_done(step_id, True)
            except Exception as e:
                on_error(step_id, str(e))
                all_success = False

            if not all_success:
                break
            continue

        # --- Special handling: git_clone ---
        if step_type == "git_clone":
            command = _fix_git_clone_command(command, project_dir)
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
                command = command.replace(".venv\\Scripts\\", venv_scripts + "\\")
                command = command.replace(".venv/Scripts/", venv_scripts + "/")
        else:
            if ".venv/bin/" in command:
                venv_scripts = os.path.join(project_dir, ".venv", scripts_dir)
                command = command.replace(".venv/bin/", venv_scripts + "/")

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
                " " + sub_cmd, cwd, env, job, on_output, cancel_event
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
            break

    close_job_object(job)
    return all_success
