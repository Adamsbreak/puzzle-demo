import process from "node:process";
import { inspectStaticPuzzle } from "../../v1/node-bridge/lib/static-solver.mjs";

function readStdin() {
  return new Promise((resolve, reject) => {
    const chunks = [];
    process.stdin.on("data", (chunk) => chunks.push(chunk));
    process.stdin.on("end", () => resolve(Buffer.concat(chunks).toString("utf8")));
    process.stdin.on("error", reject);
  });
}

async function main() {
  const raw = await readStdin();
  const payload = raw ? JSON.parse(raw) : {};
  const level = payload.level;
  const rulePack = payload.rulePack;
  if (!level || !rulePack) {
    throw new Error("Both level and rulePack are required.");
  }
  const result = inspectStaticPuzzle(level, rulePack, { maxSolutions: 2 });
  process.stdout.write(JSON.stringify(result));
}

main().catch((error) => {
  process.stderr.write(String(error && error.message ? error.message : error));
  process.exit(1);
});
