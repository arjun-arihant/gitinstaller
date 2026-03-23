"""
core/models.py — Shared typed structures for repository analysis and execution.
"""

from __future__ import annotations

from typing import Literal, NotRequired, TypedDict


ProjectType = Literal["python", "node", "unknown"]
StepType = Literal["git_clone", "venv_create", "pip_install", "npm_install", "copy_env", "custom"]


class PlanStep(TypedDict):
    """A single installation step emitted by the analyzer."""

    id: int
    type: StepType
    description: str
    command: str


class InstallationPlan(TypedDict):
    """Structured installation plan used by the app and frontend."""

    project_type: ProjectType
    entry_point: str | None
    python_version: str | None
    env_file_needed: bool
    has_webui: bool
    steps: list[PlanStep]
    launch_command: str
    notes: str | None


class RepoData(TypedDict):
    """Repository data fetched from GitHub and used for analysis."""

    owner: str
    repo: str
    description: str
    default_branch: str
    primary_language: str
    clone_url: str
    authenticated_clone_url: NotRequired[str]
    readme: str
    install_doc: str | None
    extra_files: dict[str, str]
    size_kb: int
    stars: int
    is_private: bool

