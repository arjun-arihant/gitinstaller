"""
core/platform_utils.py — Cross-platform abstraction layer for OS-specific operations.

Provides utilities for:
- OS detection (Windows, macOS, Linux)
- Script extension and path conventions
- Process management (job objects, process trees)
- File/folder operations (open explorer, launch scripts)
- Environment construction for subprocess execution
"""

from __future__ import annotations

import logging
import os
import shutil
import signal
import subprocess
import sys
import webbrowser
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# OS Detection
# ---------------------------------------------------------------------------

def is_windows() -> bool:
    """Return True if the current platform is Windows."""
    return sys.platform == "win32"


def is_macos() -> bool:
    """Return True if the current platform is macOS."""
    return sys.platform == "darwin"


def is_linux() -> bool:
    """Return True if the current platform is Linux."""
    return sys.platform.startswith("linux")


# ---------------------------------------------------------------------------
# Path / Extension Conventions
# ---------------------------------------------------------------------------

def get_script_extension() -> str:
    """Return the platform-appropriate script extension (``.bat`` or ``.sh``)."""
    return ".bat" if is_windows() else ".sh"


def get_venv_scripts_dir() -> str:
    """Return the venv scripts subdirectory name (``Scripts`` on Windows, ``bin`` elsewhere)."""
    return "Scripts" if is_windows() else "bin"


def get_path_separator() -> str:
    """Return the PATH environment variable separator (``;`` on Windows, ``:`` elsewhere)."""
    return ";" if is_windows() else ":"


def get_venv_python(project_dir: str) -> str:
    """Return the full path to the Python executable inside a project's venv.

    Args:
        project_dir: Absolute path to the project directory.
    """
    scripts = get_venv_scripts_dir()
    if is_windows():
        return os.path.join(project_dir, ".venv", scripts, "python.exe")
    return os.path.join(project_dir, ".venv", scripts, "python")


def get_venv_pip(project_dir: str) -> str:
    """Return the full path to the pip executable inside a project's venv.

    Args:
        project_dir: Absolute path to the project directory.
    """
    scripts = get_venv_scripts_dir()
    if is_windows():
        return os.path.join(project_dir, ".venv", scripts, "pip.exe")
    return os.path.join(project_dir, ".venv", scripts, "pip")


# ---------------------------------------------------------------------------
# Process Management — Windows Job Objects
# ---------------------------------------------------------------------------

def create_job_object() -> object | None:
    """Create a Windows Job Object for managing child process lifetimes.

    On non-Windows platforms, returns ``None``.
    The job object is configured with ``JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE``
    so that all child processes are terminated when the job handle is closed.
    """
    if not is_windows():
        return None

    import ctypes
    import ctypes.wintypes

    kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
    job = kernel32.CreateJobObjectW(None, None)
    if not job:
        logger.warning("Failed to create Windows Job Object")
        return None

    class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.wintypes.LARGE_INTEGER),
            ("PerJobUserTimeLimit", ctypes.wintypes.LARGE_INTEGER),
            ("LimitFlags", ctypes.wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", ctypes.wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),  # type: ignore[arg-type]  # ULONG_PTR — must be pointer-sized
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


def assign_to_job(job: object, process_handle: int) -> None:
    """Assign a subprocess to a Windows Job Object.

    Args:
        job: The job object handle returned by ``create_job_object()``.
        process_handle: The native process handle (e.g. ``proc._handle`` on Windows).
    """
    if not is_windows() or not job:
        return
    import ctypes
    ctypes.windll.kernel32.AssignProcessToJobObject(job, process_handle)  # type: ignore[attr-defined]


def close_job_object(job: object | None) -> None:
    """Close a Windows Job Object handle.

    Args:
        job: The job object handle, or ``None``.
    """
    if not job:
        return
    if is_windows():
        import ctypes
        try:
            ctypes.windll.kernel32.CloseHandle(job)  # type: ignore[attr-defined]
        except Exception:
            logger.debug("Failed to close job object handle", exc_info=True)


def terminate_job_object(job: object | None) -> None:
    """Terminate all processes in a Windows Job Object.

    Args:
        job: The job object handle, or ``None``.
    """
    if not job:
        return
    if is_windows():
        import ctypes
        try:
            ctypes.windll.kernel32.TerminateJobObject(job, 1)  # type: ignore[attr-defined]
        except Exception:
            logger.debug("Failed to terminate job object", exc_info=True)


def kill_process_tree(proc: subprocess.Popen[str] | None) -> None:
    """Kill a process and all its children.

    On Windows uses ``taskkill /F /T``. On Unix uses ``os.killpg`` with SIGTERM.

    Args:
        proc: The subprocess to kill, or ``None``.
    """
    if proc is None:
        return
    try:
        if is_windows():
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                capture_output=True, timeout=5,
            )
        else:
            os.kill(-proc.pid, signal.SIGTERM)
    except Exception:
        try:
            proc.kill()
        except Exception:
            logger.debug("Failed to kill process %s", proc.pid, exc_info=True)


