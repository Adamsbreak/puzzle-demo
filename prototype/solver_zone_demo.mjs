const directions = {
  north: { dr: -1, dc: 0 },
  south: { dr: 1, dc: 0 },
  west: { dr: 0, dc: -1 },
  east: { dr: 0, dc: 1 },
};

function cloneState(state) {
  return {
    board: {
      rows: state.board.rows,
      cols: state.board.cols,
      zones: state.board.zones.map((zone) => ({
        ...zone,
        shape: { ...zone.shape },
        targetFilter: zone.targetFilter ? { ...zone.targetFilter } : undefined,
        visual: zone.visual ? { ...zone.visual } : undefined,
      })),
      pieces: state.board.pieces.map((piece) => ({ ...piece })),
    },
    runtime: JSON.parse(JSON.stringify(state.runtime || {})),
  };
}

function matchesFilter(piece, filter = {}) {
  if (filter.pieceIds && !filter.pieceIds.includes(piece.id)) {
    return false;
  }
  if (filter.pieceKinds && !filter.pieceKinds.includes(piece.kind)) {
    return false;
  }
  if (filter.pieceRoles && !filter.pieceRoles.includes(piece.role)) {
    return false;
  }
  return true;
}

function zoneAnchorPosition(zone, board) {
  if (zone.shape.kind === "rect") {
    return { row: zone.shape.row, col: zone.shape.col };
  }

  if (zone.shape.side === "left") {
    return { row: zone.shape.index, col: 0 };
  }
  if (zone.shape.side === "right") {
    return { row: zone.shape.index, col: board.cols - 1 };
  }
  if (zone.shape.side === "top") {
    return { row: 0, col: zone.shape.index };
  }
  return { row: board.rows - 1, col: zone.shape.index };
}

function placeSpawnPieces(definition) {
  const state = cloneState({
    board: {
      rows: definition.board.rows,
      cols: definition.board.cols,
      zones: definition.board.zones,
      pieces: [],
    },
    runtime: definition.runtime || {},
  });

  definition.pieces.forEach((pieceDef) => {
    const piece = { ...pieceDef };
    if (piece.spawnZoneId) {
      const zone = state.board.zones.find((item) => item.id === piece.spawnZoneId);
      if (!zone) {
        throw new Error(`Missing spawn zone: ${piece.spawnZoneId}`);
      }
      const pos = zoneAnchorPosition(zone, state.board);
      piece.row = pos.row;
      piece.col = pos.col;
    }
    state.board.pieces.push(piece);
  });

  return state;
}

function inBounds(state, row, col) {
  return row >= 0 && col >= 0 && row < state.board.rows && col < state.board.cols;
}

function pieceAt(state, row, col, ignoreId = null) {
  return (
    state.board.pieces.find(
      (piece) => piece.id !== ignoreId && piece.row === row && piece.col === col,
    ) || null
  );
}

function canPlace(state, piece, row, col) {
  return inBounds(state, row, col) && !pieceAt(state, row, col, piece.id);
}

function overlapsRectGoal(piece, shape) {
  return piece.row === shape.row && piece.col === shape.col;
}

function matchesEdgeGoal(piece, shape, board) {
  if (shape.side === "left") {
    return piece.col === 0 && piece.row >= shape.index && piece.row < shape.index + shape.h;
  }
  if (shape.side === "right") {
    return (
      piece.col === board.cols - 1 &&
      piece.row >= shape.index &&
      piece.row < shape.index + shape.h
    );
  }
  if (shape.side === "top") {
    return piece.row === 0 && piece.col >= shape.index && piece.col < shape.index + shape.w;
  }
  return (
    piece.row === board.rows - 1 &&
    piece.col >= shape.index &&
    piece.col < shape.index + shape.w
  );
}

