"""
app.py — PyWebView entry point, exposes Python API to JavaScript
Features: Plan review, cancel, retry/skip, tray, theme, private repos, plan caching, size estimation
"""

import os
import re
import json
import threading
import typing
import webbrowser
from datetime import datetime

import webview

from core.github_fetcher import (
    fetch_repo_data, fetch_repo_size,
    RepoNotFoundError, GitHubRateLimitError, NetworkError
)
from core.claude_analyzer import analyze_repo, AnalysisError
from core.executor import execute_steps
from core.launcher_gen import generate_launcher, generate_webui_launcher
from core.webui_gen import detect_needs_webui, build_webui
from core.platform_utils import (
    is_windows, open_folder as _open_folder_native,
    launch_script, open_url
)
from core.project_manager import (
    get_all_projects, add_project, update_project_status,
    update_project_field,
    remove_project as _remove_project,
    get_install_path as _get_install_path,
    set_install_path as _set_install_path,
    get_api_key as _get_api_key,
    set_api_key as _set_api_key,
    get_github_token as _get_github_token,
    set_github_token as _set_github_token,
    get_theme as _get_theme,
    set_theme as _set_theme,
    save_plan as _save_plan,
    load_plan as _load_plan,
)


class API:
    """All methods on this class are callable from JavaScript via window.pywebview.api"""

    def __init__(self):
        self._window: typing.Any = None
        self._current_plan: typing.Optional[dict] = None
        self._current_repo_data: typing.Optional[dict] = None
        self._current_project_dir: typing.Optional[str] = None
        self._current_project_id: typing.Optional[str] = None
        self._cancel_event: threading.Event = threading.Event()
        self._install_thread: typing.Optional[threading.Thread] = None

    def _set_window(self, window):
        self._window = window

    def _push_event(self, event: dict):
        if self._window:
            event_json = json.dumps(event, ensure_ascii=False)
            event_json_escaped = event_json.replace("\\", "\\\\").replace("'", "\\'")
            self._window.evaluate_js(f"window.onInstallEvent('{event_json_escaped}')")

    # --- Project Management ---

    def get_projects(self):
        return get_all_projects()

    def get_install_path(self):
        return _get_install_path()

    def set_install_path(self, path):
        _set_install_path(path)

    def get_api_key(self):
        return _get_api_key()

    def set_api_key(self, key):
        _set_api_key(key)

    def get_github_token(self):
        return _get_github_token()

    def set_github_token(self, token):
        _set_github_token(token)

    def get_theme(self):
        return _get_theme()

    def set_theme(self, theme):
        _set_theme(theme)

    def pick_folder(self):
        if not self._window:
            return None
        result = self._window.create_file_dialog(
            webview.FOLDER_DIALOG,
            directory=_get_install_path()
        )
        if result and len(result) > 0:
            return result[0]
        return None

    def validate_github_url(self, url):
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

    def get_current_plan(self):
        return self._current_plan

    def get_cached_plan(self, project_id):
        data = _load_plan(project_id)
        if data:
            return {
                "plan": data["plan"],
                "cached_at": data.get("cached_at", ""),
            }
        return None

    def get_repo_size(self, repo_url):
        token = _get_github_token()
        return fetch_repo_size(repo_url, token or None)

    # --- Install Pipeline (2-Stage: Fetch+Analyze → then Approve+Execute) ---

    def start_analyze(self, repo_url):
        """Stage 1: Fetch repo data and analyze with AI. Returns plan for review."""
        self._cancel_event.clear()
        thread = threading.Thread(
            target=self._analyze_pipeline,
            args=(repo_url,),
            daemon=True
        )
        thread.start()

    def _analyze_pipeline(self, repo_url):
        api_key = _get_api_key()
        if not api_key:
            self._push_event({
                "type": "stage", "stage": "error",
                "message": "OpenRouter API key not set. Please add it in Settings."
            })
            return

        github_token = _get_github_token() or None

        try:
            self._push_event({"type": "stage", "stage": "fetching"})
            repo_data = fetch_repo_data(repo_url, github_token)
            self._current_repo_data = repo_data
        except RepoNotFoundError as e:
            self._push_event({"type": "stage", "stage": "error", "message": str(e)})
            return
        except GitHubRateLimitError as e:
            self._push_event({"type": "stage", "stage": "error", "message": str(e)})
            return
        except NetworkError as e:
            self._push_event({"type": "stage", "stage": "error", "message": str(e)})
            return
        except Exception as e:
            self._push_event({"type": "stage", "stage": "error", "message": f"Error fetching repo: {e}"})
            return

        owner = repo_data["owner"]
        repo = repo_data["repo"]
        project_id = f"{owner}-{repo}"

        # Check for cached plan
        cached = _load_plan(project_id)

        try:
            self._push_event({"type": "stage", "stage": "analyzing"})
            plan = analyze_repo(repo_data, api_key)
            self._current_plan = plan

            # Cache the plan
            _save_plan(project_id, plan)

            # Get size estimate
            size_mb = None
            try:
                size_mb = repo_data.get("size_kb", 0) / 1024
                size_mb = round(size_mb, 1) if size_mb else None
            except Exception:
                pass

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

        except AnalysisError as e:
            self._push_event({"type": "stage", "stage": "error", "message": str(e)})
            return
        except Exception as e:
            self._push_event({"type": "stage", "stage": "error", "message": f"AI analysis failed: {e}"})
            return

    def approve_and_install(self, install_path):
        """Stage 2: User approved the plan — execute installation."""
        if not self._current_plan or not self._current_repo_data:
            return

        self._cancel_event.clear()
        self._install_thread = threading.Thread(
            target=self._execute_pipeline,
            args=(install_path,),
            daemon=True
        )
        self._install_thread.start()

    def _execute_pipeline(self, install_path):
        repo_data = self._current_repo_data
        plan = self._current_plan
        owner = repo_data["owner"]
        repo = repo_data["repo"]
        clone_url = repo_data["clone_url"]

        try:
            self._push_event({"type": "stage", "stage": "installing"})

            # Send plan to frontend so it can build step list + set totalSteps for progress bar
            self._push_event({"type": "plan", "plan": plan})

            project_dir = os.path.join(install_path, f"{owner}-{repo}")
            self._current_project_dir = project_dir

            def on_output(line):
                self._push_event({"type": "output", "line": line})

            def on_step_start(step_id, description):
                self._push_event({
                    "type": "step_start",
                    "step_id": step_id,
                    "description": description
                })

            def on_step_done(step_id, success):
                self._push_event({
                    "type": "step_done",
                    "step_id": step_id,
                    "success": success
                })

            def on_error(step_id, error):
                self._push_event({
                    "type": "step_error",
                    "step_id": step_id,
                    "error": error
                })

            success = execute_steps(
                plan, project_dir, clone_url,
                on_output, on_step_start, on_step_done, on_error,
                cancel_event=self._cancel_event
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
                    "message": "Installation failed or was only partially completed."
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

        except Exception as e:
            self._push_event({"type": "stage", "stage": "error", "message": f"Installation error: {e}"})

    # --- Cancel ---

    def cancel_install(self):
        self._cancel_event.set()

    # --- Retry / Skip ---

    def retry_from_step(self, step_id, install_path):
        """Retry installation from a specific step."""
        if not self._current_plan or not self._current_repo_data:
            return

        self._cancel_event.clear()
        self._install_thread = threading.Thread(
            target=self._retry_pipeline,
            args=(install_path, step_id, None),
            daemon=True
        )
        self._install_thread.start()

    def skip_and_continue(self, step_id, install_path):
        """Skip a failed step and continue with the rest."""
        if not self._current_plan or not self._current_repo_data:
            return

        self._cancel_event.clear()
        self._install_thread = threading.Thread(
            target=self._retry_pipeline,
            args=(install_path, step_id, {step_id}),
            daemon=True
        )
        self._install_thread.start()

    def _retry_pipeline(self, install_path, resume_step, skip_ids):
        repo_data = self._current_repo_data
        plan = self._current_plan
        owner = repo_data["owner"]
        repo = repo_data["repo"]
        clone_url = repo_data["clone_url"]

        project_dir = os.path.join(install_path, f"{owner}-{repo}")
        self._current_project_dir = project_dir

        def on_output(line):
            self._push_event({"type": "output", "line": line})

        def on_step_start(step_id, description):
            self._push_event({"type": "step_start", "step_id": step_id, "description": description})

        def on_step_done(step_id, success):
            self._push_event({"type": "step_done", "step_id": step_id, "success": success})

        def on_error(step_id, error):
            self._push_event({"type": "step_error", "step_id": step_id, "error": error})

        self._push_event({"type": "stage", "stage": "installing"})

        success = execute_steps(
            plan, project_dir, clone_url,
            on_output, on_step_start, on_step_done, on_error,
            cancel_event=self._cancel_event,
            resume_from_step=resume_step if not skip_ids else None,
            skip_step_ids=skip_ids
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

    def build_project_webui(self):
        api_key = _get_api_key()
        if not api_key or not self._current_project_dir:
            return

        thread = threading.Thread(
            target=self._build_webui_pipeline,
            args=(api_key,),
            daemon=True
        )
        thread.start()

    def _build_webui_pipeline(self, api_key):
        self._push_event({"type": "webui_building"})

        project_dir = self._current_project_dir
        repo_data = self._current_repo_data
        plan = self._current_plan

        def on_output(line):
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

    def launch_project(self, project_id):
        projects = get_all_projects()
        for p in projects:
            if p.get("id") == project_id:
                script = p.get("launch_file") or p.get("launch_bat", "")
                if script and os.path.isfile(script):
                    launch_script(script)
                return

    def launch_webui(self, project_id):
        """Launch the WebUI script. Browser opening is handled by the generated webui.py itself."""
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

    def open_folder(self, project_id):
        projects = get_all_projects()
        for p in projects:
            if p.get("id") == project_id:
                folder = p.get("project_dir", "")
                if folder and os.path.isdir(folder):
                    _open_folder_native(folder)
                return

    def remove_project(self, project_id):
        _remove_project(project_id)


def _get_frontend_path():
    app_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(app_dir, "frontend", "index.html")


def _get_icon_path():
    app_dir = os.path.dirname(os.path.abspath(__file__))
    # Prefer .ico (required for Win32 LoadImageW)
    for ext in ("ico", "png"):
        icon = os.path.join(app_dir, "frontend", f"icon.{ext}")
        if os.path.isfile(icon):
            return icon
    return None


if __name__ == "__main__":
    api = API()

    icon_path = _get_icon_path()
    window_kwargs = {
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

        def _create_tray_image():
            """Create a simple tray icon."""
            icon_path = _get_icon_path()
            if icon_path:
                return Image.open(icon_path).resize((64, 64))
            # Fallback: generate a simple colored square
            img = Image.new("RGB", (64, 64), color=(74, 144, 217))
            return img

        def _on_tray_show(icon, item):
            if window:
                window.show()

        def _on_tray_quit(icon, item):
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
            )
        )

        def run_tray():
            tray_icon.run()

        tray_thread = threading.Thread(target=run_tray, daemon=True)
        tray_thread.start()

    except ImportError:
        pass  # pystray not installed, skip tray

    def _set_window_icon_on_shown():
        """Set window icon via Win32 API after the window is created."""
        import time
        time.sleep(0.5)  # Wait for window HWND to be available
        try:
            from core.platform_utils import is_windows
            if not is_windows() or not icon_path:
                return
            import ctypes
            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32

            # Find the window by title
            hwnd = user32.FindWindowW(None, "GitInstaller")
            if not hwnd:
                return

            IMAGE_ICON = 1
            LR_LOADFROMFILE = 0x0010
            LR_DEFAULTSIZE = 0x0040

            # Load the icon from file
            hicon_big = user32.LoadImageW(
                0, icon_path, IMAGE_ICON, 32, 32,
                LR_LOADFROMFILE
            )
            hicon_small = user32.LoadImageW(
                0, icon_path, IMAGE_ICON, 16, 16,
                LR_LOADFROMFILE
            )

            WM_SETICON = 0x0080
            ICON_BIG = 1
            ICON_SMALL = 0

            if hicon_big:
                user32.SendMessageW(hwnd, WM_SETICON, ICON_BIG, hicon_big)
            if hicon_small:
                user32.SendMessageW(hwnd, WM_SETICON, ICON_SMALL, hicon_small)
        except Exception:
            pass  # Icon setting failed silently

    if icon_path:
        icon_thread = threading.Thread(target=_set_window_icon_on_shown, daemon=True)
        icon_thread.start()

    webview.start(debug=False)

    # Cleanup tray on exit
    if tray_icon:
        try:
            tray_icon.stop()
        except Exception:
            pass
