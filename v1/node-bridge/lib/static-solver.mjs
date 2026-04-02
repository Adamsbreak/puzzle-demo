function clone(data) {
  return JSON.parse(JSON.stringify(data));
}

function getSolverBehavior(rulePack) {
  const solver = (rulePack && rulePack.solver) || {};
  const behavior = solver.behavior || {};
  return {
    targetLanePriority: behavior.targetLanePriority || "absolute",
    edgeGoalRelaxation: behavior.edgeGoalRelaxation || "final-step-only",
    stopGeneration: behavior.stopGeneration || "all-legal-stops",
  };
}

function isBoardCell(board, row, col) {
  return row >= 0 && row < board.rows && col >= 0 && col < board.cols;
}

function cellAt(board, row, col) {
  return board.cells[row] && board.cells[row][col];
}

function logicalCellToEdgeSlot(board, row, col) {
  if (row === -1 && col >= 0 && col < board.cols) return { side: "top", index: col };
  if (row === board.rows && col >= 0 && col < board.cols) return { side: "bottom", index: col };
  if (col === -1 && row >= 0 && row < board.rows) return { side: "left", index: row };
  if (col === board.cols && row >= 0 && row < board.rows) return { side: "right", index: row };
  return null;
}

function zoneSpanOnSide(zone, side) {
  return side === "top" || side === "bottom" ? zone.w : zone.h;
}

function zoneMatchesPiece(zone, piece) {
  const filter = zone.targetFilter;
  if (!filter) return true;
  if (filter.roles && filter.roles.length > 0 && !filter.roles.includes(piece.role)) return false;
  if (filter.pieceTypeIds && filter.pieceTypeIds.length > 0 && !filter.pieceTypeIds.includes(piece.typeId)) return false;
  return true;
}

function edgeGoalAtCell(puzzle, piece, row, col) {
  if (!piece || piece.role !== "target") return null;
  const edge = logicalCellToEdgeSlot(puzzle.board, row, col);
  if (!edge) return null;
  return (
    puzzle.zones.find(function (zone) {
      if (zone.role !== "goal" || zone.shapeKind !== "edge") return false;
      if (!zoneMatchesPiece(zone, piece)) return false;
      const span = zoneSpanOnSide(zone, zone.side);
      return zone.side === edge.side && edge.index >= zone.index && edge.index < zone.index + span;
    }) || null
  );
}

function destinationTouchesEdgeGoal(puzzle, piece, row, col, width, height) {
  if (!piece || piece.role !== "target") return false;
  for (let r = row; r < row + height; r += 1) {
    for (let c = col; c < col + width; c += 1) {
      if (!isBoardCell(puzzle.board, r, c) && edgeGoalAtCell(puzzle, piece, r, c)) {
        return true;
      }
    }
  }
  return false;
}

function overlap(a, b) {
  return a.row < b.row + b.h && a.row + a.h > b.row && a.col < b.col + b.w && a.col + a.w > b.col;
}

function directionAllowedByTags(tags, deltaRow, deltaCol) {
  if (!tags || tags.length === 0) return true;
  if (deltaRow === 0 && deltaCol === 0) return true;
  if (tags.includes("horizontal") && !tags.includes("vertical") && deltaRow !== 0) return false;
  if (tags.includes("vertical") && !tags.includes("horizontal") && deltaCol !== 0) return false;
  return true;
}

function cellAllowsPiece(puzzle, piece, row, col) {
  const cell = cellAt(puzzle.board, row, col);
  if (!cell) return false;
  const tags = cell.tags || [];
  if (tags.includes("blocked")) return false;
  if (tags.includes("block-lane") && piece.role === "target" && !tags.includes("target-lane")) return false;

  const moveRule = piece.moveRule || "free";
  if (moveRule === "target-lane") return tags.includes("target-lane");
  if (moveRule === "block-lane") return tags.includes("block-lane");
  return true;
}