function isGoalSatisfied(state) {
  const goalZones = state.board.zones.filter((zone) => zone.role === "goal");
  return goalZones.every((zone) => {
    const matchingPieces = state.board.pieces.filter((piece) => matchesFilter(piece, zone.targetFilter));
    if (matchingPieces.length === 0) {
      return false;
    }
    return matchingPieces.some((piece) => {
      if (zone.shape.kind === "rect") {
        return overlapsRectGoal(piece, zone.shape);
      }
      return matchesEdgeGoal(piece, zone.shape, state.board);
    });
  });
}

function serializeState(state) {
  const piecesKey = state.board.pieces
    .map((piece) => `${piece.id}:${piece.row},${piece.col}`)
    .sort()
    .join("|");
  const runtimeKey = JSON.stringify(state.runtime || {});
  return `${piecesKey}#${runtimeKey}`;
}

function listMoveActions(state) {
  const actions = [];
  state.board.pieces.forEach((piece) => {
    if (!piece.movable) {
      return;
    }
    Object.entries(directions).forEach(([direction, delta]) => {
      const nextRow = piece.row + delta.dr;
      const nextCol = piece.col + delta.dc;
      if (canPlace(state, piece, nextRow, nextCol)) {
        actions.push({
          type: "move-piece",
          pieceId: piece.id,
          direction,
          toRow: nextRow,
          toCol: nextCol,
        });
      }
    });
  });
  return actions;
}

function applyMove(state, action) {
  const nextState = cloneState(state);
  const piece = nextState.board.pieces.find((item) => item.id === action.pieceId);
  if (!piece) {
    return nextState;
  }
  piece.row = action.toRow;
  piece.col = action.toCol;
  return nextState;
}

function stepWind(state) {
  const nextState = cloneState(state);
  const wind = nextState.runtime.wind;
  if (!wind?.active) {
    return nextState;
  }

  const delta = directions[wind.direction];
  const movableByWind = nextState.board.pieces
    .filter((piece) => piece.affectedByWind)
    .sort((a, b) => {
      if (wind.direction === "east") return b.col - a.col;
      if (wind.direction === "west") return a.col - b.col;
      if (wind.direction === "south") return b.row - a.row;
      return a.row - b.row;
    });

  movableByWind.forEach((piece) => {
    const nextRow = piece.row + delta.dr;
    const nextCol = piece.col + delta.dc;
    if (canPlace(nextState, piece, nextRow, nextCol)) {
      piece.row = nextRow;
      piece.col = nextCol;
    }
  });

  return nextState;
}

function isWindStable(state) {
  const wind = state.runtime.wind;
  if (!wind?.active) {
    return true;
  }
  const delta = directions[wind.direction];
  return state.board.pieces
    .filter((piece) => piece.affectedByWind)
    .every((piece) => !canPlace(state, piece, piece.row + delta.dr, piece.col + delta.dc));
}

function settleUntilStable(state, engine, maxSteps = 32) {
  let current = cloneState(state);
  const seen = new Set([engine.serializeState(current)]);

  for (let i = 0; i < maxSteps; i += 1) {
    if (engine.isEnvironmentStable(current)) {
      return current;
    }
    const nextState = engine.stepEnvironment(current);
    const key = engine.serializeState(nextState);
    if (seen.has(key)) {
      return nextState;
    }
    seen.add(key);
    current = nextState;
  }

  return current;
}

function solve(initialState, engine, maxNodes = 2000) {
  const queue = [{ state: cloneState(initialState), steps: [] }];
  const seen = new Set([engine.serializeState(initialState)]);
  let explored = 0;

  while (queue.length > 0) {
    const current = queue.shift();
    explored += 1;

    if (engine.isGoal(current.state)) {
      return {
        solvable: true,
        steps: current.steps,
        explored,
      };
    }

    if (explored > maxNodes) {
      return {
        solvable: false,
        steps: [],
        explored,
      };
    }

    engine.listPlayerActions(current.state).forEach((action) => {
      let nextState = engine.applyPlayerAction(current.state, action);

      if (engine.mode === "settle") {
        nextState = settleUntilStable(nextState, engine);
      } else if (engine.mode === "tick") {
        nextState = engine.stepEnvironment(nextState);
      }

      const key = engine.serializeState(nextState);
      if (seen.has(key)) {
        return;
      }
      seen.add(key);
      queue.push({
        state: nextState,
        steps: [...current.steps, action],
      });
    });
  }

  return {
    solvable: false,
    steps: [],
    explored,
  };
}

