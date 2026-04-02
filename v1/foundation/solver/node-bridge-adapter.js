(function () {
  const root = window.PuzzleV1;
  const bridgeUrl = window.PuzzleV1NodeBridgeUrl || "http://127.0.0.1:3210";
  const fallbackAdapter = root.getSolverAdapter ? root.getSolverAdapter() : null;

  async function callBridge(puzzleSpec, rulePack) {
    const response = await fetch(bridgeUrl + "/solve", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        puzzleSpec: puzzleSpec,
        rulePack: rulePack,
      }),
    });

    if (!response.ok) {
      const text = await response.text();
      throw new Error("Node bridge request failed: " + response.status + " " + text);
    }

    return response.json();
  }

  root.setSolverAdapter({
    id: "node-bridge",
    kind: "bridge",
    description: "Node bridge solver adapter with builtin fallback.",
    solve: async function solve(puzzleSpec, rulePack) {
      try {
        return await callBridge(puzzleSpec, rulePack);
      } catch (error) {
        if (!fallbackAdapter || typeof fallbackAdapter.solve !== "function") {
          throw error;
        }
        const fallbackResult = await Promise.resolve(fallbackAdapter.solve(puzzleSpec, rulePack));
        fallbackResult.transport = {
          kind: "fallback-builtin",
          bridgeUrl: bridgeUrl,
          reason: error instanceof Error ? error.message : String(error),
        };
        fallbackResult.summary = (fallbackResult.summary || "Solved with builtin fallback.") + "\nNode bridge unavailable, used builtin solver fallback.";
        return fallbackResult;
      }
    },
  });
})();
