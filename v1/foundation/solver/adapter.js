(function () {
  const root = window.PuzzleV1;

  function clone(data) {
    return JSON.parse(JSON.stringify(data));
  }

  function resolveBehavior(rulePack) {
    const behavior = (rulePack && rulePack.solver && rulePack.solver.behavior) || {};
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
    return puzzle.zones.find(function (zone) {
      if (zone.role !== "goal" || zone.shapeKind !== "edge") return false;
      if (!zoneMatchesPiece(zone, piece)) return false;
      const span = zoneSpanOnSide(zone, zone.side);
      return zone.side === edge.side && edge.index >= zone.index && edge.index < zone.index + span;
    }) || null;
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
      const stepTouchesEdgeGoal =
        destinationTouchesEdgeGoal(puzzle, piece, nextRow, nextCol, piece.w, piece.h);
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
    if (moveRule === "horizontal") return [
      { dr: 0, dc: -1, name: "left" },
      { dr: 0, dc: 1, name: "right" },
    ];
    if (moveRule === "vertical") return [
      { dr: -1, dc: 0, name: "up" },
      { dr: 1, dc: 0, name: "down" },
    ];
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
          farthestMove = move;
          if (behavior.stopGeneration === "farthest-only") {
            step += 1;
            continue;
          }
          moves.push(move);
          step += 1;
        }
        if (behavior.stopGeneration === "farthest-only" && farthestMove) {
          moves.push(farthestMove);
        }
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

  function evaluateGoals(puzzle) {
    if (root.evaluateGoals) return root.evaluateGoals(puzzle);
    return { solved: false, satisfiedPieceIds: [], unsatisfiedPieceIds: [] };
  }

  function solveStaticPuzzle(puzzleSpec, rulePack) {
    const maxNodes = (rulePack.solver && rulePack.solver.maxNodes) || 50000;
    const behavior = resolveBehavior(rulePack);
    const initial = clone(puzzleSpec);
    const initialGoal = evaluateGoals(initial);

    if (initialGoal.solved) {
      return {
        status: "solved",
        summary: "当前布局已经满足终点条件。",
        steps: [],
        exploredNodes: 1,
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
          summary: "搜索节点已达到上限，当前未找到解。",
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
            summary: "已找到最少步数解。",
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
      summary: "当前规则下没有搜索到可行解。",
      exploredNodes: exploredNodes,
      maxNodes: maxNodes,
    };
  }

  root.setSolverAdapter({
    id: "builtin-static-bfs",
    kind: "builtin",
    description: "内置静态谜题 BFS 求解器，按最少操作步数搜索。",
    solve: function solve(puzzleSpec, rulePack) {
      const report = root.validatePuzzle ? root.validatePuzzle(puzzleSpec, rulePack) : { valid: true, findings: [] };
      if (!report.valid) {
        return {
          status: "invalid-puzzle",
          summary: "当前谜题结构不合法，不能开始求解。",
          findings: report.findings,
        };
      }
      return solveStaticPuzzle(puzzleSpec, rulePack);
    },
  });
})();
