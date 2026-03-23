"""
app.py — PyWebView entry point for GitInstaller.

Exposes a Python API to JavaScript via ``pywebview``. The ``API`` class methods
are callable from the frontend as ``window.pywebview.api.<method>()``.

Features: Plan review, cancel, retry/skip, system tray, theme, private repos,
plan caching, size estimation.
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
from datetime import datetime
from typing import Any

import webview

from core.github_fetcher import (
    GitHubRateLimitError,
    NetworkError,
    RepoNotFoundError,
    fetch_repo_data,
    fetch_repo_size,
)
from core.claude_analyzer import AnalysisError, analyze_repo
from core.executor import execute_steps
from core.launcher_gen import generate_launcher, generate_webui_launcher
from core.models import InstallationPlan, RepoData
from core.paths import get_frontend_dir
from core.platform_utils import (
    is_windows,
    launch_script,
    open_folder as _open_folder_native,
)
from core.project_manager import (
    add_project,
    get_all_projects,
    get_api_key as _get_api_key,
    get_github_token as _get_github_token,
    get_install_path as _get_install_path,
    get_theme as _get_theme,
    load_plan as _load_plan,
    remove_project as _remove_project,
    save_plan as _save_plan,
    set_api_key as _set_api_key,
    set_github_token as _set_github_token,
    set_install_path as _set_install_path,
    set_theme as _set_theme,
    update_project_field,
    update_project_status,
)
from core.webui_gen import build_webui, detect_needs_webui

# ---------------------------------------------------------------------------
# Logging Configuration
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# API Class
# ---------------------------------------------------------------------------

class API:
    """Python API exposed to JavaScript via ``window.pywebview.api``.

    All public methods on this class are callable from the frontend.
    """

    def __init__(self) -> None:
        self._window: Any = None
        self._current_plan: InstallationPlan | None = None
        self._current_repo_data: RepoData | None = None
        self._current_project_dir: str | None = None
        self._current_project_id: str | None = None
        self._cancel_event: threading.Event = threading.Event()
        self._install_thread: threading.Thread | None = None

    def _set_window(self, window: Any) -> None:
        """Store a reference to the pywebview window."""
        self._window = window

    def _push_event(self, event: dict) -> None:
        """Push an event to the frontend via JavaScript evaluation.

        Args:
            event: Event dict to serialise and send.
        """
        if self._window:
            event_json = json.dumps(event, ensure_ascii=False)
            event_json_escaped = event_json.replace("\\", "\\\\").replace("'", "\\'")
            self._window.evaluate_js(f"window.onInstallEvent('{event_json_escaped}')")

    # --- Project Management ---

    def get_projects(self) -> list[dict]:
        """Return all registered projects."""
        return get_all_projects()

    def get_install_path(self) -> str:
        """Return the current install path."""
        return _get_install_path()

    def set_install_path(self, path: str) -> None:
        """Persist the install path."""
        _set_install_path(path)

    def get_api_key(self) -> str:
        """Return the OpenRouter API key."""
        return _get_api_key()

    def set_api_key(self, key: str) -> None:
        """Persist the OpenRouter API key."""
        _set_api_key(key)

    def get_github_token(self) -> str:
        """Return the GitHub personal access token."""
        return _get_github_token()

    def set_github_token(self, token: str) -> None:
        """Persist the GitHub personal access token."""
        _set_github_token(token)

    def get_theme(self) -> str:
        """Return the current UI theme name."""
        return _get_theme()

    def set_theme(self, theme: str) -> None:
        """Persist the UI theme preference."""
        _set_theme(theme)

    def pick_folder(self) -> str | None:
        """Open a native folder picker dialog.

        Returns:
            The selected folder path, or ``None`` if cancelled.
        """
        if not self._window:
            return None
        result = self._window.create_file_dialog(
            webview.FOLDER_DIALOG,
            directory=_get_install_path(),
        )
        if result and len(result) > 0:
            return result[0]
        return None

    def validate_github_url(self, url: str) -> dict:
        """Validate a GitHub URL or shorthand and extract owner/repo.

        Args:
            url: The URL or ``owner/repo`` shorthand.

        Returns:
            Dict with ``valid``, ``owner``, and ``repo`` keys.
        """
        url = url.strip()
        # Accept shorthand owner/repo
        shorthand = re.match(r"^([a-zA-Z0-9_.-]+)/([a-zA-Z0-9_.-]+)$", url)
        if shorthand:
            return {"valid": True, "owner": shorthand.group(1), "repo": shorthand.group(2)}

        pattern = r"(?:https?://)?github\.com/([^/]+)/([^/.]+?)(?:\.git)?(?:/.*)?$"
        match = re.match(pattern, url)
        if match:
            return {"valid": True, "owner": match.group(1), "repo": match.group(2)}
        return {"valid": False, "owner": "", "repo": ""}

    def get_current_plan(self) -> InstallationPlan | None:
        """Return the current installation plan, if any."""
        return self._current_plan

    def get_cached_plan(self, project_id: str) -> dict[str, Any] | None:
        """Return a cached plan for the given project, if available.

        Args:
            project_id: The project identifier.
        """
        data = _load_plan(project_id)
        if data:
            return {
                "plan": data["plan"],
                "cached_at": data.get("cached_at", ""),
            }
        return None

    def get_repo_size(self, repo_url: str) -> float | None:
        """Fetch the repository size in MB.

        Args:
            repo_url: GitHub repository URL or shorthand.
        """
        token = _get_github_token()
        return fetch_repo_size(repo_url, token or None)

    # --- Install Pipeline (2-Stage: Fetch+Analyze → then Approve+Execute) ---

    def start_analyze(self, repo_url: str) -> None:
        """Stage 1: Fetch repo data and analyse with AI. Returns plan for review.

        Args:
            repo_url: GitHub repository URL or shorthand.
        """
        self._cancel_event.clear()
        thread = threading.Thread(
            target=self._analyze_pipeline,
            args=(repo_url,),
            daemon=True,
        )
        thread.start()

    def _analyze_pipeline(self, repo_url: str) -> None:
        """Background thread: fetch repo data and generate installation plan."""
        api_key = _get_api_key()
        if not api_key:
            self._push_event({
                "type": "stage", "stage": "error",
                "message": "OpenRouter API key not set. Please add it in Settings.",
            })
            return

        github_token = _get_github_token() or None

        try:
            self._push_event({"type": "stage", "stage": "fetching"})
            repo_data = fetch_repo_data(repo_url, github_token)
            self._current_repo_data = repo_data
        except RepoNotFoundError as exc:
            self._push_event({"type": "stage", "stage": "error", "message": str(exc)})
            return
        except GitHubRateLimitError as exc:
            self._push_event({"type": "stage", "stage": "error", "message": str(exc)})
            return
        except NetworkError as exc:
            self._push_event({"type": "stage", "stage": "error", "message": str(exc)})
            return
        except Exception as exc:
            logger.error("Unexpected error fetching repo: %s", exc, exc_info=True)
            self._push_event({"type": "stage", "stage": "error", "message": f"Error fetching repo: {exc}"})
            return

        owner = repo_data["owner"]
        repo = repo_data["repo"]
        project_id = f"{owner}-{repo}"

        # Check for cached plan
        cached = _load_plan(project_id)

        try:
            plan: InstallationPlan
            if cached and isinstance(cached.get("plan"), dict):
                logger.info("Using cached plan for %s", project_id)
                plan = cached["plan"]
            else:
                self._push_event({"type": "stage", "stage": "analyzing"})
                plan = analyze_repo(repo_data, api_key)
                _save_plan(project_id, plan)

            self._current_plan = plan

            # Get size estimate
            size_mb: float | None = None
            try:
                raw_size = repo_data.get("size_kb", 0)
                if raw_size:
                    size_mb = round(raw_size / 1024, 1)
            except Exception:
                logger.debug("Failed to compute size estimate", exc_info=True)

            self._push_event({
                "type": "plan_review",
                "plan": plan,
                "owner": owner,
                "repo": repo,
                "description": repo_data.get("description", ""),
                "stars": repo_data.get("stars", 0),
                "size_mb": size_mb,
                "has_cached": cached is not None,
                "cached_at": cached.get("cached_at", "") if cached else "",
            })

        except AnalysisError as exc:
            self._push_event({"type": "stage", "stage": "error", "message": str(exc)})
            return
        except Exception as exc:
            logger.error("AI analysis failed: %s", exc, exc_info=True)
            self._push_event({"type": "stage", "stage": "error", "message": f"AI analysis failed: {exc}"})
            return

    def approve_and_install(self, install_path: str) -> None:
        """Stage 2: User approved the plan — execute installation.

        Args:
            install_path: Absolute path to the parent install directory.
        """
        if not self._current_plan or not self._current_repo_data:
            return

        self._cancel_event.clear()
        self._install_thread = threading.Thread(
            target=self._execute_pipeline,
            args=(install_path,),
            daemon=True,
        )
        self._install_thread.start()

    def _execute_pipeline(self, install_path: str) -> None:
        """Background thread: execute the approved installation plan."""
        repo_data = self._current_repo_data
        plan = self._current_plan
        if not repo_data or not plan:
            return

        owner = repo_data["owner"]
        repo = repo_data["repo"]
        clone_url = repo_data.get("authenticated_clone_url", repo_data["clone_url"])

        try:
            self._push_event({"type": "stage", "stage": "installing"})

            # Send plan to frontend so it can build step list + progress bar
            self._push_event({"type": "plan", "plan": plan})

            project_dir = os.path.join(install_path, f"{owner}-{repo}")
            self._current_project_dir = project_dir

            def on_output(line: str) -> None:
                self._push_event({"type": "output", "line": line})

            def on_step_start(step_id: int, description: str) -> None:
                self._push_event({
                    "type": "step_start",
                    "step_id": step_id,
                    "description": description,
                })

            def on_step_done(step_id: int, success: bool) -> None:
                self._push_event({
                    "type": "step_done",
                    "step_id": step_id,
                    "success": success,
                })

            def on_error(step_id: int, error: str) -> None:
                self._push_event({
                    "type": "step_error",
                    "step_id": step_id,
                    "error": error,
                })

            success = execute_steps(
                plan, project_dir, clone_url,
                on_output, on_step_start, on_step_done, on_error,
                cancel_event=self._cancel_event,
            )

            if self._cancel_event.is_set():
                self._push_event({"type": "stage", "stage": "cancelled"})
                return

            # Generate launcher
            launch_file = generate_launcher(project_dir, plan)

            # Register project
            project_id = f"{owner}-{repo}"
            self._current_project_id = project_id
            project_metadata = {
                "id": project_id,
                "name": repo,
                "owner": owner,
                "description": repo_data.get("description", ""),
                "project_dir": project_dir,
                "launch_file": launch_file,
                "installed_at": datetime.now().isoformat(),
                "status": "installed" if success else "partial",
                "stars": repo_data.get("stars", 0),
                "size_mb": round(repo_data.get("size_kb", 0) / 1024, 1),
            }
            add_project(project_metadata)
            _set_install_path(install_path)

            # Check if WebUI needed
            needs_webui = detect_needs_webui(plan, project_dir)

            if not success:
                self._push_event({
                    "type": "stage", "stage": "error",
                    "message": "Installation failed or was only partially completed.",
                })
            else:
                self._push_event({"type": "stage", "stage": "done"})

            self._push_event({
                "type": "done",
                "project_id": project_id,
                "launch_file": launch_file if success else None,
                "project_dir": project_dir,
                "notes": plan.get("notes"),
                "needs_webui": needs_webui if success else False,
            })

        except Exception as exc:
            logger.error("Installation error: %s", exc, exc_info=True)
            self._push_event({"type": "stage", "stage": "error", "message": f"Installation error: {exc}"})

    # --- Cancel ---

    def cancel_install(self) -> None:
        """Signal cancellation of the current installation."""
        self._cancel_event.set()

    # --- Retry / Skip ---

    def retry_from_step(self, step_id: int, install_path: str) -> None:
        """Retry installation from a specific step.

        Args:
            step_id: The step id to resume from.
            install_path: Absolute path to the parent install directory.
        """
        if not self._current_plan or not self._current_repo_data:
            return

        self._cancel_event.clear()
        self._install_thread = threading.Thread(
            target=self._retry_pipeline,
            args=(install_path, step_id, None),
            daemon=True,
        )
        self._install_thread.start()

    def skip_and_continue(self, step_id: int, install_path: str) -> None:
        """Skip a failed step and continue with the rest.

        Args:
            step_id: The step id to skip.
            install_path: Absolute path to the parent install directory.
        """
        if not self._current_plan or not self._current_repo_data:
            return

        self._cancel_event.clear()
        self._install_thread = threading.Thread(
            target=self._retry_pipeline,
            args=(install_path, step_id, {step_id}),
            daemon=True,
        )
        self._install_thread.start()

    def _retry_pipeline(
        self,
        install_path: str,
        resume_step: int,
        skip_ids: set[int] | None,
    ) -> None:
        """Background thread: retry/skip installation from a specific step."""
        repo_data = self._current_repo_data
        plan = self._current_plan
        if not repo_data or not plan:
            return

        owner = repo_data["owner"]
        repo = repo_data["repo"]
        clone_url = repo_data.get("authenticated_clone_url", repo_data["clone_url"])

        project_dir = os.path.join(install_path, f"{owner}-{repo}")
        self._current_project_dir = project_dir

        def on_output(line: str) -> None:
            self._push_event({"type": "output", "line": line})

        def on_step_start(step_id: int, description: str) -> None:
            self._push_event({"type": "step_start", "step_id": step_id, "description": description})

        def on_step_done(step_id: int, success: bool) -> None:
            self._push_event({"type": "step_done", "step_id": step_id, "success": success})

        def on_error(step_id: int, error: str) -> None:
            self._push_event({"type": "step_error", "step_id": step_id, "error": error})

        self._push_event({"type": "stage", "stage": "installing"})

        success = execute_steps(
            plan, project_dir, clone_url,
            on_output, on_step_start, on_step_done, on_error,
            cancel_event=self._cancel_event,
            resume_from_step=resume_step,
            skip_step_ids=skip_ids,
        )

        if self._cancel_event.is_set():
            self._push_event({"type": "stage", "stage": "cancelled"})
            return

        launch_file = generate_launcher(project_dir, plan)
        project_id = f"{owner}-{repo}"
        self._current_project_id = project_id
        update_project_status(project_id, "installed" if success else "partial")
        update_project_field(project_id, "launch_file", launch_file)

        needs_webui = detect_needs_webui(plan, project_dir)

        if not success:
            self._push_event({"type": "stage", "stage": "error", "message": "Some steps failed."})
        else:
            self._push_event({"type": "stage", "stage": "done"})

        self._push_event({
            "type": "done",
            "project_id": project_id,
            "launch_file": launch_file if success else None,
            "project_dir": project_dir,
            "notes": plan.get("notes"),
            "needs_webui": needs_webui if success else False,
        })

    # --- WebUI Generation ---

    def build_project_webui(self) -> None:
        """Start building a Gradio WebUI for the current project."""
        api_key = _get_api_key()
        if not api_key or not self._current_project_dir:
            return

        thread = threading.Thread(
            target=self._build_webui_pipeline,
            args=(api_key,),
            daemon=True,
        )
        thread.start()

    def _build_webui_pipeline(self, api_key: str) -> None:
        """Background thread: generate and install a Gradio WebUI."""
        self._push_event({"type": "webui_building"})

        project_dir = self._current_project_dir
        repo_data = self._current_repo_data
        plan = self._current_plan

        if not project_dir or not repo_data or not plan:
            self._push_event({"type": "webui_done", "success": False})
            return

        def on_output(line: str) -> None:
            self._push_event({"type": "output", "line": line})

        webui_path = build_webui(project_dir, repo_data, plan, api_key, on_output)

        if webui_path:
            webui_launcher = generate_webui_launcher(project_dir)
            self._push_event({
                "type": "webui_done",
                "webui_path": webui_path,
                "webui_launcher": webui_launcher,
                "success": True,
            })
        else:
            self._push_event({
                "type": "webui_done",
                "success": False,
            })

    # --- Project Actions ---

    def launch_project(self, project_id: str) -> None:
        """Launch a project's main script.

        Args:
            project_id: The project identifier.
        """
        projects = get_all_projects()
        for p in projects:
            if p.get("id") == project_id:
                script = p.get("launch_file") or p.get("launch_bat", "")
                if script and os.path.isfile(script):
                    launch_script(script)
                return

    def launch_webui(self, project_id: str) -> None:
        """Launch the WebUI script for a project.

        Args:
            project_id: The project identifier.
        """
        projects = get_all_projects()
        for p in projects:
            if p.get("id") == project_id:
                project_dir = p.get("project_dir", "")
                from core.platform_utils import get_script_extension
                ext = get_script_extension()
                webui_script = os.path.join(project_dir, f"launch_webui{ext}")
                if os.path.isfile(webui_script):
                    launch_script(webui_script, cwd=project_dir)
                return

    def open_folder(self, project_id: str) -> None:
        """Open a project's directory in the system file explorer.

        Args:
            project_id: The project identifier.
        """
        projects = get_all_projects()
        for p in projects:
            if p.get("id") == project_id:
                folder = p.get("project_dir", "")
                if folder and os.path.isdir(folder):
                    _open_folder_native(folder)
                return

    def remove_project(self, project_id: str) -> None:
        """Remove a project from the registry (does not delete files).

        Args:
            project_id: The project identifier.
        """
        _remove_project(project_id)


# ---------------------------------------------------------------------------
# Frontend / Icon Path Resolution
# ---------------------------------------------------------------------------

def _get_frontend_path() -> str:
    """Return the absolute path to ``frontend/index.html``."""
    return os.path.join(get_frontend_dir(), "index.html")


def _get_icon_path() -> str | None:
    """Return the absolute path to the application icon, or ``None``.

    Prefers ``.ico`` (required for Win32 ``LoadImageW``), falls back to ``.png``.
    """
    frontend_dir = get_frontend_dir()
    for ext in ("ico", "png"):
        icon = os.path.join(frontend_dir, f"icon.{ext}")
        if os.path.isfile(icon):
            return icon
    return None


# ---------------------------------------------------------------------------
# Main Entry Point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    api = API()

    icon_path = _get_icon_path()
    window_kwargs: dict[str, Any] = {
        "title": "GitInstaller",
        "url": _get_frontend_path(),
        "js_api": api,
        "width": 960,
        "height": 700,
        "min_size": (800, 600),
        "resizable": True,
        "text_select": False,
    }

    window = webview.create_window(**window_kwargs)
    api._set_window(window)

    # System tray support (optional — requires pystray)
    tray_icon = None
    try:
        import pystray
        from PIL import Image

        def _create_tray_image() -> Image.Image:
            """Create a tray icon image."""
            if icon_path:
                return Image.open(icon_path).resize((64, 64))
            # Fallback: generate a simple coloured square
            return Image.new("RGB", (64, 64), color=(74, 144, 217))

        def _on_tray_show(icon: Any, item: Any) -> None:
            if window:
                window.show()

        def _on_tray_quit(icon: Any, item: Any) -> None:
            icon.stop()
            if window:
                window.destroy()

        tray_icon = pystray.Icon(
            "GitInstaller",
            _create_tray_image(),
            "GitInstaller",
            menu=pystray.Menu(
                pystray.MenuItem("Show", _on_tray_show, default=True),
                pystray.MenuItem("Quit", _on_tray_quit),
            ),
        )

        def run_tray() -> None:
            tray_icon.run()

        tray_thread = threading.Thread(target=run_tray, daemon=True)
        tray_thread.start()

    except ImportError:
        logger.debug("pystray not installed, skipping system tray")

    def _set_window_icon_on_shown() -> None:
        """Set the window icon via Win32 API after the window is created."""
        import time
        time.sleep(0.5)  # Wait for window HWND to be available
        try:
            if not is_windows() or not icon_path:
                return
            import ctypes
            user32 = ctypes.windll.user32  # type: ignore[attr-defined]

            # Find the window by title
            hwnd = user32.FindWindowW(None, "GitInstaller")
            if not hwnd:
                return

            IMAGE_ICON = 1
            LR_LOADFROMFILE = 0x0010

            # Load the icon from file
            hicon_big = user32.LoadImageW(
                0, icon_path, IMAGE_ICON, 32, 32, LR_LOADFROMFILE,
            )
            hicon_small = user32.LoadImageW(
                0, icon_path, IMAGE_ICON, 16, 16, LR_LOADFROMFILE,
            )

            WM_SETICON = 0x0080
            ICON_BIG = 1
            ICON_SMALL = 0

            if hicon_big:
                user32.SendMessageW(hwnd, WM_SETICON, ICON_BIG, hicon_big)
            if hicon_small:
                user32.SendMessageW(hwnd, WM_SETICON, ICON_SMALL, hicon_small)
        except Exception:
            logger.debug("Failed to set window icon", exc_info=True)

    if icon_path:
        icon_thread = threading.Thread(target=_set_window_icon_on_shown, daemon=True)
        icon_thread.start()

    webview.start(debug=False)

    # Cleanup tray on exit
    if tray_icon:
        try:
            tray_icon.stop()
        except Exception:
            logger.debug("Failed to stop tray icon", exc_info=True)