def get_subprocess_flags() -> int:
    """Return platform-specific subprocess creation flags."""
    if is_windows():
        return subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
    return 0


def get_popen_kwargs() -> dict[str, Any]:
    """Return platform-specific keyword arguments for ``subprocess.Popen``.

    On Windows: sets ``creationflags`` to ``CREATE_NEW_PROCESS_GROUP``.
    On Unix: sets ``process_group=0`` to create a new process group
    (preferred over the deprecated ``preexec_fn=os.setsid``).
    """
    kwargs: dict[str, Any] = {}
    if is_windows():
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
    else:
        kwargs["process_group"] = 0
    return kwargs


# ---------------------------------------------------------------------------
# File / Folder Operations
# ---------------------------------------------------------------------------

def open_folder(path: str) -> None:
    """Open a folder in the system file explorer.

    Args:
        path: Absolute path to the folder.
    """
    if is_windows():
        subprocess.Popen(["explorer", path])
    elif is_macos():
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])


def open_url(url: str) -> None:
    """Open a URL in the default web browser.

    Args:
        url: The URL to open.
    """
    webbrowser.open(url)


def launch_script(script_path: str, cwd: str | None = None) -> None:
    """Launch a ``.bat`` or ``.sh`` script in a new terminal window.

    Args:
        script_path: Absolute path to the script file.
        cwd: Working directory for the script. Defaults to the script's parent directory.
    """
    work_dir = cwd or os.path.dirname(script_path)

    if is_windows():
        subprocess.Popen(
            ["cmd", "/c", "start", "", script_path],
            shell=True,
            cwd=work_dir,
        )
    elif is_macos():
        subprocess.Popen(
            ["open", "-a", "Terminal", script_path],
            cwd=work_dir,
        )
    else:
        terminals = ["gnome-terminal", "xfce4-terminal", "konsole", "xterm"]
        for term in terminals:
            if shutil.which(term):
                if term == "gnome-terminal":
                    subprocess.Popen(
                        [term, "--", "bash", script_path],
                        cwd=work_dir,
                    )
                else:
                    subprocess.Popen(
                        [term, "-e", f"bash {script_path}"],
                        cwd=work_dir,
                    )
                break


# ---------------------------------------------------------------------------
# Environment Construction
# ---------------------------------------------------------------------------

def build_env(
    project_dir: str,
    bundled_python_dir: str = "",
    bundled_git_dir: str = "",
    bundled_node_dir: str = "",
) -> dict[str, str]:
    """Build a clean environment dict for subprocess execution.

    Constructs a ``PATH`` that prioritises the project venv, then bundled runtimes,
    then the system PATH. Also forwards essential platform-specific environment
    variables (``SYSTEMROOT``, ``HOME``, etc.).

    Args:
        project_dir: Absolute path to the project directory.
        bundled_python_dir: Path to bundled Python directory (optional).
        bundled_git_dir: Path to bundled Git ``bin/`` directory (optional).
        bundled_node_dir: Path to bundled Node.js directory (optional).

    Returns:
        A dict suitable for passing as ``env`` to ``subprocess.Popen``.
    """
    sep = get_path_separator()
    scripts_dir = get_venv_scripts_dir()

    path_parts: list[str] = [
        os.path.join(project_dir, ".venv", scripts_dir),
    ]
    if bundled_python_dir:
        path_parts.append(bundled_python_dir)
    if bundled_git_dir:
        path_parts.append(bundled_git_dir)
    if bundled_node_dir:
        path_parts.append(bundled_node_dir)
    path_parts.append(os.environ.get("PATH", ""))

    env: dict[str, str] = {
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
