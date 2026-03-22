"""
core/utils.py — Shared utility functions used across multiple core modules.
"""

from __future__ import annotations


def strip_code_fences(text: str) -> str:
    """Strip markdown code fences (```...```) from AI response text.

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