function canOccupyFootprint(puzzle, piece, row, col, width, height) {
  let outsideSide = null;
  let matchedOutsideGoal = false;
  for (let r = row; r < row + height; r += 1) {
    for (let c = col; c < col + width; c += 1) {
      if (isBoardCell(puzzle.board, r, c)) {
        if (!cellAllowsPiece(puzzle, piece, r, c)) return false;
        continue;
      }

      const edge = logicalCellToEdgeSlot(puzzle.board, r, c);
      if (!edge) return false;
      if (outsideSide && outsideSide !== edge.side) return false;
      outsideSide = edge.side;
      const goal = edgeGoalAtCell(puzzle, piece, r, c);
      if (goal) {
        matchedOutsideGoal = true;
        continue;
      }
      return false;
    }
  }
  if (outsideSide && !matchedOutsideGoal) return false;
  return true;
}

function canPlace(puzzle, piece, row, col, width, height) {
  if (!canOccupyFootprint(puzzle, piece, row, col, width, height)) return false;

  return !puzzle.pieces.some(function (other) {
    return other.id !== piece.id && overlap({ row: row, col: col, w: width, h: height }, other);
  });
}

function collectSourceTags(puzzle, piece, fromRow, fromCol) {
  const tags = new Set();
  for (let r = fromRow; r < fromRow + piece.h; r += 1) {
    for (let c = fromCol; c < fromCol + piece.w; c += 1) {
      if (!isBoardCell(puzzle.board, r, c)) continue;
      const cell = cellAt(puzzle.board, r, c);
      (cell && cell.tags ? cell.tags : []).forEach(function (tag) {
        tags.add(tag);
      });
    }
  }
  return tags;
}

function canMovePiece(puzzle, piece, row, col, fromRow, fromCol, behavior) {
  const rowDiff = row - fromRow;
  const colDiff = col - fromCol;
  if (rowDiff !== 0 && colDiff !== 0) return false;
  if (rowDiff === 0 && colDiff === 0) return false;

  const sourceTags = collectSourceTags(puzzle, piece, fromRow, fromCol);
  const deltaRow = Math.sign(rowDiff);
  const deltaCol = Math.sign(colDiff);
  const targetLaneDominates =
    piece.role === "target" &&
    sourceTags.has("target-lane") &&
    behavior.targetLanePriority === "absolute";
  const targetLaneSourceBased =
    piece.role === "target" &&
    sourceTags.has("target-lane") &&
    behavior.targetLanePriority === "source-based";
  const requireHorizontalTrack =
    !targetLaneDominates && sourceTags.has("horizontal") && !sourceTags.has("vertical");
  const requireVerticalTrack =
    !targetLaneDominates && sourceTags.has("vertical") && !sourceTags.has("horizontal");
  const requireTargetLane = targetLaneDominates || targetLaneSourceBased;
  const requireBlockLane = piece.role !== "target" && sourceTags.has("block-lane");

  const steps = Math.max(Math.abs(rowDiff), Math.abs(colDiff));
  for (let step = 1; step <= steps; step += 1) {
    const nextRow = fromRow + deltaRow * step;
    const nextCol = fromCol + deltaCol * step;
    if (!canPlace(puzzle, piece, nextRow, nextCol, piece.w, piece.h)) return false;
    const stepTouchesEdgeGoal = destinationTouchesEdgeGoal(puzzle, piece, nextRow, nextCol, piece.w, piece.h);
    const relaxForThisStep =
      stepTouchesEdgeGoal &&
      (behavior.edgeGoalRelaxation === "full-path" ||
        (behavior.edgeGoalRelaxation === "final-step-only" && step === steps));

    for (let r = nextRow; r < nextRow + piece.h; r += 1) {
      for (let c = nextCol; c < nextCol + piece.w; c += 1) {
        if (!isBoardCell(puzzle.board, r, c)) continue;
        const cell = cellAt(puzzle.board, r, c);
        const tags = cell && cell.tags ? cell.tags : [];
        if (!relaxForThisStep) {
          if (!requireTargetLane && !directionAllowedByTags(tags, deltaRow, deltaCol)) return false;
          if (requireHorizontalTrack && !tags.includes("horizontal")) return false;
          if (requireVerticalTrack && !tags.includes("vertical")) return false;
          if (requireTargetLane && !tags.includes("target-lane")) return false;
          if (requireBlockLane && !tags.includes("block-lane")) return false;
        }
      }
    }
  }

  return true;
}

