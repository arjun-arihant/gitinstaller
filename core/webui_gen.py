"""
core/webui_gen.py — Detects if a project needs a WebUI and generates a Gradio interface
"""

import os
import json
import subprocess
import sys
import requests


WEBUI_INDICATORS = [
    "flask", "django", "fastapi", "streamlit", "gradio",
    "uvicorn", "gunicorn", "dash", "nicegui", "panel",
    "app.py", "server.py", "web.py", "webapp.py",
]


def detect_needs_webui(plan: dict, project_dir: str) -> bool:
    """
    Check if a project could benefit from a Gradio web UI.
    Returns True if the project has no built-in web interface.
    """
    # Check the AI's assessment
    if plan.get("has_webui", False):
        return False

    project_type = plan.get("project_type", "unknown")

    # Node projects typically have their own frontend
    if project_type == "node":
        return False

    # Check launch command for web framework indicators
    launch_cmd = (plan.get("launch_command") or "").lower()
    for indicator in WEBUI_INDICATORS:
        if indicator in launch_cmd:
            return False

    # Check if entry point suggests a web app
    entry_point = (plan.get("entry_point") or "").lower()
    if entry_point in ("app.py", "server.py", "web.py", "main.py"):
        # Could be a web app — check files in project dir
        pass

    # Check for web framework files in the project
    if os.path.isdir(project_dir):
        for fname in os.listdir(project_dir):
            fl = fname.lower()
            if fl in ("app.py", "server.py", "wsgi.py"):
                # Read the file and check for web framework imports
                fpath = os.path.join(project_dir, fname)
                try:
                    with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                        content = f.read(5000).lower()
                        for indicator in WEBUI_INDICATORS:
                            if indicator in content:
                                return False
                except Exception:
                    pass

    # If it's a Python project (library/CLI) with no web UI detected, offer one
    if project_type == "python":
        return True

    return False


WEBUI_SYSTEM_PROMPT = r"""You are an expert Python developer. Your job is to create a simple, functional Gradio web interface for a GitHub project.

You must respond with ONLY valid Python code — no markdown, no code fences, no explanation. Just the raw Python code.

The code should:
1. Import gradio as gr
2. Import the project's main module/package
3. Create a simple Gradio interface that demonstrates the project's core functionality
4. Use gr.Blocks() for the layout
5. Include a title and description
6. Launch with share=False and server_name="127.0.0.1"
7. Be a complete, runnable Python script saved as webui.py in the project root
8. Handle imports gracefully — if the project can't be imported, show an error message
9. Keep it simple but functional — focus on the main use case from the README

IMPORTANT: The script must work from the project's root directory with the project's virtual environment activated."""


def _strip_code_fences(text: str) -> str:
    """Strip markdown code fences from AI response."""
    text = text.strip()
    if text.startswith("```"):
        first_newline = text.find("\n")
        if first_newline != -1:
            text = text[first_newline + 1:]
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3].rstrip()
    return text.strip()


def generate_webui_code(repo_data: dict, plan: dict, api_key: str) -> str:
    """
    Use AI to generate a Gradio web UI script for the project.
    Returns the generated Python code as a string.
    """
    from core.claude_analyzer import MIMO_MODEL, OPENROUTER_URL

    # Build context about the project
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

Generate a webui.py that creates a Gradio interface for the main functionality described in the README."""

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/gitinstaller",
        "X-Title": "GitInstaller",
    }

    payload = {
        "model": MIMO_MODEL,
        "messages": [
            {"role": "system", "content": WEBUI_SYSTEM_PROMPT},
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

    except Exception as e:
        # Fallback: generate a basic template
        return _generate_fallback_webui(project_name, repo_data.get("description", ""))


def _generate_fallback_webui(project_name: str, description: str) -> str:
    """Generate a basic fallback Gradio UI when AI generation fails."""
    return f'''import gradio as gr
import subprocess
import sys

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

with gr.Blocks(title="{project_name} Web UI", theme=gr.themes.Soft()) as demo:
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

demo.launch(share=False, server_name="127.0.0.1")
'''


def install_gradio_in_venv(project_dir: str, on_output=None) -> bool:
    """Install gradio into the project's virtual environment."""
    pip_exe = os.path.join(project_dir, ".venv", "Scripts", "pip.exe")

    if not os.path.isfile(pip_exe):
        # Try system pip as fallback
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


def build_webui(project_dir: str, repo_data: dict, plan: dict, api_key: str,
                on_output=None) -> str:
    """
    Full pipeline: generate webui code, install gradio, write webui.py.
    Returns path to webui.py on success, empty string on failure.
    """
    if on_output:
        on_output("Generating Gradio web UI code...\n")

    # Generate the code
    code = generate_webui_code(repo_data, plan, api_key)

    if not code:
        if on_output:
            on_output("Failed to generate web UI code.\n")
        return ""

    # Write webui.py
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

    # Install gradio
    if on_output:
        on_output("Installing Gradio...\n")

    success = install_gradio_in_venv(project_dir, on_output)

    if not success:
        if on_output:
            on_output("Warning: Gradio installation may have failed. The webui.py was still created.\n")

    return webui_path
