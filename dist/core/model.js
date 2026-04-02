export function createCells(rows, cols) {
  return Array.from({ length: rows }, () =>
    Array.from({ length: cols }, () => ({ tags: [] })),
  );
}

export function createEditorState() {
  return {
    rows: 6,
    cols: 6,
    cellSize: 64,
    showCoords: true,
    mainMode: "cells",
    paintMode: "add",
    selectedTag: "horizontal",
    cells: createCells(6, 6),
    pieces: [],
    zones: [],
    runtime: createRuntimeState(),
    selectedPieceId: null,
    clipboard: null,
    nextPieceId: 1,
    nextZoneId: 1,
    dragging: null,
    stats: { operations: 0, distance: 0 },
  };
}

export function createRuntimeState(runtime = null) {
  return {
    tick: runtime?.tick ?? 0,
    wind: runtime?.wind ? { ...runtime.wind } : null,
    flags: { ...(runtime?.flags || {}) },
    entities: (runtime?.entities || []).map((entity) => ({
      ...entity,
      data: entity.data ? { ...entity.data } : undefined,
    })),
  };
}

export function normTags(tags) {
  const unique = [...new Set((tags || []).filter(Boolean))];
  return unique.includes("blocked")
    ? ["blocked"]
    : unique.filter((tag) => tag !== "blocked");
}

export function getCell(state, row, col) {
  return state.cells[row]?.[col];
}

export function setCellTags(state, row, col, tags) {
  const cell = getCell(state, row, col);
  if (cell) {
    cell.tags = normTags(tags);
  }
}

export function mutateCell(state, row, col) {
  const cell = getCell(state, row, col);
  if (!cell) {
    return;
  }

  const currentTags = new Set(cell.tags || []);
  if (state.paintMode === "clear") {
    cell.tags = [];
    return;
  }

  if (state.paintMode === "add") {
    if (state.selectedTag === "blocked") {
      cell.tags = ["blocked"];
      return;
    }
    currentTags.delete("blocked");
    currentTags.add(state.selectedTag);
    cell.tags = normTags([...currentTags]);
    return;
  }

  currentTags.delete(state.selectedTag);
  cell.tags = normTags([...currentTags]);
}

export function makePiece(state, role) {
  const id = `piece-${state.nextPieceId++}`;
  const number = state.nextPieceId - 1;
  return {
    id,
    type: "piece",
    name: role === "target" ? `Target ${number}` : `Block ${number}`,
    role,
    row: 0,
    col: 0,
    w: 1,
    h: 1,
    moveRule: "free",
    color: role === "target" ? "#bc8d16" : "#d26a4c",
    affectedByWind: role === "target",
    blocksWind: true,
    spawnZoneId: null,
  };
}

export function clonePiece(state, piece) {
  return {
    ...piece,
    id: `piece-${state.nextPieceId++}`,
    name: `${piece.name} Copy`,
  };
}

export function makeZone(state, shapeKind, anchor = {}) {
  const id = `zone-${state.nextZoneId++}`;
  const number = state.nextZoneId - 1;
  return {
    id,
    type: "zone",
    name: `Zone ${number}`,
    role: "goal",
    shapeKind,
    side: anchor.side,
    index: anchor.index,
    row: anchor.row,
    col: anchor.col,
    w: 1,
    h: 1,
    color: "#3f7dd1",
    targetFilter: null,
  };
}

export function selectedPiece(state) {
  return state.pieces.find((piece) => piece.id === state.selectedPieceId) || null;
}

export function normalizePiece(state, piece, index) {
  return {
    id: String(piece.id || `piece-${state.nextPieceId + index}`),
    type: "piece",
    name: String(piece.name || piece.label || `Piece ${index + 1}`),
    role:
      piece.role ||
      (piece.type === "target" || piece.kind === "target" || piece.isTarget
        ? "target"
        : "normal"),
    row: Number(piece.row ?? piece.y ?? 0) || 0,
    col: Number(piece.col ?? piece.x ?? 0) || 0,
    w: Math.max(1, Number(piece.w ?? piece.width ?? 1) || 1),
    h: Math.max(1, Number(piece.h ?? piece.height ?? 1) || 1),
    moveRule: piece.moveRule || piece.movementRule || piece.axis || "free",
    color: String(piece.color || piece.fill || "#d26a4c"),
    affectedByWind: Boolean(piece.affectedByWind ?? piece.role === "target"),
    blocksWind: piece.blocksWind === false ? false : true,
    spawnZoneId: piece.spawnZoneId ?? null,
  };
}

export function normalizeZone(state, zone, index) {
  const legacyRole =
    zone.regionType === "entrance"
      ? "spawn"
      : zone.regionType === "exit"
        ? "goal"
        : undefined;

  return {
    id: String(zone.id || `zone-${state.nextZoneId + index}`),
    type: "zone",
    name: String(zone.name || zone.label || `Zone ${index + 1}`),
    role: zone.role || legacyRole || "goal",
    shapeKind: zone.shapeKind || (zone.side ? "edge" : "rect"),
    side: zone.side,
    index: zone.index == null ? undefined : Number(zone.index),
    row: zone.row == null ? undefined : Number(zone.row),
    col: zone.col == null ? undefined : Number(zone.col),
    w: Math.max(1, Number(zone.w ?? zone.width ?? 1) || 1),
    h: Math.max(1, Number(zone.h ?? zone.height ?? 1) || 1),
    color: String(zone.color || zone.fill || "#3f7dd1"),
    targetFilter: zone.targetFilter || null,
  };
}

export function resetStats(state) {
  state.stats.operations = 0;
  state.stats.distance = 0;
}

export function clonePuzzleState(state) {
  return {
    rows: state.rows,
    cols: state.cols,
    cellSize: state.cellSize,
    cells: state.cells.map((row) => row.map((cell) => ({ tags: [...cell.tags] }))),
    pieces: state.pieces.map((piece) => ({ ...piece })),
    zones: state.zones.map((zone) => ({
      ...zone,
      targetFilter: zone.targetFilter ? { ...zone.targetFilter } : null,
    })),
    runtime: createRuntimeState(state.runtime),
  };
}
