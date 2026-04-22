# Solver Architecture

## Current Topology

```mermaid
flowchart LR
  A["Main editor<br/>puzzle_grid_editor.html"] --> B["dist/editor/app.js"]
  B --> C["TS solver<br/>src/core/solver.ts"]

  D["Backend API<br/>Python"] --> E["backend/services/solver_service.py"]
  E --> F["backend/node_tools/puzzle_bridge.mjs"]
  F --> G["Node/JS static solver<br/>v1/node-bridge/lib/static-solver.mjs"]

  H["v1 frontend<br/>v1/index.html"] --> I["node-bridge-adapter.js"]
  I --> J["Node bridge HTTP server<br/>v1/node-bridge/server.mjs"]
  J --> K["Java solver<br/>v1/java-solver/StaticSolver.java"]
  J -. fallback .-> G
```

## What This Means

- The main editor currently solves locally in the browser with the TypeScript BFS solver.
- The backend service is written in Python, but it does not solve in Python.
- The backend service shells out to Node, and Node currently calls the JS static solver.
- The `v1` frontend already has a bridge adapter that can call the Node bridge server.
- The Node bridge server prefers Java and falls back to JS if Java fails.

## Runtime Paths

### 1. Main editor today

```text
Browser
  -> dist/editor/app.js
  -> src/dist core solver logic
  -> local TypeScript BFS result
```

### 2. Backend inspection path today

```text
Python service
  -> Node bridge script
  -> JS static solver
  -> JSON result back to Python
```

### 3. v1 bridge path

```text
Browser
  -> fetch http://127.0.0.1:3210/solve
  -> Node bridge server
  -> Java solver
  -> fallback to JS solver if Java fails
```

## Compatibility Notes

- The main editor supports wind and settle-mode environment logic.
- The Java `v1` solver is a static solver and does not support wind settling.
- The main editor uses `target-zone` as a tag name.
- The `v1` Java/JS static solver expects `target-lane` and `block-lane`.
- Because of that, calling Java from the main editor needs a translation layer plus a static-only guard.

## After The Bridge Hookup

```mermaid
flowchart LR
  A["Main editor solve button"] --> B{"Solver mode"}
  B -->|"TypeScript local"| C["src/core/solver.ts"]
  B -->|"Java bridge"| D["fetch Node bridge server"]
  D --> E["v1/node-bridge/server.mjs"]
  E --> F["Java solver"]
  E -. fallback .-> G["JS static solver"]
```
