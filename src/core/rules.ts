import { getCell } from "./model";
import type { EditorState, Piece, PuzzleSnapshot, Zone } from "./types";

export function tagLabel(tag: string): string {
  return (
    {
      free: "自",
      horizontal: "横",
      vertical: "竖",
      "target-zone": "目",
      blocked: "禁",
    }[tag] || tag
  );
}

export function tagClass(tag: string): string {
  return (
    {
      free: "f",
      horizontal: "h",
      vertical: "v",
      "target-zone": "t",
      blocked: "b",
    }[tag] || "h"
  );
}

export function moveRuleLabel(rule: string): string {
  return (
    {
      free: "自由",
      horizontal: "仅横向",
      vertical: "仅竖向",
      blocked: "不可移动",
    }[rule] || rule
  );
}

export function zoneRoleLabel(role: string): string {
  return (
    {
      spawn: "出生",
      goal: "目标",
      portal: "传送",
    }[role] || role
  );
}

export function overlap(a: Piece, b: Piece): boolean {
  return !(
    a.col + a.w <= b.col ||
    b.col + b.w <= a.col ||
    a.row + a.h <= b.row ||
    b.row + b.h <= a.row
  );
}

export function inBounds(
  state: EditorState | PuzzleSnapshot,
  row: number,
  col: number,
  w: number,
  h: number,
): boolean {
  return row >= 0 && col >= 0 && row + h <= state.rows && col + w <= state.cols;
}

export function cellAllows(
  state: EditorState | PuzzleSnapshot,
  piece: Piece,
  row: number,
  col: number,
  dx: number,
  dy: number,
): boolean {
  const tags = new Set(getCell(state as EditorState, row, col)?.tags || []);
  if (tags.has("blocked")) {
    return false;
  }

  const hasFree = tags.has("free");
  if (piece.role === "target" && !hasFree && !tags.has("target-zone")) {
    return false;
  }
  if (hasFree) {
    return true;
  }
  if (piece.moveRule === "free") {
    return true;
  }

  const hasHorizontal = tags.has("horizontal");
  const hasVertical = tags.has("vertical");
  if (hasHorizontal && !hasVertical && dy !== 0) {
    return false;
  }
  if (hasVertical && !hasHorizontal && dx !== 0) {
    return false;
  }
  return true;
}

export function canPlace(
  state: EditorState | PuzzleSnapshot,
  piece: Piece,
  row: number,
  col: number,
  w = piece.w,
  h = piece.h,
  ignoreId = piece.id,
): boolean {
  const insideBoard = inBounds(state, row, col, w, h);
  if (!insideBoard && !matchesEdgeGoalPlacement(state, piece, row, col, w, h)) {
    return false;
  }

  const dx = col - piece.col;
  const dy = row - piece.row;
  if (insideBoard) {
    for (let nextRow = row; nextRow < row + h; nextRow += 1) {
      for (let nextCol = col; nextCol < col + w; nextCol += 1) {
        if (!cellAllows(state, piece, nextRow, nextCol, dx, dy)) {
          return false;
        }
      }
    }
  }

  if (piece.moveRule === "blocked" && (dx || dy)) {
    return false;
  }
  if (piece.moveRule === "horizontal" && dy) {
    return false;
  }
  if (piece.moveRule === "vertical" && dx) {
    return false;
  }

  const rect = { ...piece, row, col, w, h };
  return !state.pieces.some(
    (otherPiece) => otherPiece.id !== ignoreId && overlap(rect, otherPiece),
  );
}

export function findSpot(
  state: EditorState,
  piece: Piece,
  row: number,
  col: number,
  w = piece.w,
  h = piece.h,
): [number, number] | null {
  const maxRadius = Math.max(state.rows, state.cols);
  for (let radius = 0; radius <= maxRadius; radius += 1) {
    for (let dr = -radius; dr <= radius; dr += 1) {
      for (let dc = -radius; dc <= radius; dc += 1) {
        if (Math.max(Math.abs(dr), Math.abs(dc)) !== radius) {
          continue;
        }
        const nextRow = row + dr;
        const nextCol = col + dc;
        if (canPlace(state, piece, nextRow, nextCol, w, h)) {
          return [nextRow, nextCol];
        }
      }
    }
  }
  return null;
}

