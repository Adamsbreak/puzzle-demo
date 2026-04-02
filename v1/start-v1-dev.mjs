import { spawn } from "node:child_process";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const scriptDir = dirname(fileURLToPath(import.meta.url));
const root = resolve(scriptDir, "..");
const bridgeDir = resolve(root, "v1", "node-bridge");
const children = [];

function startProcess(name, command, args, cwd) {
  const child = spawn(command, args, {
    cwd,
    stdio: ["ignore", "pipe", "pipe"],
    windowsHide: false,
  });

  children.push(child);

  child.stdout.on("data", (chunk) => {
    process.stdout.write(`[${name}] ${chunk}`);
  });

  child.stderr.on("data", (chunk) => {
    process.stderr.write(`[${name}] ${chunk}`);
  });

  child.on("exit", (code, signal) => {
    const detail = signal ? `signal=${signal}` : `code=${code}`;
    process.stdout.write(`[${name}] exited (${detail})\n`);
  });

  child.on("error", (error) => {
    process.stderr.write(`[${name}] failed: ${error.message}\n`);
  });

  return child;
}

function shutdown() {
  while (children.length > 0) {
    const child = children.pop();
    if (child && !child.killed) {
      child.kill();
    }
  }
}

process.on("SIGINT", () => {
  process.stdout.write("\nShutting down Puzzle V1 services...\n");
  shutdown();
  process.exit(0);
});

process.on("SIGTERM", () => {
  shutdown();
  process.exit(0);
});

startProcess("web", process.execPath, [resolve(root, "serve-v1-local.mjs")], root);
startProcess("bridge", process.execPath, [resolve(bridgeDir, "server.mjs")], bridgeDir);

process.stdout.write("Puzzle V1 dev launcher started.\n");
process.stdout.write("Page:   http://127.0.0.1:8000/v1/index.html\n");
process.stdout.write("Bridge: http://127.0.0.1:3210/health\n");
process.stdout.write("Press Ctrl+C to stop both services.\n");
