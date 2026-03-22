"""
core/github_fetcher.py — Fetches README and relevant files from GitHub API
"""

import re
import base64
import requests


class RepoNotFoundError(Exception):
    """Raised when the GitHub repository is not found (404)."""
    pass


class GitHubRateLimitError(Exception):
    """Raised when the GitHub API rate limit is hit."""
    pass


class NetworkError(Exception):
    """Raised on network/connection errors."""
    pass


GITHUB_API = "https://api.github.com"

# Files to look for in the repo root
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


def _parse_repo_url(repo_url: str) -> tuple:
    """
    Parse a GitHub URL and extract owner and repo name.
    Supports formats like:
      - https://github.com/owner/repo
      - https://github.com/owner/repo.git
      - https://github.com/owner/repo/tree/main
      - github.com/owner/repo
    """
    repo_url = repo_url.strip().rstrip("/")

    patterns = [
        r"(?:https?://)?github\.com/([^/]+)/([^/.]+?)(?:\.git)?(?:/.*)?$",
    ]

    for pattern in patterns:
        match = re.match(pattern, repo_url)
        if match:
            return match.group(1), match.group(2)

    raise ValueError(f"Could not parse GitHub URL: {repo_url}")


def _api_get(endpoint: str) -> dict:
    """Make a GET request to the GitHub API with error handling."""
    url = f"{GITHUB_API}{endpoint}"
    try:
        resp = requests.get(url, timeout=30)
    except requests.ConnectionError:
        raise NetworkError("Network error. Check your internet connection.")
    except requests.Timeout:
        raise NetworkError("Request timed out. Check your internet connection.")
    except requests.RequestException as e:
        raise NetworkError(f"Network error: {e}")

    if resp.status_code == 404:
        raise RepoNotFoundError("Repository not found. Check the URL and try again.")
    if resp.status_code == 403:
        remaining = resp.headers.get("X-RateLimit-Remaining", "0")
        if remaining == "0":
            raise GitHubRateLimitError(
                "GitHub rate limit hit. Please wait a few minutes."
            )
        raise NetworkError(f"GitHub API returned 403: {resp.text[:200]}")
    if resp.status_code != 200:
        raise NetworkError(f"GitHub API returned {resp.status_code}: {resp.text[:200]}")

    return resp.json()


def _decode_content(content_b64: str) -> str:
    """Decode base64-encoded file content from the GitHub API."""
    try:
        return base64.b64decode(content_b64).decode("utf-8", errors="replace")
    except Exception:
        return ""


def fetch_repo_data(repo_url: str) -> dict:
    """
    Given a GitHub repo URL, fetch all documentation files needed to
    understand the setup process.

    Returns a dict with repo metadata, README, and any extra doc files found.
    """
    owner, repo = _parse_repo_url(repo_url)

    # 1. Get repo metadata
    meta = _api_get(f"/repos/{owner}/{repo}")
    description = meta.get("description") or ""
    default_branch = meta.get("default_branch", "main")
    primary_language = meta.get("language") or "Unknown"
    clone_url = meta.get("clone_url", f"https://github.com/{owner}/{repo}.git")

    # 2. Get README
    readme_text = ""
    try:
        readme_data = _api_get(f"/repos/{owner}/{repo}/readme")
        readme_text = _decode_content(readme_data.get("content", ""))
    except (RepoNotFoundError, NetworkError):
        pass  # README is optional, soldier on

    # 3. Get root file tree
    root_contents = []
    try:
        root_contents = _api_get(f"/repos/{owner}/{repo}/contents/")
    except Exception:
        pass

    # Build a set of file names at the root for quick lookup
    root_files = {}
    for item in root_contents:
        if item.get("type") == "file":
            root_files[item["name"]] = item.get("download_url", "")

    # 4. Fetch extra documentation files
    install_doc = None
    extra_files = {}

    for fname in EXTRA_FILES:
        # Case-insensitive lookup
        matched_name = None
        for root_name in root_files:
            if root_name.lower() == fname.lower():
                matched_name = root_name
                break

        if matched_name:
            try:
                file_data = _api_get(
                    f"/repos/{owner}/{repo}/contents/{matched_name}"
                )
                content = _decode_content(file_data.get("content", ""))

                if matched_name.lower() in ("install.md", "install.txt"):
                    install_doc = content
                else:
                    extra_files[matched_name] = content
            except Exception:
                pass  # Skip files we can't fetch

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
    }
