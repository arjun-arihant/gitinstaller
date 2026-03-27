import { readdir, readFile, writeFile, mkdir, stat } from "fs/promises";
import { spawn } from "child_process";
import { join, dirname } from "path";
import { validatePath, validateCommand } from "./security.js";
import { log, getSpinner } from "./logger.js";
import chalk from "chalk";

const MAX_OUTPUT_LENGTH = 10000;
const COMMAND_TIMEOUT = 5 * 60 * 1000; // 5 minutes

export const TOOL_DEFINITIONS = [
  {
    type: "function",
    function: {
      name: "list_directory",
      description:
        "List the contents of a directory. Returns entries formatted as [DIR] or [FILE] with file sizes.",
      parameters: {
        type: "object",
        properties: {
          path: {
            type: "string",
            description:
              'Directory path relative to the project root. Use "." for project root.',
          },
        },
        required: ["path"],
      },
    },
  },
  {
    type: "function",
    function: {
      name: "read_file",
      description:
        "Read the contents of a file. Returns the file content as text, capped at max_lines.",
      parameters: {
        type: "object",
        properties: {
          path: {
            type: "string",
            description: "File path relative to the project root.",
          },
          max_lines: {
            type: "number",
            description: "Maximum number of lines to read (default: 200).",
          },
        },
        required: ["path"],
      },
    },
  },
  {
    type: "function",
    function: {
      name: "run_command",
      description:
        "Execute a command with arguments. Returns stdout, stderr, and exit code. Non-zero exit codes are informational, not errors — read the output and adapt.",
      parameters: {
        type: "object",
        properties: {
          command: {
            type: "string",
            description:
              "The executable to run (e.g. 'npm', 'pip', 'python', 'node').",
          },
          args: {
            type: "array",
            items: { type: "string" },
            description: "Arguments array passed to the command.",
          },
        },
        required: ["command", "args"],
      },
    },
  },
  {
    type: "function",
    function: {
      name: "write_file",
      description:
        "Write content to a file. Creates parent directories if needed.",
      parameters: {
        type: "object",
        properties: {
          path: {
            type: "string",
            description: "File path relative to the project root.",
          },
          content: {
            type: "string",
            description: "The content to write to the file.",
          },
        },
        required: ["path", "content"],
      },
    },
  },
  {
    type: "function",
    function: {
      name: "report_progress",
      description:
        "Report progress to the user. Use this to keep the user informed about what you're doing.",
      parameters: {
        type: "object",
        properties: {
          phase: {
            type: "string",
            description:
              "Current phase (e.g. 'analyzing', 'installing', 'configuring').",
          },
          message: {
            type: "string",
            description: "A brief description of what's happening.",
          },
        },
        required: ["phase", "message"],
      },
    },
  },
  {
    type: "function",
    function: {
      name: "finish",
      description:
        "Signal that installation is complete. Call this when you're done.",
      parameters: {
        type: "object",
        properties: {
          summary: {
            type: "string",
            description:
              "A summary of what was done and how to run the project.",
          },
          success: {
            type: "boolean",
            description: "Whether the installation was successful.",
          },
        },
        required: ["summary", "success"],
      },
    },
  },
];

// Tool implementations

async function listDirectory(args, projectDir) {
  const dirPath = validatePath(args.path || ".", projectDir);
  const entries = await readdir(dirPath, { withFileTypes: true });
  const lines = [];

  for (const entry of entries) {
    if (entry.isDirectory()) {
      lines.push(`[DIR]  ${entry.name}`);
    } else {
      try {
        const fileStat = await stat(join(dirPath, entry.name));
        const sizeKb = (fileStat.size / 1024).toFixed(1);
        lines.push(`[FILE] ${entry.name} (${sizeKb} KB)`);
      } catch {
        lines.push(`[FILE] ${entry.name}`);
      }
    }
  }

  return lines.length > 0 ? lines.join("\n") : "(empty directory)";
}