function allowedDirections(piece) {
  const moveRule = piece.moveRule || "free";
  if (!piece.movable || moveRule === "blocked") return [];
  if (moveRule === "horizontal") {
    return [
      { dr: 0, dc: -1, name: "left" },
      { dr: 0, dc: 1, name: "right" },
    ];
  }
  if (moveRule === "vertical") {
    return [
      { dr: -1, dc: 0, name: "up" },
      { dr: 1, dc: 0, name: "down" },
    ];
  }
  return [
    { dr: -1, dc: 0, name: "up" },
    { dr: 1, dc: 0, name: "down" },
    { dr: 0, dc: -1, name: "left" },
    { dr: 0, dc: 1, name: "right" },
  ];
}

function enumerateMoves(puzzle, behavior) {
  const moves = [];
  puzzle.pieces.forEach(function (piece) {
    allowedDirections(piece).forEach(function (dir) {
      let step = 1;
      let farthestMove = null;
      while (true) {
        const nextRow = piece.row + dir.dr * step;
        const nextCol = piece.col + dir.dc * step;
        if (!canMovePiece(puzzle, piece, nextRow, nextCol, piece.row, piece.col, behavior)) break;
        const move = {
          pieceId: piece.id,
          pieceName: piece.name,
          direction: dir.name,
          fromRow: piece.row,
          fromCol: piece.col,
          toRow: nextRow,
          toCol: nextCol,
        };
        if (behavior.stopGeneration === "farthest-only") {
          farthestMove = move;
        } else {
          moves.push(move);
        }
        step += 1;
      }
      if (farthestMove) moves.push(farthestMove);
    });
  });
  return moves;
}

function applyMove(puzzle, move) {
  const next = clone(puzzle);
  const piece = next.pieces.find(function (item) {
    return item.id === move.pieceId;
  });
  if (piece) {
    piece.row = move.toRow;
    piece.col = move.toCol;
  }
  return next;
}

function serializeState(puzzle) {
  return puzzle.pieces
    .slice()
    .sort(function (a, b) {
      return a.id.localeCompare(b.id);
    })
    .map(function (piece) {
      return [
        piece.id,
        piece.row,
        piece.col,
        piece.w,
        piece.h,
        piece.moveRule || "free",
        piece.role,
      ].join(":");
    })
    .join("|");
}

function buildEdgeZoneCells(state, zone) {
  const cells = [];
  const span = zoneSpanOnSide(zone, zone.side);
  for (let offset = 0; offset < span; offset += 1) {
    if (zone.side === "top") cells.push({ row: -1, col: zone.index + offset });
    else if (zone.side === "bottom") cells.push({ row: state.board.rows, col: zone.index + offset });
    else if (zone.side === "left") cells.push({ row: zone.index + offset, col: -1 });
    else cells.push({ row: zone.index + offset, col: state.board.cols });
  }
  return cells;
}

function pieceCells(piece) {
  const cells = [];
  for (let row = piece.row; row < piece.row + piece.h; row += 1) {
    for (let col = piece.col; col < piece.col + piece.w; col += 1) {
      cells.push({ row: row, col: col });
    }
  }
  return cells;
}

function isPieceInZone(state, piece, zone) {
  if (zone.role !== "goal" || !zoneMatchesPiece(zone, piece)) return false;

  if (zone.shapeKind === "rect") {
    const mode = zone.goalMode || "full";
    const zoneRect = { row: zone.row, col: zone.col, w: zone.w, h: zone.h };
    const pieceRect = { row: piece.row, col: piece.col, w: piece.w, h: piece.h };
    if (mode === "partial") return overlap(pieceRect, zoneRect);
    return (
      pieceRect.row >= zoneRect.row &&
      pieceRect.col >= zoneRect.col &&
      pieceRect.row + pieceRect.h <= zoneRect.row + zoneRect.h &&
      pieceRect.col + pieceRect.w <= zoneRect.col + zoneRect.w
    );
  }

  const zoneCells = buildEdgeZoneCells(state, zone);
  const zoneKeys = new Set(zoneCells.map(function (cell) {
    return cell.row + ":" + cell.col;
  }));
  const cells = pieceCells(piece);
  const matched = cells.filter(function (cell) {
    return zoneKeys.has(cell.row + ":" + cell.col);
  });
  if ((zone.goalMode || "full") === "partial") return matched.length > 0;
  return matched.length === cells.length && cells.length > 0;
}

