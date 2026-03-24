"""
core/utils.py — Shared utility functions used across multiple core modules.
"""

from __future__ import annotations

import re


def strip_code_fences(text: str) -> str:
    r"""Strip markdown code fences from AI response text.

    Args:
        text: Raw text that may be wrapped in markdown code fences.

    Returns:
        The text with leading/trailing code fences removed.
    """
    text = text.strip()
    if text.startswith("```"):
        first_newline = text.find("\n")
        if first_newline != -1:
            text = text[first_newline + 1:]
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3].rstrip()
    return text.strip()


def parse_github_url(url: str) -> tuple[bool, str, str]:
    """Parse a GitHub URL or shorthand into (valid, owner, repo).

    Accepts:
    - ``owner/repo``
    - ``https://github.com/owner/repo``
    - ``https://github.com/owner/repo.git``
    - ``https://github.com/owner/repo/tree/branch/...``

    Args:
        url: The raw URL or shorthand string.

    Returns:
        A ``(valid, owner, repo)`` tuple. If parsing fails, ``valid`` is
        ``False`` and owner/repo are empty strings.
    """
    url = url.strip().rstrip("/")

    # Accept shorthand owner/repo
    shorthand = re.match(r"^([a-zA-Z0-9_.-]+)/([a-zA-Z0-9_.-]+)$", url)
    if shorthand:
        return True, shorthand.group(1), shorthand.group(2)

    pattern = r"(?:https?://)?github\.com/([^/]+)/([^/.]+?)(?:\.git)?(?:/.*)?$"
    match = re.match(pattern, url)
    if match:
        return True, match.group(1), match.group(2)

    return False, "", ""
