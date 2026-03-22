"""
core/executor.py — Runs installation steps sequentially using subprocess + Windows Job Objects
"""

import os
import sys
import shutil
import subprocess
import ctypes
import ctypes.wintypes


def _get_app_dir():
    """Get the directory where the app is installed."""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _get_bundled_python():
    """Resolve path to bundled Python executable, fallback to system."""
    app_dir = _get_app_dir()
    bundled = os.path.join(app_dir, "bundled", "python", "python.exe")
    if os.path.isfile(bundled):
        return bundled
    # Fallback to system Python with warning
    print("[WARNING] Bundled Python not found, using system Python")
    if getattr(sys, 'frozen', False):
        import shutil
        sys_python = shutil.which("python")
        if sys_python:
            return sys_python
        else:
            raise RuntimeError("Bundled Python not found, and system Python not found in PATH!")
    return sys.executable


def _get_bundled_git_dir():
    """Resolve path to bundled Git bin directory, fallback to empty string."""
    app_dir = _get_app_dir()
    bundled = os.path.join(app_dir, "bundled", "git", "bin")
    if os.path.isdir(bundled):
        return bundled
    print("[WARNING] Bundled Git not found, using system Git")
    return ""


def create_job_object():
    """Create a Windows Job Object to group all child processes."""
    kernel32 = ctypes.windll.kernel32

    job = kernel32.CreateJobObjectW(None, None)
    if not job:
        return None

    class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.wintypes.LARGE_INTEGER),
            ("PerJobUserTimeLimit", ctypes.wintypes.LARGE_INTEGER),
            ("LimitFlags", ctypes.wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", ctypes.wintypes.DWORD),
            ("Affinity", ctypes.POINTER(ctypes.c_ulong)),
            ("PriorityClass", ctypes.wintypes.DWORD),
            ("SchedulingClass", ctypes.wintypes.DWORD),
        ]

    class IO_COUNTERS(ctypes.Structure):
        _fields_ = [
            ("ReadOperationCount", ctypes.c_ulonglong),
            ("WriteOperationCount", ctypes.c_ulonglong),
            ("OtherOperationCount", ctypes.c_ulonglong),
            ("ReadTransferCount", ctypes.c_ulonglong),
            ("WriteTransferCount", ctypes.c_ulonglong),
            ("OtherTransferCount", ctypes.c_ulonglong),
        ]

    class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
            ("IoInfo", IO_COUNTERS),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
    info.BasicLimitInformation.LimitFlags = 0x2000

    kernel32.SetInformationJobObject(
        job, 9, ctypes.byref(info), ctypes.sizeof(info),
    )

    return job


def assign_to_job(job, process_handle):
    """Assign a subprocess to the Job Object."""
    if job:
        ctypes.windll.kernel32.AssignProcessToJobObject(job, process_handle)


def _build_env(project_dir: str) -> dict:
    """Build a clean environment dict for subprocess execution."""
    bundled_python_dir = os.path.dirname(_get_bundled_python())
    bundled_git_dir = _get_bundled_git_dir()

    path_parts = [
        os.path.join(project_dir, ".venv", "Scripts"),
        bundled_python_dir,
    ]
    if bundled_git_dir:
        path_parts.append(bundled_git_dir)
    path_parts.append(os.environ.get("PATH", ""))

    env = {
        "PATH": ";".join(path_parts),
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUTF8": "1",
    }

    for key in ("SYSTEMROOT", "TEMP", "TMP", "APPDATA", "USERPROFILE",
                "LOCALAPPDATA", "HOMEDRIVE", "HOMEPATH", "COMSPEC"):
        val = os.environ.get(key)
        if val:
            env[key] = val

    return env


def _run_single_command(command, cwd, env, job, on_output):
    """Run a single shell command and stream output. Returns (returncode, output_lines)."""
    output_lines = []

    try:
        proc = subprocess.Popen(
            command,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=env,
            shell=True,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
        )

        try:
            handle = int(proc._handle)
            assign_to_job(job, handle)
        except Exception:
            pass

        for line in proc.stdout:
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
    """
    Ensure git clone always clones into the exact project_dir path.
    Git clone by default uses the repo name as the directory,
    but we need owner-repo format.
    """
    # If the command doesn't already specify a target directory after the URL,
    # append the project_dir basename
    parts = command.strip().split()

    # Find the git clone URL (the last argument that looks like a URL or .git path)
    # Typical: git clone https://github.com/owner/repo.git
    # We want: git clone https://github.com/owner/repo.git "project_dir"
    if "clone" in parts:
        # Check if a target directory is already specified
        clone_idx = parts.index("clone")
        # Count non-flag arguments after 'clone'
        non_flag_args = []
        for p in parts[clone_idx + 1:]:
            if not p.startswith("-"):
                non_flag_args.append(p)

        if len(non_flag_args) <= 1:
            # Only the URL is specified, no target dir — append project_dir
            command = f'{command.rstrip()} "{project_dir}"'

    return command


def _split_chained_commands(command):
    """Split &&-chained commands into a list of individual commands."""
    # Split on && but be careful not to split within quotes
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
                  on_step_done, on_error):
    """
    Execute the installation steps sequentially inside the project directory.
    Returns True if all steps succeeded, False if any step failed.
    """
    steps = plan.get("steps", [])
    if not steps:
        on_output("No installation steps found in the plan.\n")
        return False

    job = create_job_object()
    env = _build_env(project_dir)
    all_success = True

    for step in steps:
        step_id = step.get("id", 0)
        step_type = step.get("type", "custom")
        description = step.get("description", "Running command...")
        command = step.get("command", "")

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
            on_output(f"$ \"{python_exe}\" -m venv \".venv\"\n")
            try:
                proc = subprocess.run([python_exe, "-m", "venv", venv_path],
                                      cwd=project_dir, capture_output=True, text=True, env=env)
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

        # --- Resolve .venv\Scripts\ paths ---
        if ".venv\\Scripts\\" in command or ".venv/Scripts/" in command:
            command = command.replace(
                ".venv\\Scripts\\",
                os.path.join(project_dir, ".venv", "Scripts") + "\\"
            )
            command = command.replace(
                ".venv/Scripts/",
                os.path.join(project_dir, ".venv", "Scripts") + "/"
            )

        # --- Handle chained commands (&&) ---
        sub_commands = _split_chained_commands(command)

        step_failed = False
        for i, sub_cmd in enumerate(sub_commands):
            sub_cmd = sub_cmd.strip()
            if not sub_cmd:
                continue

            # Skip "cd" commands — we already handle cwd properly
            if sub_cmd.lower().startswith("cd "):
                on_output(f"[Skipping cd, using project dir as cwd]\n")
                continue

            on_output(f"$ {sub_cmd}\n")

            # Determine cwd for this sub-command
            run_cwd = cwd

            returncode, output_lines = _run_single_command(
                " " + sub_cmd, run_cwd, env, job, on_output
            )

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

    # Close the job object handle
    if job:
        try:
            ctypes.windll.kernel32.CloseHandle(job)
        except Exception:
            pass

    return all_success
