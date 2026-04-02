(function () {
  const root = window.PuzzleV1;

  function getCell(state, row, col) {
    return state.board.cells[row] && state.board.cells[row][col];
  }

  function normalizeTags(tags) {
    const unique = Array.from(new Set((tags || []).filter(Boolean)));
    return unique.includes("blocked")
      ? ["blocked"]
      : unique.filter(function (tag) {
          return tag !== "blocked";
        });
  }

  function applyTagToCell(state, row, col) {
    const cell = getCell(state, row, col);
    if (!cell) return;

    const tagId = state.ui.selectedTagId;
    if (state.ui.paintMode === "clear") {
      cell.tags = [];
      return;
    }

    const current = new Set(cell.tags || []);
    if (state.ui.paintMode === "add") {
      if (tagId === "blocked") {
        cell.tags = ["blocked"];
        return;
      }
      current.delete("blocked");
      current.add(tagId);
    } else {
      current.delete(tagId);
    }
    cell.tags = normalizeTags(Array.from(current));
  }

  function resizeBoard(state, rows, cols, cellSize) {
    state.board.rows = rows;
    state.board.cols = cols;
    state.board.cellSize = cellSize;
    state.board.cells = root.createCells(rows, cols);
    state.pieces = state.pieces.filter(function (piece) {
      return piece.row >= 0 && piece.col >= 0 && piece.row + piece.h <= rows && piece.col + piece.w <= cols;
    });
    state.zones = state.zones.filter(function (zone) {
      if (zone.shapeKind === "rect") {
        return zone.row + zone.h <= rows && zone.col + zone.w <= cols;
      }
      if (zone.side === "top" || zone.side === "bottom") {
        return zone.index + zone.w <= cols;
      }
      return zone.index + zone.h <= rows;
    });
  }

  function exportPuzzleSpec(state) {
    return JSON.stringify(
      {
        meta: state.meta,
        board: state.board,
        pieces: state.pieces,
        zones: state.zones,
      },
      null,
      2,
    );
  }

  function importPuzzleSpec(state, rawText) {
    const parsed = JSON.parse(rawText);
    state.meta = parsed.meta || state.meta;
    state.board.rows = parsed.board.rows;
    state.board.cols = parsed.board.cols;
    state.board.cellSize = parsed.board.cellSize;
    state.board.cells = parsed.board.cells;
    state.pieces = parsed.pieces || [];
    state.zones = parsed.zones || [];
    state.zones.forEach(function (zone) {
      if (!zone.goalMode) zone.goalMode = "full";
    });
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

  function overlap(a, b) {
    return a.row < b.row + b.h && a.row + a.h > b.row && a.col < b.col + b.w && a.col + a.w > b.col;
  }

  function edgeSlotToLogicalCell(state, side, index) {
    if (side === "top") return { row: -1, col: index };
    if (side === "bottom") return { row: state.board.rows, col: index };
    if (side === "left") return { row: index, col: -1 };
    return { row: index, col: state.board.cols };
  }

  function buildEdgeZoneCells(state, zone) {
    const cells = [];
    const span = zoneSpanOnSide(zone, zone.side);
    for (let offset = 0; offset < span; offset += 1) {
      cells.push(edgeSlotToLogicalCell(state, zone.side, zone.index + offset));
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

  function evaluateGoals(state) {
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
      if (hit) {
        satisfied.push(piece.id);
      } else {
        unsatisfied.push(piece.id);
      }
    });

    return {
      solved: targets.length > 0 && unsatisfied.length === 0,
      satisfiedPieceIds: satisfied,
      unsatisfiedPieceIds: unsatisfied,
    };
  }

  function validatePuzzle(state, rulePack) {
    const findings = [];
    const targetPieces = state.pieces.filter(function (piece) {
      return piece.role === "target";
    });

    if (targetPieces.length === 0) {
      findings.push("至少需要一个目标物。");
    }

    if (!state.zones.some(function (zone) { return zone.role === "goal"; })) {
      findings.push("至少需要一个终点区域。");
    }

    if (
      rulePack.goals.some(function (goal) {
        return goal.type === "all-targets-reach-goals";
      }) &&
      targetPieces.length > 0 &&
      !state.zones.some(function (zone) {
        return zone.role === "goal";
      })
    ) {
      findings.push("当前规则包要求目标物到达终点，但还没有配置终点区域。");
    }

    return {
      valid: findings.length === 0,
      findings: findings,
    };
  }

  root.getCell = getCell;
  root.applyTagToCell = applyTagToCell;
  root.resizeBoard = resizeBoard;
  root.exportPuzzleSpec = exportPuzzleSpec;
  root.importPuzzleSpec = importPuzzleSpec;
  root.evaluateGoals = evaluateGoals;
  root.validatePuzzle = validatePuzzle;
})();
