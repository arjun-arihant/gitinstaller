import { existsSync, mkdirSync } from "fs";
import { join } from "path";
import { spawn } from "child_process";
import { log } from "./logger.js";
import chalk from "chalk";

const PYTHON_VERSION = "3.12";

// Platform triples for python-build-standalone
function getPlatformTriple() {
  const platform = process.platform;
  const arch = process.arch;

  if (platform === "win32" && arch === "x64") return "x86_64-pc-windows-msvc";
  if (platform === "linux" && arch === "x64") return "x86_64-unknown-linux-gnu";
  if (platform === "darwin" && arch === "arm64") return "aarch64-apple-darwin";
  if (platform === "darwin" && arch === "x64") return "x86_64-apple-darwin";

  throw new Error(`Unsupported platform: ${platform}-${arch}`);
}

function getPythonBinPath(pythonDir) {
  if (process.platform === "win32") {
    return join(pythonDir, "python", "python.exe");
  }
  return join(pythonDir, "python", "bin", "python3");
}

export async function ensurePython(baseDir) {
  const pythonDir = join(baseDir, ".gitinstaller", "python");
  const binPath = getPythonBinPath(pythonDir);

  if (existsSync(binPath)) {
    return binPath;
  }

  log(chalk.yellow("Downloading Python (python-build-standalone)..."));
  mkdirSync(pythonDir, { recursive: true });

  // Find the latest release with a matching asset
  const triple = getPlatformTriple();
  const releaseUrl =
    "https://api.github.com/repos/astral-sh/python-build-standalone/releases/latest";
  const releaseResp = await fetch(releaseUrl, {
    headers: { Accept: "application/vnd.github.v3+json" },
  });

  if (!releaseResp.ok) {
    throw new Error(
      `Failed to fetch python-build-standalone releases: HTTP ${releaseResp.status}`
    );
  }

  const release = await releaseResp.json();

  // Find asset matching: cpython-3.12.x+date-{triple}-install_only_stripped.tar.gz
  const asset = release.assets.find(
    (a) =>
      a.name.includes(triple) &&
      a.name.startsWith(`cpython-${PYTHON_VERSION}.`) &&
      a.name.includes("install_only_stripped") &&
      a.name.endsWith(".tar.gz")
  );

  if (!asset) {
    throw new Error(
      `No python-build-standalone asset found for ${triple} with Python ${PYTHON_VERSION}`
    );
  }

  log(chalk.gray(`  Downloading ${asset.name}...`));

  // Download the tar.gz
  const dlResp = await fetch(asset.browser_download_url);
  if (!dlResp.ok) {
    throw new Error(`Failed to download Python: HTTP ${dlResp.status}`);
  }

  const buffer = Buffer.from(await dlResp.arrayBuffer());
  const tarPath = join(pythonDir, "python.tar.gz");

  const { writeFileSync } = await import("fs");
  writeFileSync(tarPath, buffer);

  // Extract with tar (available on Win10+, Linux, macOS)
  log(chalk.gray("  Extracting Python..."));
  // On Windows, use forward slashes and --force-local to prevent
  // GNU tar from interpreting drive letters (D:) as remote hosts
  const tarFile = tarPath.replace(/\\/g, "/");
  const outDir = pythonDir.replace(/\\/g, "/");
  const tarArgs = ["xzf", tarFile, "-C", outDir];
  if (process.platform === "win32") tarArgs.push("--force-local");
  await runSpawn("tar", tarArgs);

  // Clean up the archive
  const { unlinkSync } = await import("fs");
  try {
    unlinkSync(tarPath);
  } catch {
    // ignore cleanup failure
  }

  if (!existsSync(binPath)) {
    throw new Error(
      `Python extraction succeeded but binary not found at ${binPath}`
    );
  }

  log(chalk.green("  Python downloaded and ready."));
  return binPath;
}

export function getVenvPython(projectDir) {
  if (process.platform === "win32") {
    return join(projectDir, "venv", "Scripts", "python.exe");
  }
  return join(projectDir, "venv", "bin", "python3");
}

export function getVenvPip(projectDir) {
  if (process.platform === "win32") {
    return join(projectDir, "venv", "Scripts", "pip.exe");
  }
  return join(projectDir, "venv", "bin", "pip3");
}

function runSpawn(cmd, args, cwd) {
  return new Promise((resolve, reject) => {
    const proc = spawn(cmd, args, { cwd, shell: false });
    let stderr = "";
    proc.stderr.on("data", (d) => (stderr += d.toString()));
    proc.on("close", (code) => {
      if (code !== 0) reject(new Error(`${cmd} exited with code ${code}: ${stderr}`));
      else resolve();
    });
    proc.on("error", reject);
  });
}