function createStaticEngine() {
  return {
    mode: "static",
    deterministic: true,
    listPlayerActions: listMoveActions,
    applyPlayerAction: applyMove,
    isGoal: isGoalSatisfied,
    serializeState,
  };
}

function createWindSettleEngine() {
  return {
    mode: "settle",
    deterministic: true,
    listPlayerActions: listMoveActions,
    applyPlayerAction: applyMove,
    stepEnvironment: stepWind,
    isEnvironmentStable: isWindStable,
    isGoal: isGoalSatisfied,
    serializeState,
  };
}

function formatSteps(steps) {
  return steps
    .map((step, index) => `${index + 1}. ${step.pieceId} -> (${step.toRow}, ${step.toCol}) via ${step.direction}`)
    .join("\n");
}

function runScenario(label, definition, engine) {
  const initialState = placeSpawnPieces(definition);
  const result = solve(initialState, engine);
  console.log(`\n[${label}]`);
  console.log(`solvable: ${result.solvable}`);
  console.log(`explored: ${result.explored}`);
  if (result.steps.length > 0) {
    console.log(formatSteps(result.steps));
  } else {
    console.log("no steps");
  }
  return result;
}

const staticScenario = {
  board: {
    rows: 3,
    cols: 4,
    zones: [
      {
        id: "spawn-target",
        role: "spawn",
        shape: { kind: "edge", side: "left", index: 1, w: 1, h: 1 },
        targetFilter: { pieceIds: ["target"] },
      },
      {
        id: "goal-target",
        role: "goal",
        shape: { kind: "rect", row: 1, col: 2, w: 1, h: 1 },
        targetFilter: { pieceIds: ["target"] },
      },
    ],
  },
  runtime: {},
  pieces: [
    {
      id: "target",
      kind: "gem",
      role: "target",
      movable: true,
      affectedByWind: false,
      blocksWind: true,
      spawnZoneId: "spawn-target",
    },
  ],
};

const windScenario = {
  board: {
    rows: 3,
    cols: 5,
    zones: [
      {
        id: "spawn-target",
        role: "spawn",
        shape: { kind: "rect", row: 1, col: 1, w: 1, h: 1 },
        targetFilter: { pieceIds: ["target"] },
      },
      {
        id: "spawn-shield",
        role: "spawn",
        shape: { kind: "rect", row: 1, col: 3, w: 1, h: 1 },
        targetFilter: { pieceIds: ["shield"] },
      },
      {
        id: "goal-target",
        role: "goal",
        shape: { kind: "edge", side: "right", index: 1, w: 1, h: 1 },
        targetFilter: { pieceIds: ["target"] },
      },
    ],
  },
  runtime: {
    wind: {
      direction: "east",
      active: true,
    },
  },
  pieces: [
    {
      id: "target",
      kind: "gem",
      role: "target",
      movable: true,
      affectedByWind: true,
      blocksWind: true,
      spawnZoneId: "spawn-target",
    },
    {
      id: "shield",
      kind: "wall",
      role: "blocker",
      movable: true,
      affectedByWind: false,
      blocksWind: true,
      spawnZoneId: "spawn-shield",
    },
  ],
};

const staticResult = runScenario("Static: edge spawn -> rect goal", staticScenario, createStaticEngine());
const windResult = runScenario("Settle: wind pushes target to edge goal", windScenario, createWindSettleEngine());

if (!staticResult.solvable || staticResult.steps.length !== 2) {
  throw new Error("Static scenario validation failed.");
}

if (!windResult.solvable || windResult.steps.length !== 1 || windResult.steps[0].pieceId !== "shield") {
  throw new Error("Wind scenario validation failed.");
}

console.log("\nPrototype validation passed.");
