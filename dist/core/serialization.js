import {
  createRuntimeState,
  createCells,
  normalizePiece,
  normalizeZone,
  resetStats,
  setCellTags,
} from "./model.js";

export function snapshotState(state) {
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

export function exportPuzzle(state) {
  return JSON.stringify(snapshotState(state), null, 2);
}

export function hydrateStateFromData(state, data) {
  const board = data.board || {};
  state.rows = Number(data.rows ?? data.gridRows ?? board.rows) || state.rows;
  state.cols = Number(data.cols ?? data.gridCols ?? board.cols) || state.cols;
  state.cellSize = Number(data.cellSize ?? data.tileSize ?? board.cellSize) || state.cellSize;

  state.cells = createCells(state.rows, state.cols);
  const sourceCells = data.cells || data.grid || board.cells || [];
  (sourceCells || []).forEach((row, rowIndex) => {
    (row || []).forEach((cell, colIndex) => {
      if (typeof cell === "string") {
        if (cell === "row") {
          setCellTags(state, rowIndex, colIndex, ["horizontal"]);
        } else if (cell === "col") {
          setCellTags(state, rowIndex, colIndex, ["vertical"]);
        } else if (cell === "blocked") {
          setCellTags(state, rowIndex, colIndex, ["blocked"]);
        }
        return;
      }

      const tags = cell?.tags || cell?.modes || cell?.rules || [];
      if (Array.isArray(tags) && tags.length) {
        setCellTags(
          state,
          rowIndex,
          colIndex,
          tags.map((tag) => (tag === "row" ? "horizontal" : tag === "col" ? "vertical" : tag)),
        );
      } else if (cell?.rule || cell?.mode) {
        const singleRule = cell.rule || cell.mode;
        if (singleRule === "row") {
          setCellTags(state, rowIndex, colIndex, ["horizontal"]);
        } else if (singleRule === "col") {
          setCellTags(state, rowIndex, colIndex, ["vertical"]);
        } else if (singleRule === "blocked") {
          setCellTags(state, rowIndex, colIndex, ["blocked"]);
        }
      }
    });
  });

  const sourcePieces = data.pieces || data.obstacles || data.blocks || [];
  const sourceZones = data.zones || data.edgeRegions || data.regions || data.edgeAreas || [];

  state.pieces = sourcePieces.map((piece, index) => normalizePiece(state, piece, index));
  state.zones = sourceZones.map((zone, index) => normalizeZone(state, zone, index));
  state.runtime = createRuntimeState(data.runtime || null);

  state.nextPieceId =
    state.pieces.reduce(
      (maxId, item) => Math.max(maxId, Number(String(item.id).split("-").pop()) || 0),
      0,
    ) + 1;
  state.nextZoneId =
    state.zones.reduce(
      (maxId, item) => Math.max(maxId, Number(String(item.id).split("-").pop()) || 0),
      0,
    ) + 1;
  state.selectedPieceId = state.pieces[0]?.id || null;
  resetStats(state);
  return state;
}
