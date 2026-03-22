"""
core/claude_analyzer.py — Sends repository documentation to an AI model via OpenRouter
and returns a structured JSON installation plan.

Uses the MiMo V2 Flash model for cost-effective analysis.
"""

from __future__ import annotations

import json
import logging

import requests

from core.utils import strip_code_fences

logger = logging.getLogger(__name__)


class AnalysisError(Exception):
    """Raised when AI analysis fails or returns unparseable results."""


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Internal Helpers
# ---------------------------------------------------------------------------

def _build_user_message(repo_data: dict) -> str:
    """Construct the user message from fetched repository data.

    Args:
        repo_data: Dict returned by ``fetch_repo_data()``.

    Returns:
        A formatted string containing all relevant documentation.
    """
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


def _call_openrouter(messages: list[dict[str, str]], api_key: str) -> str:
    """Make a chat completion request to OpenRouter.

    Args:
        messages: List of message dicts with ``role`` and ``content``.
        api_key: OpenRouter API key.

    Returns:
        The assistant's response content string.

    Raises:
        AnalysisError: On network errors or unexpected response structure.
    """
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
            OPENROUTER_URL, headers=headers, json=payload, timeout=120,
        )
    except requests.RequestException as exc:
        raise AnalysisError(f"Network error calling OpenRouter: {exc}")

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
    """Fix common AI mistakes in the generated plan.

    - Strips ``&&`` chains from commands (keeps only the meaningful part).
    - Ensures ``has_webui`` field exists.
    - Injects a ``venv_create`` step for Python projects if the AI omitted it.

    Args:
        plan: The raw parsed plan dict.

    Returns:
        The corrected plan dict (modified in place and returned).
    """
    steps: list[dict] = plan.get("steps", [])

    for step in steps:
        command = step.get("command", "")
        # Strip && chains — take only the meaningful part
        if "&&" in command:
            parts = [p.strip() for p in command.split("&&")]
            # Remove cd commands, keep the rest
            meaningful = [p for p in parts if not p.lower().startswith("cd ")]
            if meaningful:
                step["command"] = meaningful[0]

    # Ensure has_webui field exists
    if "has_webui" not in plan:
        plan["has_webui"] = False

    # Force venv_create step for Python projects if AI omitted it
    if plan.get("project_type") == "python":
        has_venv = any(s.get("type") == "venv_create" for s in steps)
        if not has_venv:
            venv_step = {
                "id": 999,
                "type": "venv_create",
                "description": "Create virtual environment",
                "command": "python -m venv .venv",
            }
            # Insert after git_clone if it exists, otherwise at start
            insert_idx = 0
            for i, s in enumerate(steps):
                if s.get("type") == "git_clone":
                    insert_idx = i + 1
                    break
            steps.insert(insert_idx, venv_step)
            # Re-number step ids sequentially
            for i, s in enumerate(steps):
                s["id"] = i + 1

    return plan


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def analyze_repo(repo_data: dict, api_key: str) -> dict:
    """Analyse fetched repository data and produce a structured installation plan.

    Sends the documentation to the AI model via OpenRouter, parses the JSON
    response, and post-processes it to fix common mistakes. If the first
    response is not valid JSON, a retry is attempted.

    Args:
        repo_data: Dict returned by ``fetch_repo_data()``.
        api_key: OpenRouter API key.

    Returns:
        A validated installation plan dict.

    Raises:
        AnalysisError: If the AI response cannot be parsed after retry.
    """
    user_msg = _build_user_message(repo_data)

    messages: list[dict[str, str]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_msg},
    ]

    response_text = _call_openrouter(messages, api_key)
    cleaned = strip_code_fences(response_text)

    try:
        plan = json.loads(cleaned)
    except json.JSONDecodeError:
        logger.warning("First AI response was not valid JSON, retrying...")
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
        retry_cleaned = strip_code_fences(retry_text)

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
