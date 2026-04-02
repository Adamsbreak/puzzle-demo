import type {
  CellState,
  CellTag,
  EditorState,
  Piece,
  PieceRole,
  PuzzleSnapshot,
  RuntimeState,
  Zone,
  ZoneRole,
  ZoneShapeKind,
  ZoneSide,
} from "./types";

export function createCells(rows: number, cols: number): CellState[][] {
  return Array.from({ length: rows }, () =>
    Array.from({ length: cols }, () => ({ tags: [] })),
  );
}

export function createEditorState(): EditorState {
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

export function createRuntimeState(
  runtime: Partial<RuntimeState> | null = null,
): RuntimeState {
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

export function normTags(tags: CellTag[]): CellTag[] {
  const unique = [...new Set((tags || []).filter(Boolean))] as CellTag[];
  return unique.includes("blocked")
    ? ["blocked"]
    : unique.filter((tag) => tag !== "blocked");
}

export function getCell(state: EditorState | PuzzleSnapshot, row: number, col: number) {
  return state.cells[row]?.[col];
}

export function setCellTags(
  state: EditorState,
  row: number,
  col: number,
  tags: CellTag[],
): void {
  const cell = getCell(state, row, col);
  if (cell) {
    cell.tags = normTags(tags);
  }
}

export function mutateCell(state: EditorState, row: number, col: number): void {
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
    cell.tags = normTags([...currentTags] as CellTag[]);
    return;
  }

  currentTags.delete(state.selectedTag);
  cell.tags = normTags([...currentTags] as CellTag[]);
}

export function makePiece(state: EditorState, role: PieceRole): Piece {
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

export function clonePiece(state: EditorState, piece: Piece): Piece {
  return {
    ...piece,
    id: `piece-${state.nextPieceId++}`,
    name: `${piece.name} Copy`,
  };
}

export function makeZone(
  state: EditorState,
  shapeKind: ZoneShapeKind,
  anchor: { side?: ZoneSide; index?: number; row?: number; col?: number } = {},
): Zone {
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

export function selectedPiece(state: EditorState): Piece | null {
  return state.pieces.find((piece) => piece.id === state.selectedPieceId) || null;
}

export function normalizePiece(
  state: EditorState,
  piece: Record<string, unknown>,
  index: number,
): Piece {
  return {
    id: String(piece.id || `piece-${state.nextPieceId + index}`),
    type: "piece",
    name: String(piece.name || piece.label || `Piece ${index + 1}`),
    role:
      (piece.role as PieceRole) ||
      (piece.type === "target" || piece.kind === "target" || piece.isTarget
        ? "target"
        : "normal"),
    row: Number(piece.row ?? piece.y ?? 0) || 0,
    col: Number(piece.col ?? piece.x ?? 0) || 0,
    w: Math.max(1, Number(piece.w ?? piece.width ?? 1) || 1),
    h: Math.max(1, Number(piece.h ?? piece.height ?? 1) || 1),
    moveRule: (piece.moveRule || piece.movementRule || piece.axis || "free") as Piece["moveRule"],
    color: String(piece.color || piece.fill || "#d26a4c"),
    affectedByWind: Boolean(piece.affectedByWind ?? piece.role === "target"),
    blocksWind: piece.blocksWind === false ? false : true,
    spawnZoneId: (piece.spawnZoneId as string | null) ?? null,
  };
}

export function normalizeZone(
  state: EditorState,
  zone: Record<string, unknown>,
  index: number,
): Zone {
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
    role: (zone.role || legacyRole || "goal") as ZoneRole,
    shapeKind: (zone.shapeKind || (zone.side ? "edge" : "rect")) as ZoneShapeKind,
    side: zone.side as ZoneSide | undefined,
    index: zone.index == null ? undefined : Number(zone.index),
    row: zone.row == null ? undefined : Number(zone.row),
    col: zone.col == null ? undefined : Number(zone.col),
    w: Math.max(1, Number(zone.w ?? zone.width ?? 1) || 1),
    h: Math.max(1, Number(zone.h ?? zone.height ?? 1) || 1),
    color: String(zone.color || zone.fill || "#3f7dd1"),
    targetFilter: (zone.targetFilter as Zone["targetFilter"]) || null,
  };
}

export function resetStats(state: EditorState): void {
  state.stats.operations = 0;
  state.stats.distance = 0;
}

export function clonePuzzleState(state: EditorState | PuzzleSnapshot): PuzzleSnapshot {
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
