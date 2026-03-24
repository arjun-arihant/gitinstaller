"""
GitInstaller Core Package.

Modules:
    paths           — Centralised path resolution for dev and frozen builds
    platform_utils  — Cross-platform OS abstractions
    github_fetcher  — GitHub API client for repository data
    claude_analyzer — AI-powered installation plan generation
    executor        — Sequential step execution engine
    launcher_gen    — Launch script generation
    webui_gen       — Gradio WebUI generation
    project_manager — Persistent state management
    utils           — Shared utility functions
    version         — Application version string
"""

from . import (
    claude_analyzer,
    executor,
    github_fetcher,
    launcher_gen,
    models,
    paths,
    platform_utils,
    project_manager,
    utils,
    version,
    webui_gen,
)

__all__ = [
    "paths",
    "platform_utils",
    "github_fetcher",
    "claude_analyzer",
    "executor",
    "launcher_gen",
    "webui_gen",
    "project_manager",
    "utils",
    "models",
    "version",
]
