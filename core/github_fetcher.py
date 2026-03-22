"""
core/github_fetcher.py — Fetches README and relevant files from the GitHub API.

Supports authenticated requests (private repos via GitHub token) and
repository size estimation.
"""

from __future__ import annotations

import base64
import logging
import re

import requests

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Custom Exceptions
# ---------------------------------------------------------------------------

class RepoNotFoundError(Exception):
    """Raised when the target repository does not exist or is inaccessible."""


class GitHubRateLimitError(Exception):
    """Raised when the GitHub API rate limit has been exceeded."""


class NetworkError(Exception):
    """Raised on network-level failures (timeout, connection error, unexpected HTTP status)."""


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

GITHUB_API = "https://api.github.com"

EXTRA_FILES = [
    "INSTALL.md", "INSTALL.txt", "install.md",
    "CONTRIBUTING.md",
    "requirements.txt", "requirements-dev.txt",
    "package.json",
    "Cargo.toml",
    "pyproject.toml",
    "setup.py", "setup.cfg",
    ".env.example", ".env.sample",
]


# ---------------------------------------------------------------------------
# Internal Helpers
# ---------------------------------------------------------------------------

def _parse_repo_url(repo_url: str) -> tuple[str, str]:
    """Extract ``(owner, repo)`` from a GitHub URL or shorthand.

    Accepts:
    - ``owner/repo``
    - ``https://github.com/owner/repo``
    - ``https://github.com/owner/repo.git``

    Args:
        repo_url: The raw URL or shorthand string.

    Returns:
        A ``(owner, repo)`` tuple.

    Raises:
        ValueError: If the URL cannot be parsed.
    """
    repo_url = repo_url.strip().rstrip("/")

    # Handle shorthand "owner/repo"
    shorthand = re.match(r"^([a-zA-Z0-9_.-]+)/([a-zA-Z0-9_.-]+)$", repo_url)
    if shorthand:
        return shorthand.group(1), shorthand.group(2)

    patterns = [
        r"(?:https?://)?github\.com/([^/]+)/([^/.]+?)(?:\.git)?(?:/.*)?$",
    ]
    for pattern in patterns:
        match = re.match(pattern, repo_url)
        if match:
            return match.group(1), match.group(2)

    raise ValueError(f"Could not parse GitHub URL: {repo_url}")


def _build_headers(github_token: str | None = None) -> dict[str, str]:
    """Build HTTP headers for GitHub API requests.

    Args:
        github_token: Optional personal access token for authentication.
    """
    headers = {"Accept": "application/vnd.github.v3+json"}
    if github_token:
        headers["Authorization"] = f"token {github_token}"
    return headers


def _api_get(endpoint: str, github_token: str | None = None) -> dict | list:
    """Perform a GET request against the GitHub API.

    Args:
        endpoint: API path (e.g. ``/repos/owner/repo``).
        github_token: Optional authentication token.

    Returns:
        Parsed JSON response.

    Raises:
        RepoNotFoundError: On HTTP 404.
        GitHubRateLimitError: On HTTP 403 with exhausted rate limit.
        NetworkError: On any other HTTP or connection error.
    """
    url = f"{GITHUB_API}{endpoint}"
    headers = _build_headers(github_token)
    try:
        resp = requests.get(url, headers=headers, timeout=30)
    except requests.ConnectionError:
        raise NetworkError("Network error. Check your internet connection.")
    except requests.Timeout:
        raise NetworkError("Request timed out. Check your internet connection.")
    except requests.RequestException as exc:
        raise NetworkError(f"Network error: {exc}")

    if resp.status_code == 404:
        raise RepoNotFoundError("Repository not found. Check the URL and try again.")
    if resp.status_code == 403:
        remaining = resp.headers.get("X-RateLimit-Remaining", "0")
        if remaining == "0":
            raise GitHubRateLimitError("GitHub rate limit hit. Please wait a few minutes.")
        raise NetworkError(f"GitHub API returned 403: {resp.text[:200]}")
    if resp.status_code == 401:
        raise NetworkError("GitHub authentication failed. Check your token in Settings.")
    if resp.status_code != 200:
        raise NetworkError(f"GitHub API returned {resp.status_code}: {resp.text[:200]}")

    return resp.json()


