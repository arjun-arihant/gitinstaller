"""
core/webui_gen.py — Detects if a project needs a WebUI and generates a Gradio interface
Loads design.md for consistent theming. Auto-opens browser on launch.
"""

import os
import json
import subprocess
import sys
import requests

from core.platform_utils import is_windows, get_venv_pip


WEBUI_INDICATORS = [
    "flask", "django", "fastapi", "streamlit", "gradio",
    "uvicorn", "gunicorn", "dash", "nicegui", "panel",
    "app.py", "server.py", "web.py", "webapp.py",
]


def _get_app_dir():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_design_spec():
    """Load the design.md specification file."""
    design_path = os.path.join(_get_app_dir(), "data", "design.md")
    if os.path.isfile(design_path):
        try:
            with open(design_path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception:
            pass
    return ""


def detect_needs_webui(plan, project_dir):
    if plan.get("has_webui", False):
        return False

    project_type = plan.get("project_type", "unknown")
    if project_type == "node":
        return False

    launch_cmd = (plan.get("launch_command") or "").lower()
    for indicator in WEBUI_INDICATORS:
        if indicator in launch_cmd:
            return False

    entry_point = (plan.get("entry_point") or "").lower()
    if entry_point in ("app.py", "server.py", "web.py", "main.py"):
        pass

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
                    pass

    if project_type == "python":
        return True

    return False


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


def _strip_code_fences(text):
    text = text.strip()
    if text.startswith("```"):
        first_newline = text.find("\n")
        if first_newline != -1:
            text = text[first_newline + 1:]
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3].rstrip()
    return text.strip()


def generate_webui_code(repo_data, plan, api_key):
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
            OPENROUTER_URL, headers=headers, json=payload, timeout=120
        )
        if resp.status_code != 200:
            raise Exception(f"OpenRouter error: {resp.status_code}")

        data = resp.json()
        code = data["choices"][0]["message"]["content"]
        code = _strip_code_fences(code)
        return code

    except Exception:
        return _generate_fallback_webui(project_name, repo_data.get("description", ""))


def _generate_fallback_webui(project_name, description):
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


def install_gradio_in_venv(project_dir, on_output=None):
    pip_exe = get_venv_pip(project_dir)
    if not os.path.isfile(pip_exe):
        pip_exe = "pip"

    cmd = f'"{pip_exe}" install gradio'

    if on_output:
        on_output(f"$ {cmd}\n")

    try:
        proc = subprocess.Popen(
            cmd,
            cwd=project_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            shell=True,
        )

        for line in proc.stdout:
            line = line.rstrip("\n\r")
            if on_output:
                on_output(line + "\n")

        proc.wait()
        return proc.returncode == 0

    except Exception as e:
        if on_output:
            on_output(f"Error installing gradio: {e}\n")
        return False


def build_webui(project_dir, repo_data, plan, api_key, on_output=None):
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
    except Exception as e:
        if on_output:
            on_output(f"Error writing webui.py: {e}\n")
        return ""

    if on_output:
        on_output("Installing Gradio...\n")

    success = install_gradio_in_venv(project_dir, on_output)

    if not success:
        if on_output:
            on_output("Warning: Gradio installation may have failed. The webui.py was still created.\n")

    return webui_path
