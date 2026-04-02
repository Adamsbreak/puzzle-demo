import { clonePuzzleState } from "./model";
import { canPlace, isSolvedState } from "./rules";
import type {
  Direction,
  EnvironmentRule,
  EditorState,
  Piece,
  PuzzleSnapshot,
  RuleEngine,
  SolverMove,
  SolverResult,
} from "./types";

const DIRECTION_DELTAS = {
  north: { dr: -1, dc: 0 },
  south: { dr: 1, dc: 0 },
  west: { dr: 0, dc: -1 },
  east: { dr: 0, dc: 1 },
} satisfies Record<Direction, { dr: number; dc: number }>;

function serializeState(state: EditorState | PuzzleSnapshot): string {
  const piecesKey = state.pieces
    .map((piece) => `${piece.id}:${piece.row},${piece.col}`)
    .sort()
    .join("|");
  const runtimeKey = JSON.stringify(state.runtime || {});
  return `${piecesKey}#${runtimeKey}`;
}

function cloneSolverState(state: EditorState | PuzzleSnapshot): PuzzleSnapshot {
  return clonePuzzleState(state);
}

function buildMove(
  piece: Piece,
  nextRow: number,
  nextCol: number,
  direction: Direction,
): SolverMove {
  return {
    pieceId: piece.id,
    pieceName: piece.name,
    fromRow: piece.row,
    fromCol: piece.col,
    toRow: nextRow,
    toCol: nextCol,
    direction,
  };
}

function candidateDirections(piece: Piece): Direction[] {
  if (piece.moveRule === "blocked") {
    return [];
  }
  if (piece.moveRule === "horizontal") {
    return ["west", "east"];
  }
  if (piece.moveRule === "vertical") {
    return ["north", "south"];
  }
  return ["north", "south", "west", "east"];
}

export function listLegalMoves(state: EditorState | PuzzleSnapshot): SolverMove[] {
  const moves: SolverMove[] = [];
  state.pieces.forEach((piece) => {
    candidateDirections(piece).forEach((direction) => {
      const delta = DIRECTION_DELTAS[direction];
      const nextRow = piece.row + delta.dr;
      const nextCol = piece.col + delta.dc;
      if (canPlace(state, piece, nextRow, nextCol)) {
        moves.push(buildMove(piece, nextRow, nextCol, direction));
      }
    });
  });
  return moves;
}

export function applyMove(
  state: EditorState | PuzzleSnapshot,
  move: SolverMove,
): PuzzleSnapshot {
  const nextState = cloneSolverState(state);
  const piece = nextState.pieces.find((item) => item.id === move.pieceId);
  if (piece) {
    piece.row = move.toRow;
    piece.col = move.toCol;
  }
  return nextState;
}

function isRuleActive(
  rule: EnvironmentRule,
  state: EditorState | PuzzleSnapshot,
): boolean {
  return rule.isActive ? rule.isActive(state) : true;
}

function stepWind(state: EditorState | PuzzleSnapshot): PuzzleSnapshot {
  const nextState = cloneSolverState(state);
  const wind = nextState.runtime.wind;
  if (!wind?.active) {
    return nextState;
  }

  const delta = DIRECTION_DELTAS[wind.direction];
  const pieces = nextState.pieces
    .filter((piece) => piece.affectedByWind)
    .sort((a, b) => {
      if (wind.direction === "east") {
        return b.col - a.col;
      }
      if (wind.direction === "west") {
        return a.col - b.col;
      }
      if (wind.direction === "south") {
        return b.row - a.row;
      }
      return a.row - b.row;
    });

  pieces.forEach((piece) => {
    const nextRow = piece.row + delta.dr;
    const nextCol = piece.col + delta.dc;
    if (canPlace(nextState, piece, nextRow, nextCol)) {
      piece.row = nextRow;
      piece.col = nextCol;
    }
  });

  return nextState;
}

function isWindStable(state: EditorState | PuzzleSnapshot): boolean {
  const wind = state.runtime.wind;
  if (!wind?.active) {
    return true;
  }
  const delta = DIRECTION_DELTAS[wind.direction];
  return state.pieces
    .filter((piece) => piece.affectedByWind)
    .every((piece) => !canPlace(state, piece, piece.row + delta.dr, piece.col + delta.dc));
}

function createWindRule(): EnvironmentRule {
  return {
    id: "wind",
    mode: "settle",
    isActive: (state) => Boolean(state.runtime.wind?.active),
    step: stepWind,
    isStable: isWindStable,
  };
}

function applyEnvironmentRulesOnce(
  state: PuzzleSnapshot,
  rules: EnvironmentRule[],
): PuzzleSnapshot {
  return rules.reduce((current, rule) => {
    if (!isRuleActive(rule, current)) {
      return current;
    }
    return rule.step(current);
  }, cloneSolverState(state));
}

