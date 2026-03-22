"""
core/platform_utils.py — Cross-platform abstraction layer for OS-specific operations
"""

import os
import sys
import signal
import subprocess
import webbrowser


def is_windows():
    return sys.platform == "win32"


def is_macos():
    return sys.platform == "darwin"


def is_linux():
    return sys.platform.startswith("linux")


def get_script_extension():
    return ".bat" if is_windows() else ".sh"


def get_venv_scripts_dir():
    return "Scripts" if is_windows() else "bin"


def get_path_separator():
    return ";" if is_windows() else ":"


def get_venv_python(project_dir):
    scripts = get_venv_scripts_dir()
    if is_windows():
        return os.path.join(project_dir, ".venv", scripts, "python.exe")
    return os.path.join(project_dir, ".venv", scripts, "python")


def get_venv_pip(project_dir):
    scripts = get_venv_scripts_dir()
    if is_windows():
        return os.path.join(project_dir, ".venv", scripts, "pip.exe")
    return os.path.join(project_dir, ".venv", scripts, "pip")


# --- Process Management ---

def create_job_object():
    """Create a process group/job object for managing child processes."""
    if not is_windows():
        return None

    import ctypes
    import ctypes.wintypes

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
    info.BasicLimitInformation.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE

    kernel32.SetInformationJobObject(
        job, 9, ctypes.byref(info), ctypes.sizeof(info),
    )

    return job


def assign_to_job(job, process_handle):
    """Assign a subprocess to the Job Object (Windows only)."""
    if not is_windows() or not job:
        return
    import ctypes
    ctypes.windll.kernel32.AssignProcessToJobObject(job, process_handle)


def close_job_object(job):
    """Close the job object handle."""
    if not job:
        return
    if is_windows():
        import ctypes
        try:
            ctypes.windll.kernel32.CloseHandle(job)
        except Exception:
            pass


def terminate_job_object(job):
    """Terminate all processes in the job object."""
    if not job:
        return
    if is_windows():
        import ctypes
        try:
            ctypes.windll.kernel32.TerminateJobObject(job, 1)
        except Exception:
            pass


def kill_process_tree(proc):
    """Kill a process and all its children."""
    if proc is None:
        return
    try:
        if is_windows():
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                capture_output=True, timeout=5
            )
        else:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


def get_subprocess_flags():
    """Get platform-specific subprocess creation flags."""
    if is_windows():
        return subprocess.CREATE_NEW_PROCESS_GROUP
    return 0


def get_popen_kwargs():
    """Get platform-specific Popen keyword arguments."""
    kwargs = {}
    if is_windows():
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["preexec_fn"] = os.setsid
    return kwargs


# --- File/Folder Operations ---

def open_folder(path):
    """Open a folder in the system file explorer."""
    if is_windows():
        subprocess.Popen(["explorer", path])
    elif is_macos():
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])


def open_url(url):
    """Open a URL in the default browser."""
    webbrowser.open(url)


def launch_script(script_path, cwd=None):
    """Launch a .bat or .sh script in a new terminal window."""
    if is_windows():
        subprocess.Popen(
            ["cmd", "/c", "start", "", script_path],
            shell=True,
            cwd=cwd or os.path.dirname(script_path)
        )
    elif is_macos():
        subprocess.Popen(
            ["open", "-a", "Terminal", script_path],
            cwd=cwd or os.path.dirname(script_path)
        )
    else:
        terminals = ["gnome-terminal", "xfce4-terminal", "konsole", "xterm"]
        for term in terminals:
            import shutil
            if shutil.which(term):
                if term == "gnome-terminal":
                    subprocess.Popen(
                        [term, "--", "bash", script_path],
                        cwd=cwd or os.path.dirname(script_path)
                    )
                else:
                    subprocess.Popen(
                        [term, "-e", f"bash {script_path}"],
                        cwd=cwd or os.path.dirname(script_path)
                    )
                break


def build_env(project_dir, bundled_python_dir="", bundled_git_dir="", bundled_node_dir=""):
    """Build a clean environment dict for subprocess execution."""
    sep = get_path_separator()
    scripts_dir = get_venv_scripts_dir()

    path_parts = [
        os.path.join(project_dir, ".venv", scripts_dir),
    ]
    if bundled_python_dir:
        path_parts.append(bundled_python_dir)
    if bundled_git_dir:
        path_parts.append(bundled_git_dir)
    if bundled_node_dir:
        path_parts.append(bundled_node_dir)
    path_parts.append(os.environ.get("PATH", ""))

    env = {
        "PATH": sep.join(path_parts),
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUTF8": "1",
    }

    if is_windows():
        for key in ("SYSTEMROOT", "TEMP", "TMP", "APPDATA", "USERPROFILE",
                     "LOCALAPPDATA", "HOMEDRIVE", "HOMEPATH", "COMSPEC"):
            val = os.environ.get(key)
            if val:
                env[key] = val
    else:
        for key in ("HOME", "USER", "SHELL", "LANG", "TERM", "TMPDIR"):
            val = os.environ.get(key)
            if val:
                env[key] = val

    return env
