import { getCell } from "./model.js";

export function tagLabel(tag) {
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

export function tagClass(tag) {
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

export function moveRuleLabel(rule) {
  return (
    {
      free: "自由",
      horizontal: "仅横向",
      vertical: "仅竖向",
      blocked: "不可移动",
    }[rule] || rule
  );
}

export function zoneRoleLabel(role) {
  return (
    {
      spawn: "出生",
      goal: "目标",
      portal: "传送",
    }[role] || role
  );
}

export function overlap(a, b) {
  return !(
    a.col + a.w <= b.col ||
    b.col + b.w <= a.col ||
    a.row + a.h <= b.row ||
    b.row + b.h <= a.row
  );
}

export function inBounds(state, row, col, w, h) {
  return row >= 0 && col >= 0 && row + h <= state.rows && col + w <= state.cols;
}

export function cellAllows(state, piece, row, col, dx, dy) {
  const tags = new Set(getCell(state, row, col)?.tags || []);
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
  state,
  piece,
  row,
  col,
  w = piece.w,
  h = piece.h,
  ignoreId = piece.id,
) {
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

export function findSpot(state, piece, row, col, w = piece.w, h = piece.h) {
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

export function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

export function recordMove(state, fromRow, fromCol, toRow, toCol) {
  const distance = Math.abs(toRow - fromRow) + Math.abs(toCol - fromCol);
  if (!distance) {
    return;
  }
  state.stats.operations += 1;
  state.stats.distance += distance;
}

function matchesZoneFilter(piece, zone) {
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

function pieceInsideRectZone(piece, zone) {
  const row = zone.row ?? 0;
  const col = zone.col ?? 0;
  return (
    piece.row >= row &&
    piece.col >= col &&
    piece.row + piece.h <= row + zone.h &&
    piece.col + piece.w <= col + zone.w
  );
}

function rectMatchesEdgeGoalPlacement(state, rect, zone) {
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

function pieceMatchesZone(state, piece, zone) {
  if (zone.shapeKind === "rect") {
    return pieceInsideRectZone(piece, zone);
  }
  return rectMatchesEdgeGoalPlacement(state, piece, zone);
}

function matchesEdgeGoalPlacement(state, piece, row, col, w, h) {
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

function pieceOnTargetTaggedCells(state, piece) {
  for (let row = piece.row; row < piece.row + piece.h; row += 1) {
    for (let col = piece.col; col < piece.col + piece.w; col += 1) {
      const tags = new Set(getCell(state, row, col)?.tags || []);
      if (!tags.has("target-zone")) {
        return false;
      }
    }
  }
  return true;
}

function hasTargetCells(state) {
  return state.cells.some((row) => row.some((cell) => cell.tags.includes("target-zone")));
}

export function isSolvedState(state) {
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
