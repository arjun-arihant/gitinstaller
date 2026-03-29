#!/usr/bin/env node

import { readFileSync, mkdirSync, existsSync } from "fs";
import { resolve, dirname, join } from "path";
import { fileURLToPath } from "url";
import chalk from "chalk";
import ora from "ora";
import { downloadRepo } from "./src/github.js";
import { ensurePython, getVenvPython, ensureConda } from "./src/python.js";
import { runAgent } from "./src/agent.js";
import { setSpinner, log } from "./src/logger.js";

const __dirname = dirname(fileURLToPath(import.meta.url));

// If a portable Node.js exists in .gitinstaller/node/, prepend it to PATH so
// that all child processes (npm, npx, node) spawned by the LLM agent find it.
function setupPortableNodePath() {
  const nodeDir = join(__dirname, ".gitinstaller", "node");
  if (!existsSync(nodeDir)) return;
  const binDir =
    process.platform === "win32" ? nodeDir : join(nodeDir, "bin");
  const sep = process.platform === "win32" ? ";" : ":";
  if (!process.env.PATH.includes(binDir)) {
    process.env.PATH = binDir + sep + process.env.PATH;
  }
}

// Load .env manually (no dotenv dependency)
function loadEnv() {
  const envPath = resolve(__dirname, ".env");
  if (!existsSync(envPath)) return;
  const content = readFileSync(envPath, "utf-8");
  for (const line of content.split("\n")) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) continue;
    const eqIdx = trimmed.indexOf("=");
    if (eqIdx === -1) continue;
    const key = trimmed.slice(0, eqIdx).trim();
    const value = trimmed.slice(eqIdx + 1).trim();
    if (!process.env[key]) {
      process.env[key] = value;
    }
  }
}

function parseGitHubUrl(url) {
  const match = url.match(
    /^https?:\/\/github\.com\/([a-zA-Z0-9._-]+)\/([a-zA-Z0-9._-]+)\/?$/
  );
  if (!match) return null;
  return { owner: match[1], repo: match[2].replace(/\.git$/, "") };
}

// Scan README / installation docs for conda install commands.
// Returns true if the project REQUIRES conda (not just suggests it for env creation).
// We look for "conda install" or "mamba install" which indicate conda-only packages.
// We ignore "conda create" / "conda activate" since those are just env management
// and can be replaced with venv + pip.
function detectCondaNeeds(projectDir) {
  const readmeNames = [
    "README.md", "README.rst", "README.txt", "README",
    "INSTALL.md", "INSTALL.rst", "INSTALLATION.md",
  ];

  for (const name of readmeNames) {
    const path = join(projectDir, name);
    if (!existsSync(path)) continue;

    try {
      const content = readFileSync(path, "utf-8").toLowerCase();

      // Look for conda/mamba install in command lines
      const lines = content.split("\n");
      for (const line of lines) {
        const trimmed = line.trim();
        // Match lines that start with (possibly after $) conda install or mamba install
        if (/^(?:\$\s*)?conda\s+install\b/.test(trimmed)) return true;
        if (/^(?:\$\s*)?mamba\s+install\b/.test(trimmed)) return true;
      }
    } catch {
      // unreadable file, skip
    }
  }

  return false;
}

async function main() {
  setupPortableNodePath();
  loadEnv();

  const args = process.argv.slice(2);
  const command = args[0];
  const url = args[1];

  if (command !== "install" || !url) {
    console.log(chalk.yellow("Usage: node index.js install <github-repo-url>"));
    console.log(
      chalk.gray("  Example: node index.js install https://github.com/user/repo")
    );
    process.exit(1);
  }

  if (!process.env.OPENROUTER_API_KEY) {
    console.log(
      chalk.red("Error: OPENROUTER_API_KEY not set. Create a .env file (see .env.example).")
    );
    process.exit(1);
  }

  const parsed = parseGitHubUrl(url);
  if (!parsed) {
    console.log(chalk.red("Error: Invalid GitHub URL. Expected https://github.com/owner/repo"));
    process.exit(1);
  }

  const installDir = resolve(__dirname, "installations", parsed.repo);
  mkdirSync(installDir, { recursive: true });

  const spinner = ora({ text: "Starting installation...", color: "cyan" }).start();
  setSpinner(spinner);

  try {
    // Step 1: Download repo
    spinner.text = "Downloading repository...";
    const repoMeta = await downloadRepo(url, installDir);
    log(chalk.green(`\u2713 Downloaded ${repoMeta.owner}/${repoMeta.repo} (${repoMeta.branch})`));

    // Step 2: Ensure Python is available
    spinner.text = "Setting up Python...";
    const pythonBin = await ensurePython(__dirname);
    const venvPython = getVenvPython(installDir);
    log(chalk.green("\u2713 Python ready"));

    // Step 2b: Detect conda needs via environment.yml or README scan
    const hasCondaEnvFile =
      existsSync(join(installDir, "environment.yml")) ||
      existsSync(join(installDir, "environment.yaml"));
    const needsConda = hasCondaEnvFile || detectCondaNeeds(installDir);
    let condaBin = null;
    if (needsConda) {
      spinner.text = hasCondaEnvFile
        ? "Conda environment file detected, setting up Miniforge..."
        : "Conda installation detected in README, setting up Miniforge...";
      condaBin = await ensureConda(__dirname);
      log(chalk.green("\u2713 Conda ready"));
    }

    // Step 3: Run the agentic installer
    spinner.text = "LLM agent is analyzing the project...";
    const result = await runAgent(installDir, url, repoMeta, {
      pythonBin,
      venvPython,
      condaBin,
      hasCondaEnv: needsConda,
    });

    spinner.stop();

    if (result.success) {
      console.log(chalk.green.bold("\n\u2713 Installation complete!"));
      console.log(chalk.white(result.summary));
      process.exit(0);
    } else {
      console.log(chalk.red.bold("\n\u2717 Installation failed"));
      console.log(chalk.white(result.summary));
      process.exit(1);
    }
  } catch (err) {
    spinner.stop();
    console.log(chalk.red.bold("\n\u2717 Fatal error:"), err.message);
    process.exit(1);
  }
}

main();