export function evaluateGoals(state) {
  const targets = state.pieces.filter(function (piece) {
    return piece.role === "target";
  });
  const goalZones = state.zones.filter(function (zone) {
    return zone.role === "goal";
  });

  const satisfied = [];
  const unsatisfied = [];
  targets.forEach(function (piece) {
    const hit = goalZones.some(function (zone) {
      return isPieceInZone(state, piece, zone);
    });
    if (hit) satisfied.push(piece.id);
    else unsatisfied.push(piece.id);
  });

  return {
    solved: targets.length > 0 && unsatisfied.length === 0,
    satisfiedPieceIds: satisfied,
    unsatisfiedPieceIds: unsatisfied,
  };
}

export function validatePuzzle(state, rulePack) {
  const findings = [];
  const targetPieces = state.pieces.filter(function (piece) {
    return piece.role === "target";
  });

  if (targetPieces.length === 0) findings.push("At least one target piece is required.");
  if (!state.zones.some(function (zone) { return zone.role === "goal"; })) {
    findings.push("At least one goal zone is required.");
  }

  if (
    rulePack &&
    Array.isArray(rulePack.goals) &&
    rulePack.goals.some(function (goal) { return goal.type === "all-targets-reach-goals"; }) &&
    targetPieces.length > 0 &&
    !state.zones.some(function (zone) { return zone.role === "goal"; })
  ) {
    findings.push("The active rule pack requires goal zones for target pieces.");
  }

  return {
    valid: findings.length === 0,
    findings: findings,
  };
}

export function solveStaticPuzzle(puzzleSpec, rulePack) {
  const maxNodes = (rulePack && rulePack.solver && rulePack.solver.maxNodes) || 50000;
  const behavior = getSolverBehavior(rulePack);
  const initial = clone(puzzleSpec);
  const initialGoal = evaluateGoals(initial);

  if (initialGoal.solved) {
    return {
      status: "solved",
      summary: "The current layout already satisfies the goal.",
      steps: [],
      exploredNodes: 1,
      stepCount: 0,
    };
  }

  const queue = [{
    puzzle: initial,
    steps: [],
  }];
  const seen = new Set([serializeState(initial)]);
  let exploredNodes = 0;

  while (queue.length > 0) {
    const current = queue.shift();
    exploredNodes += 1;
    if (exploredNodes > maxNodes) {
      return {
        status: "search-limit",
        summary: "Search node limit reached before finding a solution.",
        exploredNodes: exploredNodes,
        maxNodes: maxNodes,
      };
    }

    const moves = enumerateMoves(current.puzzle, behavior);
    for (let i = 0; i < moves.length; i += 1) {
      const move = moves[i];
      const nextPuzzle = applyMove(current.puzzle, move);
      const key = serializeState(nextPuzzle);
      if (seen.has(key)) continue;
      seen.add(key);

      const nextSteps = current.steps.concat([move]);
      const goalState = evaluateGoals(nextPuzzle);
      if (goalState.solved) {
        return {
          status: "solved",
          summary: "Solved with the minimum number of operations.",
          exploredNodes: exploredNodes,
          stepCount: nextSteps.length,
          steps: nextSteps,
          satisfiedPieceIds: goalState.satisfiedPieceIds,
        };
      }

      queue.push({
        puzzle: nextPuzzle,
        steps: nextSteps,
      });
    }
  }

  return {
    status: "no-solution",
    summary: "No solution found under the current static rules.",
    exploredNodes: exploredNodes,
    maxNodes: maxNodes,
  };
}

function capCount(value, maxCount) {
  return Math.min(value, maxCount);
}

function summarizeInitialMoves(puzzleSpec, rulePack) {
  const behavior = getSolverBehavior(rulePack);
  const moves = enumerateMoves(clone(puzzleSpec), behavior);
  const pieceMoveCounts = {};
  moves.forEach(function (move) {
    pieceMoveCounts[move.pieceId] = (pieceMoveCounts[move.pieceId] || 0) + 1;
  });
  return {
    initialMoveCount: moves.length,
    pieceMoveCounts: pieceMoveCounts,
  };
}

