"""
app.py — PyWebView entry point, exposes Python API to JavaScript
"""

import os
import re
import json
import threading
import subprocess
import typing
from datetime import datetime

import webview

from core.github_fetcher import fetch_repo_data, RepoNotFoundError, GitHubRateLimitError, NetworkError
from core.claude_analyzer import analyze_repo, AnalysisError
from core.executor import execute_steps
from core.launcher_gen import generate_launcher, generate_webui_launcher
from core.webui_gen import detect_needs_webui, build_webui
from core.project_manager import (
    get_all_projects, add_project, update_project_status,
    remove_project as _remove_project, get_install_path as _get_install_path,
    set_install_path as _set_install_path, get_api_key as _get_api_key,
    set_api_key as _set_api_key
)


class API:
    """All methods on this class are callable from JavaScript via window.pywebview.api"""

    def __init__(self):
        self._window: typing.Any = None
        self._current_plan: typing.Optional[dict] = None
        self._current_repo_data: typing.Optional[dict] = None
        self._current_project_dir: typing.Optional[str] = None
        self._current_project_id: typing.Optional[str] = None

    def _set_window(self, window):
        self._window = window

    def _push_event(self, event: dict):
        """Push a JSON event to the frontend via evaluate_js."""
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
        pattern = r"(?:https?://)?github\.com/([^/]+)/([^/.]+?)(?:\.git)?(?:/.*)?$"
        match = re.match(pattern, url.strip())
        if match:
            return {"valid": True, "owner": match.group(1), "repo": match.group(2)}
        return {"valid": False, "owner": "", "repo": ""}

    def get_current_plan(self):
        return self._current_plan

    # --- Install Pipeline ---

    def start_install(self, repo_url, install_path):
        """Starts full install pipeline in background thread."""
        api_key = _get_api_key()
        if not api_key:
            self._push_event({
                "type": "stage", "stage": "error",
                "message": "OpenRouter API key not set. Please add it in Settings."
            })
            return

        thread = threading.Thread(
            target=self._install_pipeline,
            args=(repo_url, install_path, api_key),
            daemon=True
        )
        thread.start()

    def _install_pipeline(self, repo_url, install_path, api_key):
        """Run the full install pipeline."""
        try:
            # Stage 1: Fetch
            self._push_event({"type": "stage", "stage": "fetching"})
            repo_data = fetch_repo_data(repo_url)
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
        clone_url = repo_data["clone_url"]

        try:
            # Stage 2: Analyze
            self._push_event({"type": "stage", "stage": "analyzing"})
            plan = analyze_repo(repo_data, api_key)
            self._current_plan = plan

            self._push_event({"type": "plan", "plan": plan})

        except AnalysisError as e:
            self._push_event({"type": "stage", "stage": "error", "message": str(e)})
            return
        except Exception as e:
            self._push_event({"type": "stage", "stage": "error", "message": f"AI analysis failed: {e}"})
            return

        try:
            # Stage 3: Execute
            self._push_event({"type": "stage", "stage": "installing"})

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
                on_output, on_step_start, on_step_done, on_error
            )

            # Stage 4: Generate launcher
            launch_bat = generate_launcher(project_dir, plan)

            # Stage 5: Register project
            project_id = f"{owner}-{repo}"
            self._current_project_id = project_id
            project_metadata = {
                "id": project_id,
                "name": repo,
                "owner": owner,
                "description": repo_data.get("description", ""),
                "project_dir": project_dir,
                "launch_bat": launch_bat,
                "installed_at": datetime.now().isoformat(),
                "status": "installed" if success else "partial",
            }
            add_project(project_metadata)
            _set_install_path(install_path)

            # Stage 6: Check if WebUI is needed
            needs_webui = detect_needs_webui(plan, project_dir)

            # Done
            if not success:
                self._push_event({"type": "stage", "stage": "error", "message": "Installation failed or was only partially completed."})
            else:
                self._push_event({"type": "stage", "stage": "done"})
                
            self._push_event({
                "type": "done",
                "project_id": project_id,
                "launch_bat": launch_bat if success else None,
                "project_dir": project_dir,
                "notes": plan.get("notes"),
                "needs_webui": needs_webui if success else False,
            })

        except Exception as e:
            self._push_event({"type": "stage", "stage": "error", "message": f"Installation error: {e}"})

    # --- WebUI Generation ---

    def build_project_webui(self):
        """Build a Gradio WebUI for the current project in background thread."""
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
        """Generate and install Gradio WebUI."""
        self._push_event({"type": "webui_building"})

        project_dir = self._current_project_dir
        repo_data = self._current_repo_data
        plan = self._current_plan

        def on_output(line):
            self._push_event({"type": "output", "line": line})

        webui_path = build_webui(project_dir, repo_data, plan, api_key, on_output)

        if webui_path:
            # Generate webui launcher bat
            webui_bat = generate_webui_launcher(project_dir)

            self._push_event({
                "type": "webui_done",
                "webui_path": webui_path,
                "webui_bat": webui_bat,
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
                bat = p.get("launch_bat", "")
                if bat and os.path.isfile(bat):
                    subprocess.Popen(
                        ["cmd", "/c", "start", "", bat],
                        shell=True,
                        cwd=os.path.dirname(bat)
                    )
                return

    def launch_webui(self, project_id):
        """Launch the WebUI for a project."""
        projects = get_all_projects()
        for p in projects:
            if p.get("id") == project_id:
                project_dir = p.get("project_dir", "")
                webui_bat = os.path.join(project_dir, "launch_webui.bat")
                if os.path.isfile(webui_bat):
                    subprocess.Popen(
                        ["cmd", "/c", "start", "", webui_bat],
                        shell=True,
                        cwd=project_dir
                    )
                return

    def open_folder(self, project_id):
        projects = get_all_projects()
        for p in projects:
            if p.get("id") == project_id:
                folder = p.get("project_dir", "")
                if folder and os.path.isdir(folder):
                    subprocess.Popen(["explorer", folder])
                return

    def remove_project(self, project_id):
        _remove_project(project_id)


def _get_frontend_path():
    app_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(app_dir, "frontend", "index.html")


if __name__ == "__main__":
    api = API()
    window = webview.create_window(
        "GitInstaller",
        _get_frontend_path(),
        js_api=api,
        width=900,
        height=650,
        resizable=False,
        text_select=False
    )
    api._set_window(window)
    webview.start(debug=False)