export function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}

export function recordMove(
  state: EditorState,
  fromRow: number,
  fromCol: number,
  toRow: number,
  toCol: number,
): void {
  const distance = Math.abs(toRow - fromRow) + Math.abs(toCol - fromCol);
  if (!distance) {
    return;
  }
  state.stats.operations += 1;
  state.stats.distance += distance;
}

function matchesZoneFilter(piece: Piece, zone: Zone): boolean {
  if (!zone.targetFilter) {
    return piece.role === "target";
  }
  if (zone.targetFilter.pieceIds && !zone.targetFilter.pieceIds.includes(piece.id)) {
    return false;
  }
  if (zone.targetFilter.pieceRoles && !zone.targetFilter.pieceRoles.includes(piece.role)) {
    return false;
  }
  return true;
}

function pieceInsideRectZone(piece: Piece, zone: Zone): boolean {
  const row = zone.row ?? 0;
  const col = zone.col ?? 0;
  return (
    piece.row >= row &&
    piece.col >= col &&
    piece.row + piece.h <= row + zone.h &&
    piece.col + piece.w <= col + zone.w
  );
}

function rectMatchesEdgeGoalPlacement(
  state: EditorState | PuzzleSnapshot,
  rect: Pick<Piece, "row" | "col" | "w" | "h">,
  zone: Zone,
): boolean {
  const index = zone.index ?? 0;
  if (zone.side === "left") {
    return rect.col < 0 && rect.row >= index && rect.row + rect.h <= index + zone.h;
  }
  if (zone.side === "right") {
    return (
      rect.col + rect.w > state.cols &&
      rect.row >= index &&
      rect.row + rect.h <= index + zone.h
    );
  }
  if (zone.side === "top") {
    return rect.row < 0 && rect.col >= index && rect.col + rect.w <= index + zone.w;
  }
  return (
    rect.row + rect.h > state.rows &&
    rect.col >= index &&
    rect.col + rect.w <= index + zone.w
  );
}

function pieceMatchesZone(
  state: EditorState | PuzzleSnapshot,
  piece: Piece,
  zone: Zone,
): boolean {
  if (zone.shapeKind === "rect") {
    return pieceInsideRectZone(piece, zone);
  }
  return rectMatchesEdgeGoalPlacement(state, piece, zone);
}

function matchesEdgeGoalPlacement(
  state: EditorState | PuzzleSnapshot,
  piece: Piece,
  row: number,
  col: number,
  w: number,
  h: number,
): boolean {
  if (piece.role !== "target") {
    return false;
  }
  const rect = { ...piece, row, col, w, h };
  return state.zones.some(
    (zone) =>
      zone.role === "goal" &&
      zone.shapeKind === "edge" &&
      matchesZoneFilter(piece, zone) &&
      rectMatchesEdgeGoalPlacement(state, rect, zone),
  );
}

function pieceOnTargetTaggedCells(state: EditorState | PuzzleSnapshot, piece: Piece): boolean {
  for (let row = piece.row; row < piece.row + piece.h; row += 1) {
    for (let col = piece.col; col < piece.col + piece.w; col += 1) {
      const tags = new Set(getCell(state as EditorState, row, col)?.tags || []);
      if (!tags.has("target-zone")) {
        return false;
      }
    }
  }
  return true;
}

function hasTargetCells(state: EditorState | PuzzleSnapshot): boolean {
  return state.cells.some((row) => row.some((cell) => cell.tags.includes("target-zone")));
}

export function isSolvedState(state: EditorState | PuzzleSnapshot): boolean {
  const targets = state.pieces.filter((piece) => piece.role === "target");
  if (targets.length === 0) {
    return false;
  }

  const goalZones = state.zones.filter((zone) => zone.role === "goal");
  return targets.every((piece) => {
    const matchingZones = goalZones.filter((zone) => matchesZoneFilter(piece, zone));
    if (matchingZones.length > 0) {
      return matchingZones.some((zone) => pieceMatchesZone(state, piece, zone));
    }
    if (hasTargetCells(state)) {
      return pieceOnTargetTaggedCells(state, piece);
    }
    return false;
  });
}
