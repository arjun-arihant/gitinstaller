import { existsSync, mkdirSync } from "fs";
import { join } from "path";
import { log } from "./logger.js";
import chalk from "chalk";

const PYTHON_VERSION = "3.12";
const MINIFORGE_VERSION = "24.11.3-0";

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

  const { writeFileSync, unlinkSync } = await import("fs");
  writeFileSync(tarPath, buffer);

  // Extract using pure Node.js (zlib decompression + tar header parsing).
  // This works on every platform without relying on a system tar binary.
  log(chalk.gray("  Extracting Python..."));
  await extractTarGz(tarPath, pythonDir);

  // Clean up the archive
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

// --- Conda (Miniforge) support ---

function getMiniforgeAssetName() {
  const platform = process.platform;
  const arch = process.arch;

  if (platform === "win32" && arch === "x64") return "Miniforge3-Windows-x86_64.exe";
  if (platform === "linux" && arch === "x64") return "Miniforge3-Linux-x86_64.sh";
  if (platform === "linux" && arch === "arm64") return "Miniforge3-Linux-aarch64.sh";
  if (platform === "darwin" && arch === "arm64") return "Miniforge3-MacOSX-arm64.sh";
  if (platform === "darwin" && arch === "x64") return "Miniforge3-MacOSX-x86_64.sh";

  throw new Error(`Unsupported platform for Miniforge: ${platform}-${arch}`);
}

function getCondaBinPath(condaDir) {
  if (process.platform === "win32") {
    return join(condaDir, "condabin", "conda.bat");
  }
  return join(condaDir, "condabin", "conda");
}

export function getCondaActivatePath(condaDir) {
  if (process.platform === "win32") {
    return join(condaDir, "Scripts", "activate.bat");
  }
  return join(condaDir, "etc", "profile.d", "conda.sh");
}

export async function ensureConda(baseDir) {
  const condaDir = join(baseDir, ".gitinstaller", "conda");
  const condaBin = getCondaBinPath(condaDir);

  if (existsSync(condaBin)) {
    return condaBin;
  }

  log(chalk.yellow("Downloading Miniforge (conda)..."));
  mkdirSync(condaDir, { recursive: true });

  const assetName = getMiniforgeAssetName();
  const downloadUrl = `https://github.com/conda-forge/miniforge/releases/download/${MINIFORGE_VERSION}/${assetName}`;

  log(chalk.gray(`  Downloading ${assetName}...`));

  const dlResp = await fetch(downloadUrl);
  if (!dlResp.ok) {
    throw new Error(`Failed to download Miniforge: HTTP ${dlResp.status}`);
  }

  const buffer = Buffer.from(await dlResp.arrayBuffer());
  const { writeFileSync } = await import("fs");
  const installerPath = join(condaDir, assetName);
  writeFileSync(installerPath, buffer);

  log(chalk.gray("  Installing Miniforge..."));

  const { spawn } = await import("child_process");

  if (process.platform === "win32") {
    // Silent install on Windows using the .exe installer
    await runInstallerProcess(spawn, installerPath, [
      "/InstallationType=JustMe",
      "/AddToPath=0",
      "/RegisterPython=0",
      "/NoRegistry=1",
      "/NoScripts=1",
      "/S",
      `/D=${condaDir}`,
    ]);
  } else {
    // Silent install on Linux/macOS using the .sh installer
    const { chmodSync } = await import("fs");
    chmodSync(installerPath, 0o755);
    await runInstallerProcess(spawn, "/bin/bash", [
      installerPath,
      "-b",     // batch mode (no prompts)
      "-u",     // update existing install if present
      "-p", condaDir,
    ]);
  }

  // Clean up installer
  try {
    const { unlinkSync } = await import("fs");
    unlinkSync(installerPath);
  } catch {
    // ignore cleanup failure
  }

  if (!existsSync(condaBin)) {
    throw new Error(
      `Miniforge installation succeeded but conda binary not found at ${condaBin}`
    );
  }

  log(chalk.green("  Miniforge (conda) downloaded and ready."));
  return condaBin;
}

