import { resolve } from "path";

const BLOCKED_COMMANDS = new Set([
  "rm",
  "rmdir",
  "del",
  "rd",
  "sudo",
  "su",
  "chmod",
  "chown",
  "mkfs",
  "dd",
  "format",
  "shutdown",
  "reboot",
  "powershell",
  "cmd",
  "bash",
  "sh",
  "zsh",
]);

const BLOCKED_ARG_PATTERNS = [
  /\|/,               // pipe — covers all | variants; interpreted by shell on Windows
  />\s*\/dev\//,      // /dev/ redirection
  />\s*[A-Za-z]:\\/,  // Windows drive redirection (e.g. > C:\file)
  /&&/,
  /;/,
  /`/,
  /\$\(/,
  /--no-preserve-root/,
];

export function validatePath(requestedPath, projectDir) {
  const resolved = resolve(projectDir, requestedPath);
  const normalizedProject = resolve(projectDir);
  if (!resolved.startsWith(normalizedProject)) {
    throw new Error(
      `Path traversal blocked: "${requestedPath}" resolves outside project directory`
    );
  }
  return resolved;
}

export function validateCommand(command, args) {
  // Block dangerous commands
  const cmdName = command.toLowerCase().replace(/\.exe$/, "");
  if (BLOCKED_COMMANDS.has(cmdName)) {
    throw new Error(`Blocked command: "${command}"`);
  }

  // Reject commands with path separators (prevents running arbitrary binaries)
  if (command.includes("/") || command.includes("\\")) {
    // Allow venv python paths (e.g., venv/Scripts/python.exe)
    if (!command.includes("venv")) {
      throw new Error(
        `Command must not contain path separators: "${command}"`
      );
    }
  }

  // Check args for shell injection patterns
  const argsStr = args.join(" ");
  for (const pattern of BLOCKED_ARG_PATTERNS) {
    if (pattern.test(argsStr)) {
      throw new Error(
        `Blocked argument pattern detected in: "${argsStr}"`
      );
    }
  }

  return { command, args };
}
