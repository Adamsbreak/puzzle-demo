import { createServer } from "node:http";
import { spawn } from "node:child_process";
import { resolve } from "node:path";
import { solveStaticPuzzle, validatePuzzle } from "./lib/static-solver.mjs";

const host = process.env.PUZZLE_NODE_BRIDGE_HOST || "127.0.0.1";
const port = Number(process.env.PUZZLE_NODE_BRIDGE_PORT || 3210);
const engine = process.env.PUZZLE_SOLVER_ENGINE || "java";
const javaSolverDir = resolve(process.cwd(), "..", "java-solver");
const javaCommand = process.platform === "win32" ? "cmd.exe" : "mvn";
const javaArgs =
  process.platform === "win32"
    ? ["/d", "/s", "/c", "mvn -q exec:java"]
    : ["-q", "exec:java"];
const javaTimeoutMs = Number(process.env.PUZZLE_JAVA_TIMEOUT_MS || 30000);

function sendJson(res, statusCode, payload) {
  res.writeHead(statusCode, {
    "Content-Type": "application/json; charset=utf-8",
    "Cache-Control": "no-cache",
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
  });
  res.end(JSON.stringify(payload, null, 2));
}

function sendText(res, statusCode, text) {
  res.writeHead(statusCode, {
    "Content-Type": "text/plain; charset=utf-8",
    "Cache-Control": "no-cache",
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
  });
  res.end(text);
}

function readJsonBody(req) {
  return new Promise(function (resolveBody, reject) {
    const chunks = [];
    let total = 0;
    req.on("data", function (chunk) {
      total += chunk.length;
      if (total > 5 * 1024 * 1024) {
        reject(new Error("Request body is too large."));
        req.destroy();
        return;
      }
      chunks.push(chunk);
    });
    req.on("end", function () {
      try {
        const raw = Buffer.concat(chunks).toString("utf8");
        resolveBody(raw ? JSON.parse(raw) : {});
      } catch (error) {
        reject(error);
      }
    });
    req.on("error", reject);
  });
}

function runJavaSolver(payload) {
  return new Promise(function (resolveRun, reject) {
    const child = spawn(javaCommand, javaArgs, {
      cwd: javaSolverDir,
      stdio: ["pipe", "pipe", "pipe"],
      windowsHide: true,
    });

    const stdoutChunks = [];
    const stderrChunks = [];
    let settled = false;

    const timer = setTimeout(function () {
      if (settled) return;
      settled = true;
      child.kill();
      reject(new Error("Java solver timed out after " + javaTimeoutMs + "ms."));
    }, javaTimeoutMs);

    child.stdout.on("data", function (chunk) {
      stdoutChunks.push(chunk);
    });

    child.stderr.on("data", function (chunk) {
      stderrChunks.push(chunk);
    });

    child.on("error", function (error) {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      reject(error);
    });

    child.on("close", function (code) {
      if (settled) return;
      settled = true;
      clearTimeout(timer);

      const stdout = Buffer.concat(stdoutChunks).toString("utf8").trim();
      const stderr = Buffer.concat(stderrChunks).toString("utf8").trim();

      if (code !== 0) {
        reject(
          new Error(
              "Java solver exited with code "
              + code
              + (stderr ? ": " + stderr : stdout ? ": " + stdout : "."))
        );
        return;
      }

      try {
        resolveRun(stdout ? JSON.parse(stdout) : {});
      } catch (error) {
        reject(
          new Error(
              "Java solver returned invalid JSON."
              + (stdout ? " Output: " + stdout.slice(0, 400) : ""))
        );
      }
    });

    child.stdin.end(JSON.stringify(payload));
  });
}

function solveBuiltin(payload) {
  const result = solveStaticPuzzle(payload.puzzleSpec, payload.rulePack);
  return Object.assign({}, result, {
    engine: "builtin",
    transport: {
      kind: "node-bridge",
      host: host,
      port: port,
      solver: "builtin",
    },
  });
}

async function solveWithFallback(payload) {
  if (engine === "builtin") {
    return solveBuiltin(payload);
  }

  if (engine !== "java") {
    return {
      status: "not-implemented",
      summary: "The selected solver engine is not implemented: " + engine,
      engine: engine,
    };
  }

  try {
    const result = await runJavaSolver(payload.puzzleSpec);
    return Object.assign({}, result, {
      engine: "java",
      transport: {
        kind: "node-bridge",
        host: host,
        port: port,
        solver: "java",
      },
    });
  } catch (error) {
    const fallback = solveBuiltin(payload);
    fallback.summary =
      (fallback.summary || "Solved with builtin fallback.")
      + "\nJava solver failed, used builtin fallback.";
    fallback.transport = {
      kind: "node-bridge",
      host: host,
      port: port,
      solver: "builtin-fallback",
      preferredSolver: "java",
      reason: error instanceof Error ? error.message : String(error),
    };
    fallback.engine = "builtin";
    return fallback;
  }
}

async function solveRequest(payload) {
  const puzzleSpec = payload && payload.puzzleSpec;
  const rulePack = payload && payload.rulePack;

  if (!puzzleSpec || !rulePack) {
    return {
      status: "invalid-request",
      summary: "Both puzzleSpec and rulePack are required.",
    };
  }

  const report = validatePuzzle(puzzleSpec, rulePack);
  if (!report.valid) {
    return {
      status: "invalid-puzzle",
      summary: "The puzzle structure is invalid.",
      findings: report.findings,
      engine: engine,
    };
  }

  return solveWithFallback({
    puzzleSpec: puzzleSpec,
    rulePack: rulePack,
  });
}

const server = createServer(async function (req, res) {
  try {
    if (req.method === "OPTIONS") {
      sendText(res, 204, "");
      return;
    }

    if (req.method === "GET" && req.url === "/health") {
      sendJson(res, 200, {
        ok: true,
        service: "puzzle-v1-node-bridge",
        engine: engine,
        host: host,
        port: port,
        javaSolverDir: javaSolverDir,
      });
      return;
    }

    if (req.method === "POST" && req.url === "/solve") {
      const payload = await readJsonBody(req);
      const result = await solveRequest(payload);
      sendJson(res, 200, result);
      return;
    }

    sendJson(res, 404, {
      ok: false,
      message: "Not found.",
    });
  } catch (error) {
    sendJson(res, 500, {
      status: "bridge-error",
      summary: error instanceof Error ? error.message : String(error),
      engine: engine,
    });
  }
});

server.listen(port, host, function () {
  console.log("Puzzle V1 Node bridge running at http://" + host + ":" + port);
  console.log("Health check: http://" + host + ":" + port + "/health");
  console.log("Solver engine: " + engine);
});