def _decode_content(content_b64: str) -> str:
    """Decode a base64-encoded file content string from the GitHub API.

    Args:
        content_b64: Base64-encoded content.

    Returns:
        Decoded UTF-8 string, or empty string on failure.
    """
    try:
        return base64.b64decode(content_b64).decode("utf-8", errors="replace")
    except Exception:
        logger.debug("Failed to decode base64 content", exc_info=True)
        return ""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def fetch_repo_size(repo_url: str, github_token: str | None = None) -> float | None:
    """Fetch the repository size from the GitHub API.

    Args:
        repo_url: GitHub repository URL or shorthand.
        github_token: Optional authentication token.

    Returns:
        Size in MB as a float, or ``None`` on failure.
    """
    try:
        owner, repo = _parse_repo_url(repo_url)
        meta = _api_get(f"/repos/{owner}/{repo}", github_token)
        if isinstance(meta, dict):
            size_kb = meta.get("size", 0)
            return round(size_kb / 1024, 1)
        return None
    except Exception:
        logger.debug("Failed to fetch repo size for %s", repo_url, exc_info=True)
        return None


def fetch_repo_data(repo_url: str, github_token: str | None = None) -> dict:
    """Fetch all documentation files needed to understand a repository's setup.

    Retrieves the README, INSTALL docs, dependency manifests, and other
    relevant files from the GitHub API.

    Args:
        repo_url: GitHub repository URL or shorthand.
        github_token: Optional authentication token.

    Returns:
        A dict containing ``owner``, ``repo``, ``description``, ``clone_url``,
        ``readme``, ``install_doc``, ``extra_files``, ``size_kb``, ``stars``, etc.

    Raises:
        RepoNotFoundError: If the repository does not exist.
        GitHubRateLimitError: If the rate limit is exceeded.
        NetworkError: On network failures.
        ValueError: If the URL cannot be parsed.
    """
    owner, repo = _parse_repo_url(repo_url)

    meta = _api_get(f"/repos/{owner}/{repo}", github_token)
    if not isinstance(meta, dict):
        raise NetworkError("Unexpected API response format")

    description = meta.get("description") or ""
    default_branch = meta.get("default_branch", "main")
    primary_language = meta.get("language") or "Unknown"
    clone_url = meta.get("clone_url", f"https://github.com/{owner}/{repo}.git")
    size_kb: int = meta.get("size", 0)
    stars: int = meta.get("stargazers_count", 0)

    # For private repos with a token, embed the token in the clone URL
    if meta.get("private") and github_token:
        clone_url = f"https://{github_token}@github.com/{owner}/{repo}.git"

    # Fetch README
    readme_text = ""
    try:
        readme_data = _api_get(f"/repos/{owner}/{repo}/readme", github_token)
        if isinstance(readme_data, dict):
            readme_text = _decode_content(readme_data.get("content", ""))
    except (RepoNotFoundError, NetworkError):
        logger.debug("No README found for %s/%s", owner, repo)

    # Fetch root directory listing
    root_contents: list[dict] = []
    try:
        result = _api_get(f"/repos/{owner}/{repo}/contents/", github_token)
        if isinstance(result, list):
            root_contents = result
    except Exception:
        logger.debug("Failed to list root contents for %s/%s", owner, repo, exc_info=True)

    root_files: dict[str, str] = {}
    for item in root_contents:
        if item.get("type") == "file":
            root_files[item["name"]] = item.get("download_url", "")

    # Fetch extra documentation / config files
    install_doc: str | None = None
    extra_files: dict[str, str] = {}

    for fname in EXTRA_FILES:
        matched_name: str | None = None
        for root_name in root_files:
            if root_name.lower() == fname.lower():
                matched_name = root_name
                break

        if matched_name:
            try:
                file_data = _api_get(
                    f"/repos/{owner}/{repo}/contents/{matched_name}", github_token,
                )
                if isinstance(file_data, dict):
                    content = _decode_content(file_data.get("content", ""))
                    if matched_name.lower() in ("install.md", "install.txt"):
                        install_doc = content
                    else:
                        extra_files[matched_name] = content
            except Exception:
                logger.debug("Failed to fetch %s for %s/%s", matched_name, owner, repo, exc_info=True)

    return {
        "owner": owner,
        "repo": repo,
        "description": description,
        "default_branch": default_branch,
        "primary_language": primary_language,
        "clone_url": clone_url,
        "readme": readme_text,
        "install_doc": install_doc,
        "extra_files": extra_files,
        "size_kb": size_kb,
        "stars": stars,
    }
