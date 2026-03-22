"""
core/claude_analyzer.py — Sends docs to MiMo via OpenRouter, returns JSON step plan
"""

import json
import requests


class AnalysisError(Exception):
    """Raised when AI analysis fails or returns unparseable results."""
    pass


MIMO_MODEL = "xiaomi/mimo-v2-flash"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

SYSTEM_PROMPT = r"""You are an expert software installation assistant. Your job is to read GitHub repository documentation and produce a precise, ordered JSON installation plan for WINDOWS.

You must respond with ONLY a valid JSON object — no markdown, no code fences, no explanation, no preamble. Just the raw JSON.

The JSON must follow this exact schema:
{
  "project_type": "python" | "node" | "unknown",
  "entry_point": "<relative path to the main file to run, e.g. main.py or index.js>",
  "python_version": "<required python version string or null>",
  "env_file_needed": true | false,
  "has_webui": true | false,
  "steps": [
    {
      "id": 1,
      "type": "git_clone" | "venv_create" | "pip_install" | "npm_install" | "copy_env" | "custom",
      "description": "<human readable description of this step>",
      "command": "<exact shell command to run>"
    }
  ],
  "launch_command": "<command to launch the project from within the project dir, using the venv python if python project>",
  "notes": "<any important notes for the user, or null>"
}

CRITICAL RULES:
- The git_clone step command must be EXACTLY: git clone <clone_url>
  (Do NOT add a target directory — the system handles that automatically)
- For Python projects, always create a venv as step 2 with type "venv_create" and command: python -m venv .venv
  (The system overrides this command with the correct python path automatically)
- Each command must be a SINGLE command — absolutely NO && chaining or multiple commands
- Each step must have exactly ONE command
- If a .env.example or .env.sample file exists, include a copy_env step with command: copy .env.example .env
- Only include steps clearly supported by the documentation
- Do not include steps that require sudo, admin rights, or system-wide installs
- If you cannot determine the entry point, set entry_point to null
- Set has_webui to true if the project includes a web interface (Flask, Django, Gradio, Streamlit, FastAPI web server, etc.)
- Set has_webui to false if the project is a library, CLI tool, or has no built-in web interface"""


def _build_user_message(repo_data: dict) -> str:
    """Construct the user message from repo data."""
    parts = [
        f"Repository: {repo_data['owner']}/{repo_data['repo']}",
        f"Description: {repo_data['description']}",
        f"Primary Language: {repo_data['primary_language']}",
        f"Clone URL: {repo_data['clone_url']}",
        "",
        "README:",
        repo_data.get("readme", "(No README found)"),
    ]

    if repo_data.get("install_doc"):
        parts.append("")
        parts.append("INSTALL.md:")
        parts.append(repo_data["install_doc"])

    for fname, content in repo_data.get("extra_files", {}).items():
        parts.append("")
        parts.append(f"{fname}:")
        parts.append(content)

    return "\n".join(parts)


def _strip_fences(text: str) -> str:
    """Strip markdown code fences from AI response."""
    text = text.strip()
    if text.startswith("```"):
        first_newline = text.find("\n")
        if first_newline != -1:
            text = text[first_newline + 1:]
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3].rstrip()
    return text.strip()


def _call_openrouter(messages: list, api_key: str) -> str:
    """Make a chat completion request to OpenRouter."""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/gitinstaller",
        "X-Title": "GitInstaller",
    }

    payload = {
        "model": MIMO_MODEL,
        "messages": messages,
        "temperature": 0.1,
    }

    try:
        resp = requests.post(
            OPENROUTER_URL, headers=headers, json=payload, timeout=120
        )
    except requests.RequestException as e:
        raise AnalysisError(f"Network error calling OpenRouter: {e}")

    if resp.status_code != 200:
        raise AnalysisError(
            f"OpenRouter API error (HTTP {resp.status_code}): {resp.text[:500]}"
        )

    data = resp.json()

    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError):
        raise AnalysisError(f"Unexpected OpenRouter response structure: {json.dumps(data)[:500]}")


def _post_process_plan(plan: dict) -> dict:
    """Fix common AI mistakes in the plan."""
    steps = plan.get("steps", [])

    for step in steps:
        command = step.get("command", "")
        # Strip && chains — take only the meaningful part
        if "&&" in command:
            parts = [p.strip() for p in command.split("&&")]
            # Remove cd commands, keep the rest
            meaningful = [p for p in parts if not p.lower().startswith("cd ")]
            if meaningful:
                step["command"] = meaningful[0]  # Take the first meaningful command

    # Ensure has_webui field exists
    if "has_webui" not in plan:
        plan["has_webui"] = False

    # Force venv_create step for python projects if AI omitted it
    if plan.get("project_type") == "python":
        has_venv = any(s.get("type") == "venv_create" for s in steps)
        if not has_venv:
            venv_step = {
                "id": 999,
                "type": "venv_create",
                "description": "Create virtual environment",
                "command": "python -m venv .venv"
            }
            # Insert after git_clone if it exists, otherwise at start
            insert_idx = 0
            for i, s in enumerate(steps):
                if s.get("type") == "git_clone":
                    insert_idx = i + 1
                    break
            steps.insert(insert_idx, venv_step)
            for i, s in enumerate(steps):
                s["id"] = i + 1

    return plan


def analyze_repo(repo_data: dict, api_key: str) -> dict:
    """
    Send the fetched repo data to MiMo V2 Flash via OpenRouter and get back
    a structured JSON installation plan.
    """
    user_msg = _build_user_message(repo_data)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_msg},
    ]

    response_text = _call_openrouter(messages, api_key)
    cleaned = _strip_fences(response_text)

    try:
        plan = json.loads(cleaned)
    except json.JSONDecodeError:
        retry_messages = messages + [
            {"role": "assistant", "content": response_text},
            {
                "role": "user",
                "content": (
                    "Your previous response was not valid JSON. Return only the raw "
                    "JSON object with no markdown, no code fences, and no explanation. "
                    f"Previous response: {response_text}"
                ),
            },
        ]

        retry_text = _call_openrouter(retry_messages, api_key)
        retry_cleaned = _strip_fences(retry_text)

        try:
            plan = json.loads(retry_cleaned)
        except json.JSONDecodeError:
            raise AnalysisError(
                f"Could not parse installation plan. The README may be too ambiguous. "
                f"Raw response: {retry_text[:500]}"
            )

    if not isinstance(plan.get("steps"), list):
        raise AnalysisError(
            f"Invalid plan structure — 'steps' is not a list. "
            f"Parsed: {json.dumps(plan)[:500]}"
        )

    # Post-process to fix common AI mistakes
    plan = _post_process_plan(plan)

    return plan
