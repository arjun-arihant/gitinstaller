"""
core/webui_gen.py — Detects if a project needs a WebUI and generates a Gradio interface.

Loads ``data/design.md`` for consistent theming. Auto-opens browser on launch.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
from typing import Callable

import requests

from core.models import InstallationPlan, RepoData
from core.paths import get_design_spec_path
from core.platform_utils import is_windows, get_venv_pip
from core.utils import strip_code_fences

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

WEBUI_INDICATORS = [
    "flask", "django", "fastapi", "streamlit", "gradio",
    "uvicorn", "gunicorn", "dash", "nicegui", "panel",
    "app.py", "server.py", "web.py", "webapp.py",
]


# ---------------------------------------------------------------------------
# Design Spec Loader
# ---------------------------------------------------------------------------

def _load_design_spec() -> str:
    """Load the ``data/design.md`` specification file for WebUI theming.

    Returns:
        The design spec contents, or an empty string if unavailable.
    """
    design_path = get_design_spec_path()
    if os.path.isfile(design_path):
        try:
            with open(design_path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception:
            logger.warning("Failed to read design spec at %s", design_path, exc_info=True)
    return ""


# ---------------------------------------------------------------------------
# WebUI Detection
# ---------------------------------------------------------------------------

def detect_needs_webui(plan: InstallationPlan, project_dir: str) -> bool:
    """Determine whether a project would benefit from a generated Gradio WebUI.

    Returns ``False`` if the project already has a web interface, is a Node
    project, or if web-related indicators are found in the launch command or
    source files. Returns ``True`` only for Python projects that appear to
    lack a web interface.

    Args:
        plan: The installation plan dict.
        project_dir: Absolute path to the installed project directory.
    """
    if plan.get("has_webui", False):
        return False

    project_type = plan.get("project_type", "unknown")
    if project_type == "node":
        return False

    launch_cmd = (plan.get("launch_command") or "").lower()
    for indicator in WEBUI_INDICATORS:
        if indicator in launch_cmd:
            return False

    # Scan key source files for web framework imports
    if os.path.isdir(project_dir):
        for fname in os.listdir(project_dir):
            fl = fname.lower()
            if fl in ("app.py", "server.py", "wsgi.py"):
                fpath = os.path.join(project_dir, fname)
                try:
                    with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                        content = f.read(5000).lower()
                        for indicator in WEBUI_INDICATORS:
                            if indicator in content:
                                return False
                except Exception:
                    logger.debug("Failed to scan %s for web indicators", fpath, exc_info=True)

    if project_type == "python":
        return True

    return False


# ---------------------------------------------------------------------------
# WebUI Code Generation
# ---------------------------------------------------------------------------

WEBUI_SYSTEM_PROMPT = r"""You are an expert Python developer. Your job is to create a Gradio web interface for a GitHub project.

You must respond with ONLY valid Python code — no markdown, no code fences, no explanation. Just the raw Python code.

The code MUST:
1. Import gradio as gr
2. Import the project's main module/package
3. Create a Gradio interface that demonstrates the project's core functionality
4. Use gr.Blocks() with the EXACT theme provided in the design specification below
5. Include a title heading and description using gr.Markdown
6. Include the GitInstaller branding footer as specified in the design spec
7. Launch with share=False, server_name="127.0.0.1"
8. Auto-open the browser using webbrowser.open() in a threading.Timer
9. Be a complete, runnable Python script
10. Handle imports gracefully — if the project can't be imported, show an error message
11. Keep it functional — focus on the main use case from the README

IMPORTANT: The script must include this auto-launch pattern:
```python
import webbrowser
import threading
threading.Timer(1.5, lambda: webbrowser.open("http://127.0.0.1:7860")).start()
demo.launch(share=False, server_name="127.0.0.1")
```

{design_spec}"""


def generate_webui_code(repo_data: RepoData, plan: InstallationPlan, api_key: str) -> str:
    """Generate Gradio WebUI Python code for a project using AI.

    Falls back to a generic template if the AI call fails.

    Args:
        repo_data: Dict returned by ``fetch_repo_data()``.
        plan: The installation plan dict.
        api_key: OpenRouter API key.

    Returns:
        Python source code string for the WebUI.
    """
    from core.claude_analyzer import MIMO_MODEL, OPENROUTER_URL

    design_spec = _load_design_spec()
    system_prompt = WEBUI_SYSTEM_PROMPT.replace("{design_spec}", design_spec)

    readme = repo_data.get("readme", "(No README)")
    entry_point = plan.get("entry_point", "unknown")
    project_name = repo_data.get("repo", "project")

    user_msg = f"""Create a Gradio web UI for this project:

Project: {repo_data.get('owner', '')}/{project_name}
Description: {repo_data.get('description', '')}
Primary Language: {repo_data.get('primary_language', '')}
Entry Point: {entry_point}
Project Type: {plan.get('project_type', 'unknown')}

README:
{readme[:4000]}

Extra files found:
{json.dumps(list(repo_data.get('extra_files', {}).keys()))}

Generate a webui.py that creates a themed Gradio interface following the design specification provided in the system prompt."""

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/gitinstaller",
        "X-Title": "GitInstaller",
    }

    payload = {
        "model": MIMO_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_msg},
        ],
        "temperature": 0.2,
    }

    try:
        resp = requests.post(
            OPENROUTER_URL, headers=headers, json=payload, timeout=120,
        )
        if resp.status_code != 200:
            raise RuntimeError(f"OpenRouter error: {resp.status_code}")

        data = resp.json()
        code = data["choices"][0]["message"]["content"]
        code = strip_code_fences(code)
        return code

    except Exception:
        logger.warning(
            "AI WebUI generation failed, using fallback template",
            exc_info=True,
        )
        return _generate_fallback_webui(project_name, repo_data.get("description", ""))


def _generate_fallback_webui(project_name: str, description: str) -> str:
    """Generate a generic fallback Gradio WebUI template.

    Note: The fallback UI provides a command runner interface. This is
    intentionally limited to the project directory context.

    Args:
        project_name: Display name for the project.
        description: Short project description.

    Returns:
        Python source code string.
    """
    return f'''import gradio as gr
import subprocess
import webbrowser
import threading

def run_command(command):
    """Run a shell command and return output."""
    try:
        result = subprocess.run(
            command, shell=True, capture_output=True, text=True, timeout=60
        )
        output = result.stdout
        if result.stderr:
            output += "\\n\\nSTDERR:\\n" + result.stderr
        return output if output.strip() else "Command completed successfully (no output)"
    except subprocess.TimeoutExpired:
        return "Command timed out after 60 seconds"
    except Exception as e:
        return f"Error: {{e}}"

theme = gr.themes.Base(
    primary_hue=gr.themes.Color(
        c50="#e8f0fe", c100="#d0e1fc", c200="#a1c3f9",
        c300="#72a5f6", c400="#4A90D9", c500="#4A90D9",
        c600="#3b7ac4", c700="#2c64af", c800="#1d4e9a",
        c900="#0e3885", c950="#072260"
    ),
    neutral_hue=gr.themes.Color(
        c50="#e1e2e6", c100="#c3c5cc", c200="#909296",
        c300="#6b6d72", c400="#55565c", c500="#44454b",
        c600="#3a3b41", c700="#2c2d33", c800="#25262b",
        c900="#1a1b1e", c950="#111113"
    ),
    font=["-apple-system", "BlinkMacSystemFont", "Segoe UI", "Roboto", "sans-serif"],
    font_mono=["Cascadia Code", "Consolas", "Fira Code", "monospace"],
).set(
    body_background_fill="#1a1b1e",
    body_background_fill_dark="#1a1b1e",
    block_background_fill="#25262b",
    block_background_fill_dark="#25262b",
    block_border_color="#3a3b41",
    block_border_color_dark="#3a3b41",
    block_label_text_color="#909296",
    block_label_text_color_dark="#909296",
    block_title_text_color="#e1e2e6",
    block_title_text_color_dark="#e1e2e6",
    input_background_fill="#2c2d33",
    input_background_fill_dark="#2c2d33",
    input_border_color="#3a3b41",
    input_border_color_dark="#3a3b41",
    button_primary_background_fill="#4A90D9",
    button_primary_background_fill_dark="#4A90D9",
    button_primary_text_color="#ffffff",
    button_primary_text_color_dark="#ffffff",
    border_color_primary="#3a3b41",
    border_color_primary_dark="#3a3b41",
)

with gr.Blocks(title="{project_name} — GitInstaller", theme=theme) as demo:
    gr.Markdown("# {project_name}")
    gr.Markdown("{description}")

    with gr.Row():
        with gr.Column():
            cmd_input = gr.Textbox(
                label="Command",
                placeholder="Enter a command to run...",
                lines=2
            )
            run_btn = gr.Button("Run", variant="primary")

        with gr.Column():
            output = gr.Textbox(label="Output", lines=15, interactive=False)

    run_btn.click(fn=run_command, inputs=[cmd_input], outputs=[output])

    gr.Markdown(
        "<center style=\'color: #6b6d72; font-size: 12px; margin-top: 16px;\'>"
        "Built with <a href=\'https://github.com/arjun-arihant/gitinstaller\' "
        "style=\'color: #4A90D9; text-decoration: none;\'>GitInstaller</a>"
        "</center>"
    )

threading.Timer(1.5, lambda: webbrowser.open("http://127.0.0.1:7860")).start()
demo.launch(share=False, server_name="127.0.0.1")
'''


# ---------------------------------------------------------------------------
# Gradio Installation
# ---------------------------------------------------------------------------

def install_gradio_in_venv(
    project_dir: str,
    on_output: Callable[[str], None] | None = None,
) -> bool:
    """Install Gradio into the project's virtual environment.

    Args:
        project_dir: Absolute path to the project directory.
        on_output: Optional callback for streaming install output.

    Returns:
        ``True`` if installation succeeded, ``False`` otherwise.
    """
    pip_exe = get_venv_pip(project_dir)
    if not os.path.isfile(pip_exe):
        pip_exe = "pip"

    cmd = f'"{pip_exe}" install gradio'

    if on_output:
        on_output(f"$ {cmd}\n")

    try:
        from core.executor import _get_bundled_git_dir, _get_bundled_node_dir, _get_bundled_python
        from core.platform_utils import build_env
        from core.paths import get_bundled_dir

        bundled_python_dir = os.path.dirname(_get_bundled_python())
        bundled_git_dir = _get_bundled_git_dir()
        bundled_node_dir = _get_bundled_node_dir()

        extra_git_dirs: list[str] = []
        if bundled_git_dir and is_windows():
            git_base = os.path.join(get_bundled_dir(), "git")
            for sub in ("mingw64\\bin", "mingw64\\libexec\\git-core", "usr\\bin"):
                candidate = os.path.join(git_base, sub)
                if os.path.isdir(candidate) and candidate != bundled_git_dir:
                    extra_git_dirs.append(candidate)

        env = build_env(project_dir, bundled_python_dir, bundled_git_dir, bundled_node_dir)

        if extra_git_dirs:
            sep = ";" if is_windows() else ":"
            current_path = env.get("PATH", "")
            git_extras = sep.join(extra_git_dirs)
            if bundled_git_dir and bundled_git_dir in current_path:
                env["PATH"] = current_path.replace(
                    bundled_git_dir,
                    f"{bundled_git_dir}{sep}{git_extras}",
                )
            else:
                env["PATH"] = f"{git_extras}{sep}{current_path}"

        proc = subprocess.Popen(
            cmd,
            cwd=project_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            shell=True,
            env=env,
        )

        for line in proc.stdout:  # type: ignore[union-attr]
            line = line.rstrip("\n\r")
            if on_output:
                on_output(f"{line}\n")

        proc.wait()
        return proc.returncode == 0

    except Exception as exc:
        logger.error("Error installing gradio: %s", exc, exc_info=True)
        if on_output:
            on_output(f"Error installing gradio: {exc}\n")
        return False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_webui(
    project_dir: str,
    repo_data: RepoData,
    plan: InstallationPlan,
    api_key: str,
    on_output: Callable[[str], None] | None = None,
) -> str:
    """Generate and install a Gradio WebUI for a project.

    Args:
        project_dir: Absolute path to the project directory.
        repo_data: Dict returned by ``fetch_repo_data()``.
        plan: The installation plan dict.
        api_key: OpenRouter API key.
        on_output: Optional callback for streaming progress output.

    Returns:
        Absolute path to the generated ``webui.py``, or empty string on failure.
    """
    if on_output:
        on_output("Generating Gradio web UI code...\n")

    code = generate_webui_code(repo_data, plan, api_key)

    if not code:
        if on_output:
            on_output("Failed to generate web UI code.\n")
        return ""

    webui_path = os.path.join(project_dir, "webui.py")
    try:
        with open(webui_path, "w", encoding="utf-8") as f:
            f.write(code)
        if on_output:
            on_output(f"Created {webui_path}\n")
    except Exception as exc:
        logger.error("Error writing webui.py: %s", exc, exc_info=True)
        if on_output:
            on_output(f"Error writing webui.py: {exc}\n")
        return ""

    if on_output:
        on_output("Installing Gradio...\n")

    success = install_gradio_in_venv(project_dir, on_output)

    if not success:
        if on_output:
            on_output("Warning: Gradio installation may have failed. The webui.py was still created.\n")

    return webui_path