function runInstallerProcess(spawn, command, args) {
  return new Promise((resolve, reject) => {
    const proc = spawn(command, args, {
      stdio: ["ignore", "pipe", "pipe"],
      shell: false,
    });

    let stderr = "";
    proc.stderr.on("data", (data) => { stderr += data.toString(); });
    proc.on("error", reject);
    proc.on("close", (code) => {
      if (code !== 0) {
        reject(new Error(`Miniforge installer exited with code ${code}: ${stderr}`));
      } else {
        resolve();
      }
    });
  });
}

/**
 * Pure-JS .tar.gz extractor using Node.js built-in zlib.
 * Handles regular files, directories, and symlinks.
 * No system tar binary required.
 */
async function extractTarGz(tarGzPath, destDir) {
  const { createGunzip } = await import("zlib");
  const { createReadStream, createWriteStream, chmodSync } = await import("fs");
  const { mkdir, symlink } = await import("fs/promises");
  const { join, dirname } = await import("path");

  const BLOCK = 512;

  return new Promise((resolve, reject) => {
    const gunzip = createGunzip();
    const src = createReadStream(tarGzPath);
    src.pipe(gunzip);

    const chunks = [];
    gunzip.on("data", (chunk) => chunks.push(chunk));
    gunzip.on("error", reject);
    gunzip.on("end", async () => {
      try {
        const buf = Buffer.concat(chunks);
        let offset = 0;

        while (offset + BLOCK <= buf.length) {
          // Check for end-of-archive (two zero blocks)
          let allZero = true;
          for (let i = 0; i < BLOCK; i++) {
            if (buf[offset + i] !== 0) { allZero = false; break; }
          }
          if (allZero) break;

          // Parse POSIX / ustar header
          const name = readStr(buf, offset, 100);
          const modeOctal = readStr(buf, offset + 100, 8);
          const sizeOctal = readStr(buf, offset + 124, 12);
          const typeflag = String.fromCharCode(buf[offset + 156]);
          const linkname = readStr(buf, offset + 157, 100);

          // ustar prefix field (bytes 345-499)
          const prefix = readStr(buf, offset + 345, 155);
          const fullName = prefix ? prefix + "/" + name : name;

          const fileSize = parseInt(sizeOctal.trim(), 8) || 0;
          const mode = parseInt(modeOctal.trim(), 8) || 0o644;

          offset += BLOCK; // advance past header

          const destPath = join(destDir, fullName);

          if (typeflag === "5" || fullName.endsWith("/")) {
            // Directory
            await mkdir(destPath, { recursive: true });
          } else if (typeflag === "2") {
            // Symlink
            await mkdir(dirname(destPath), { recursive: true });
            try { await symlink(linkname, destPath); } catch { /* ignore duplicate */ }
          } else {
            // Regular file (typeflag "0", "\0", or empty)
            await mkdir(dirname(destPath), { recursive: true });
            const data = buf.slice(offset, offset + fileSize);
            await new Promise((res, rej) => {
              const ws = createWriteStream(destPath, { mode });
              ws.write(data);
              ws.end();
              ws.on("finish", res);
              ws.on("error", rej);
            });
            // Preserve executable bits
            if (mode & 0o111) {
              try { chmodSync(destPath, mode); } catch { /* ignore */ }
            }
          }

          // Advance offset by file data, rounded up to 512-byte blocks
          const dataBlocks = Math.ceil(fileSize / BLOCK);
          offset += dataBlocks * BLOCK;
        }

        resolve();
      } catch (err) {
        reject(err);
      }
    });
    src.on("error", reject);
  });
}

function readStr(buf, offset, length) {
  let end = offset;
  while (end < offset + length && buf[end] !== 0) end++;
  return buf.slice(offset, end).toString("utf8");
}