function countShortestSolutions(puzzleSpec, rulePack, maxSolutions) {
  const cap = Math.max(1, Number(maxSolutions) || 2);
  const behavior = getSolverBehavior(rulePack);
  const initial = clone(puzzleSpec);
  const initialGoal = evaluateGoals(initial);
  if (initialGoal.solved) {
    return {
      shortestStepCount: 0,
      solutionCount: 1,
      capped: false,
    };
  }

  let depth = 0;
  let exploredNodes = 0;
  const seenDepth = new Map([[serializeState(initial), 0]]);
  let frontier = new Map([[serializeState(initial), { puzzle: initial, count: 1 }]]);
  const maxNodes = (rulePack && rulePack.solver && rulePack.solver.maxNodes) || 50000;

  while (frontier.size > 0) {
    const nextFrontier = new Map();
    let solutionCount = 0;
    let capped = false;

    for (const entry of frontier.values()) {
      exploredNodes += 1;
      if (exploredNodes > maxNodes) {
        return {
          shortestStepCount: null,
          solutionCount: 0,
          capped: false,
          aborted: true,
          reason: "search-limit",
        };
      }

      const moves = enumerateMoves(entry.puzzle, behavior);
      for (let i = 0; i < moves.length; i += 1) {
        const move = moves[i];
        const nextPuzzle = applyMove(entry.puzzle, move);
        const key = serializeState(nextPuzzle);
        const nextDepth = depth + 1;
        const priorDepth = seenDepth.get(key);
        if (priorDepth != null && priorDepth < nextDepth) continue;
        if (priorDepth == null) seenDepth.set(key, nextDepth);

        const goalState = evaluateGoals(nextPuzzle);
        if (goalState.solved) {
          solutionCount = capCount(solutionCount + entry.count, cap);
          capped = capped || solutionCount >= cap;
          continue;
        }

        const bucket = nextFrontier.get(key);
        if (bucket) {
          bucket.count = capCount(bucket.count + entry.count, cap);
        } else {
          nextFrontier.set(key, {
            puzzle: nextPuzzle,
            count: capCount(entry.count, cap),
          });
        }
      }
    }

    if (solutionCount > 0) {
      return {
        shortestStepCount: depth + 1,
        solutionCount: solutionCount,
        capped: capped,
        aborted: false,
      };
    }

    frontier = nextFrontier;
    depth += 1;
  }

  return {
    shortestStepCount: null,
    solutionCount: 0,
    capped: false,
    aborted: false,
  };
}

function summarizeMechanics(puzzleSpec) {
  const totals = {
    horizontal: 0,
    vertical: 0,
    "block-lane": 0,
    "target-lane": 0,
    blocked: 0,
  };
  const totalCells = Math.max(1, puzzleSpec.board.rows * puzzleSpec.board.cols);
  puzzleSpec.board.cells.forEach(function (row) {
    row.forEach(function (cell) {
      const tags = cell && Array.isArray(cell.tags) ? cell.tags : [];
      Object.keys(totals).forEach(function (tag) {
        if (tags.includes(tag)) totals[tag] += 1;
      });
    });
  });

  const edgeGoalZones = puzzleSpec.zones.filter(function (zone) {
    return zone.role === "goal" && zone.shapeKind === "edge";
  }).length;
  const rectGoalZones = puzzleSpec.zones.filter(function (zone) {
    return zone.role === "goal" && zone.shapeKind === "rect";
  }).length;

  return {
    totalCells: totalCells,
    cellTagCounts: totals,
    zoneMechanics: {
      edgeGoalZones: edgeGoalZones,
      rectGoalZones: rectGoalZones,
    },
  };
}

export function inspectStaticPuzzle(puzzleSpec, rulePack, options) {
  const validation = validatePuzzle(puzzleSpec, rulePack);
  const goalState = evaluateGoals(puzzleSpec);
  const moveSummary = summarizeInitialMoves(puzzleSpec, rulePack);
  const shortestSolutions = countShortestSolutions(
    puzzleSpec,
    rulePack,
    options && options.maxSolutions ? options.maxSolutions : 2,
  );
  const solveResult = validation.valid ? solveStaticPuzzle(puzzleSpec, rulePack) : null;

  return {
    validation: validation,
    goalState: goalState,
    frontier: moveSummary,
    shortestSolutions: shortestSolutions,
    mechanics: summarizeMechanics(puzzleSpec),
    solve: solveResult,
  };
}
