# GitInstaller

A CLI tool that takes a GitHub repo URL and installs it autonomously. An LLM agent analyzes the project, figures out what kind of repo it is, and installs all dependencies — no input required.

```
node index.js install https://github.com/user/repo
```

## How It Works

1. Downloads the repo as a ZIP (no git required)
2. Downloads a bundled Python if the project needs it (no system Python required)
3. An LLM agent reads the project files, determines the project type, and runs the appropriate install commands
4. Reports progress and finishes with a summary of how to run the project

The LLM decides what to do. The tool just executes. It handles Python projects (requirements.txt, pyproject.toml, setup.py), Node.js projects (package.json), and more.

## Setup

```bash
npm install
cp .env.example .env
```

Edit `.env` and set your OpenRouter API key:

```
OPENROUTER_API_KEY=your-key-here
```

Get a key at [openrouter.ai](https://openrouter.ai).

## Usage

```bash
node index.js install https://github.com/owner/repo
```

Installed projects land in `./installations/{repo-name}/`.

## Requirements

- Node.js 18+
- No Python, git, or other tools required — they are handled automatically

## Constraints

- Max 20 LLM tool calls per install (prevents runaway loops)
- 5-minute timeout per command
- All operations stay inside the project directory — no writes outside it
- Blocked commands: `rm`, `sudo`, `curl | bash`, and other destructive patterns
