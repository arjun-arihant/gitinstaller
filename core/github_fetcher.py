"""
core/github_fetcher.py — Fetches README and relevant files from GitHub API
Supports authenticated requests (private repos) and repo size estimation.
"""

import re
import base64
import requests


class RepoNotFoundError(Exception):
    pass


class GitHubRateLimitError(Exception):
    pass


class NetworkError(Exception):
    pass


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


def _parse_repo_url(repo_url):
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


def _build_headers(github_token=None):
    headers = {"Accept": "application/vnd.github.v3+json"}
    if github_token:
        headers["Authorization"] = f"token {github_token}"
    return headers


def _api_get(endpoint, github_token=None):
    url = f"{GITHUB_API}{endpoint}"
    headers = _build_headers(github_token)
    try:
        resp = requests.get(url, headers=headers, timeout=30)
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
            raise GitHubRateLimitError("GitHub rate limit hit. Please wait a few minutes.")
        raise NetworkError(f"GitHub API returned 403: {resp.text[:200]}")
    if resp.status_code == 401:
        raise NetworkError("GitHub authentication failed. Check your token in Settings.")
    if resp.status_code != 200:
        raise NetworkError(f"GitHub API returned {resp.status_code}: {resp.text[:200]}")

    return resp.json()


def _decode_content(content_b64):
    try:
        return base64.b64decode(content_b64).decode("utf-8", errors="replace")
    except Exception:
        return ""


def fetch_repo_size(repo_url, github_token=None):
    """Fetch the repository size in KB from GitHub API. Returns size in MB as float."""
    try:
        owner, repo = _parse_repo_url(repo_url)
        meta = _api_get(f"/repos/{owner}/{repo}", github_token)
        size_kb = meta.get("size", 0)
        return round(size_kb / 1024, 1)
    except Exception:
        return None


def fetch_repo_data(repo_url, github_token=None):
    """
    Given a GitHub repo URL, fetch all documentation files needed to
    understand the setup process.
    """
    owner, repo = _parse_repo_url(repo_url)

    meta = _api_get(f"/repos/{owner}/{repo}", github_token)
    description = meta.get("description") or ""
    default_branch = meta.get("default_branch", "main")
    primary_language = meta.get("language") or "Unknown"
    clone_url = meta.get("clone_url", f"https://github.com/{owner}/{repo}.git")
    size_kb = meta.get("size", 0)
    stars = meta.get("stargazers_count", 0)

    # If private and token available, use token-embedded clone URL
    if meta.get("private") and github_token:
        clone_url = f"https://{github_token}@github.com/{owner}/{repo}.git"

    readme_text = ""
    try:
        readme_data = _api_get(f"/repos/{owner}/{repo}/readme", github_token)
        readme_text = _decode_content(readme_data.get("content", ""))
    except (RepoNotFoundError, NetworkError):
        pass

    root_contents = []
    try:
        root_contents = _api_get(f"/repos/{owner}/{repo}/contents/", github_token)
    except Exception:
        pass

    root_files = {}
    for item in root_contents:
        if item.get("type") == "file":
            root_files[item["name"]] = item.get("download_url", "")

    install_doc = None
    extra_files = {}

    for fname in EXTRA_FILES:
        matched_name = None
        for root_name in root_files:
            if root_name.lower() == fname.lower():
                matched_name = root_name
                break

        if matched_name:
            try:
                file_data = _api_get(
                    f"/repos/{owner}/{repo}/contents/{matched_name}", github_token
                )
                content = _decode_content(file_data.get("content", ""))
                if matched_name.lower() in ("install.md", "install.txt"):
                    install_doc = content
                else:
                    extra_files[matched_name] = content
            except Exception:
                pass

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