async function readFileContent(args, projectDir) {
  const filePath = validatePath(args.path, projectDir);
  const content = await readFile(filePath, "utf-8");
  const maxLines = args.max_lines || 200;
  const lines = content.split("\n");

  if (lines.length > maxLines) {
    return (
      lines.slice(0, maxLines).join("\n") +
      `\n\n... (truncated, showing ${maxLines} of ${lines.length} lines)`
    );
  }
  return content;
}

function runCommandTool(args, projectDir) {
  return new Promise((resolve) => {
    try {
      validateCommand(args.command, args.args || []);
    } catch (err) {
      resolve(`Error: ${err.message}`);
      return;
    }

    const ac = new AbortController();
    const timeout = setTimeout(() => ac.abort(), COMMAND_TIMEOUT);

    let stdout = "";
    let stderr = "";

    // On Windows, npm/npx/yarn are .cmd batch scripts and require a shell to
    // execute. We use shell:true on Windows only. validateCommand() already
    // blocks dangerous commands (cmd, powershell, bash, etc.) and injection
    // patterns (&&, ||, ;, backticks, $(...)), so this is safe.
    const useShell = process.platform === "win32";

    const proc = spawn(args.command, args.args || [], {
      cwd: projectDir,
      shell: useShell,
      signal: ac.signal,
      env: { ...process.env, PATH: process.env.PATH },
    });

    proc.stdout.on("data", (data) => {
      stdout += data.toString();
      if (stdout.length > MAX_OUTPUT_LENGTH) {
        stdout = stdout.slice(0, MAX_OUTPUT_LENGTH);
      }
    });

    proc.stderr.on("data", (data) => {
      stderr += data.toString();
      if (stderr.length > MAX_OUTPUT_LENGTH) {
        stderr = stderr.slice(0, MAX_OUTPUT_LENGTH);
      }
    });

    proc.on("close", (code) => {
      clearTimeout(timeout);
      let result = `EXIT CODE: ${code}`;
      if (stdout.trim()) result += `\nSTDOUT:\n${stdout.trim()}`;
      if (stderr.trim()) result += `\nSTDERR:\n${stderr.trim()}`;
      resolve(result);
    });

    proc.on("error", (err) => {
      clearTimeout(timeout);
      if (err.name === "AbortError") {
        resolve(`Error: Command timed out after 5 minutes`);
      } else {
        resolve(`Error: Failed to run command: ${err.message}`);
      }
    });
  });
}

async function writeFileContent(args, projectDir) {
  const filePath = validatePath(args.path, projectDir);
  await mkdir(dirname(filePath), { recursive: true });
  await writeFile(filePath, args.content, "utf-8");
  const bytes = Buffer.byteLength(args.content, "utf-8");
  return `File written: ${args.path} (${bytes} bytes)`;
}

function reportProgress(args) {
  const spinner = getSpinner();
  const msg = `[${args.phase}] ${args.message}`;
  if (spinner && spinner.isSpinning) {
    spinner.text = msg;
  }
  log(chalk.cyan(`  ${msg}`));
  return "Progress reported.";
}

function finishTool(args) {
  return JSON.stringify({
    __finish: true,
    summary: args.summary || "Installation finished.",
    success: args.success !== false,
  });
}

// Dispatcher

export async function executeTool(toolCall, projectDir) {
  const name = toolCall.function.name;
  let args;
  try {
    args = JSON.parse(toolCall.function.arguments);
  } catch (e) {
    return `Error: Invalid JSON in tool arguments: ${e.message}`;
  }

  try {
    switch (name) {
      case "list_directory":
        return await listDirectory(args, projectDir);
      case "read_file":
        return await readFileContent(args, projectDir);
      case "run_command":
        return await runCommandTool(args, projectDir);
      case "write_file":
        return await writeFileContent(args, projectDir);
      case "report_progress":
        return reportProgress(args);
      case "finish":
        return finishTool(args);
      default:
        return `Error: Unknown tool "${name}"`;
    }
  } catch (err) {
    return `Error: ${err.message}`;
  }
}