function settleUntilStable(
  state: PuzzleSnapshot,
  rules: EnvironmentRule[],
  maxSteps = 64,
): PuzzleSnapshot {
  let current = cloneSolverState(state);
  const seen = new Set<string>([serializeState(current)]);

  for (let i = 0; i < maxSteps; i += 1) {
    const pendingRules = rules.filter((rule) => isRuleActive(rule, current));
    if (pendingRules.length === 0) {
      return current;
    }
    const stable = pendingRules.every(
      (rule) => !rule.isStable || rule.isStable(current),
    );
    if (stable) {
      return current;
    }
    const nextState = applyEnvironmentRulesOnce(current, pendingRules);
    const key = serializeState(nextState);
    if (seen.has(key)) {
      return nextState;
    }
    seen.add(key);
    current = nextState;
  }

  return current;
}

function advanceRuntimeTick(state: PuzzleSnapshot): PuzzleSnapshot {
  const nextState = cloneSolverState(state);
  nextState.runtime.tick += 1;
  return nextState;
}

function determineSolverMode(rules: EnvironmentRule[]): SolverMode {
  if (rules.some((rule) => rule.mode === "tick")) {
    return "tick";
  }
  if (rules.some((rule) => rule.mode === "settle")) {
    return "settle";
  }
  return "static";
}

function advanceEnvironmentWithRules(
  state: PuzzleSnapshot,
  rules: EnvironmentRule[],
): PuzzleSnapshot {
  if (rules.length === 0) {
    return cloneSolverState(state);
  }

  const settleRules = rules.filter((rule) => rule.mode === "settle");
  const tickRules = rules.filter((rule) => rule.mode === "tick");

  let current = cloneSolverState(state);
  if (settleRules.length > 0) {
    current = settleUntilStable(current, settleRules);
  }
  if (tickRules.length > 0) {
    current = advanceRuntimeTick(current);
    current = applyEnvironmentRulesOnce(current, tickRules);
  }
  if (settleRules.length > 0) {
    current = settleUntilStable(current, settleRules);
  }

  return current;
}

export function createStaticRuleEngine(): RuleEngine {
  return {
    mode: "static",
    deterministic: true,
    listPlayerActions: listLegalMoves,
    applyPlayerAction: applyMove,
    isGoal: isSolvedState,
    serializeState,
  };
}

export function createEnvironmentRuleEngine(rules: EnvironmentRule[]): RuleEngine {
  const mode = determineSolverMode(rules);
  if (mode === "static") {
    return createStaticRuleEngine();
  }
  return {
    mode,
    deterministic: true,
    listPlayerActions: listLegalMoves,
    applyPlayerAction: applyMove,
    advanceEnvironment: (state) => advanceEnvironmentWithRules(state, rules),
    isGoal: isSolvedState,
    serializeState,
  };
}

export function createWindRuleEngine(): RuleEngine {
  return createEnvironmentRuleEngine([createWindRule()]);
}

export function resolveEnvironmentRules(
  state: EditorState | PuzzleSnapshot,
): EnvironmentRule[] {
  const rules: EnvironmentRule[] = [];
  if (state.runtime.wind?.active) {
    rules.push(createWindRule());
  }
  return rules;
}

export function resolveRuleEngine(state: EditorState | PuzzleSnapshot): RuleEngine {
  return createEnvironmentRuleEngine(resolveEnvironmentRules(state));
}

export function solvePuzzle(
  initialState: EditorState | PuzzleSnapshot,
  options: { maxNodes?: number; ruleEngine?: RuleEngine } = {},
): SolverResult {
  const maxNodes = options.maxNodes ?? 30000;
  const engine = options.ruleEngine || resolveRuleEngine(initialState);
  const start = cloneSolverState(initialState);
  const queue: Array<{ state: PuzzleSnapshot; steps: SolverMove[] }> = [
    { state: start, steps: [] },
  ];
  const seen = new Set<string>([engine.serializeState(start)]);
  let explored = 0;

  while (queue.length > 0) {
    const current = queue.shift();
    if (!current) {
      break;
    }

    explored += 1;
    if (engine.isGoal(current.state)) {
      return {
        solvable: true,
        steps: current.steps,
        explored,
        truncated: false,
        mode: engine.mode,
      };
    }

    if (explored >= maxNodes) {
      return {
        solvable: false,
        steps: [],
        explored,
        truncated: true,
        mode: engine.mode,
      };
    }

    engine.listPlayerActions(current.state).forEach((move) => {
      let nextState = engine.applyPlayerAction(current.state, move);
      if (engine.advanceEnvironment) {
        nextState = engine.advanceEnvironment(nextState);
      }

      const key = engine.serializeState(nextState);
      if (seen.has(key)) {
        return;
      }
      seen.add(key);
      queue.push({ state: nextState, steps: [...current.steps, move] });
    });
  }

  return {
    solvable: false,
    steps: [],
    explored,
    truncated: false,
    mode: engine.mode,
  };
}
