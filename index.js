#!/usr/bin/env node

import { readFileSync, mkdirSync, existsSync } from "fs";
import { resolve, dirname } from "path";
import { fileURLToPath } from "url";
import chalk from "chalk";
import ora from "ora";
import { downloadRepo } from "./src/github.js";
import { ensurePython, getVenvPython } from "./src/python.js";
import { runAgent } from "./src/agent.js";
import { setSpinner, log } from "./src/logger.js";

const __dirname = dirname(fileURLToPath(import.meta.url));

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

async function main() {
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

    // Step 3: Run the agentic installer
    spinner.text = "LLM agent is analyzing the project...";
    const result = await runAgent(installDir, url, repoMeta, {
      pythonBin,
      venvPython,
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
