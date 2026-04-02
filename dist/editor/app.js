import {
  clonePiece,
  createCells,
  createEditorState,
  makePiece,
  makeZone,
  mutateCell,
  resetStats,
  selectedPiece,
} from "../core/model.js";
import {
  canPlace,
  clamp,
  findSpot,
  moveRuleLabel,
  recordMove,
  tagClass,
  tagLabel,
  zoneRoleLabel,
} from "../core/rules.js";
import { exportPuzzle, hydrateStateFromData } from "../core/serialization.js";
import { solvePuzzle } from "../core/solver.js";

const state = createEditorState();
const $ = (id) => document.getElementById(id);
const board = $("board");
const menu = $("menu");
const menuBox = $("menuBox");
const modalMask = $("modalMask");
const modalBody = $("modalBody");
const modalTitle = $("modalTitle");

let modalHandler = null;
let isPainting = false;
let solverMessage = "尚未求解。";

function styleRect(node, rect) {
  node.style.left = `${rect.left}px`;
  node.style.top = `${rect.top}px`;
  node.style.width = `${rect.width}px`;
  node.style.height = `${rect.height}px`;
}

function zoneRect(zone) {
  const size = state.cellSize;
  if (zone.shapeKind === "rect") {
    return {
      left: (zone.col || 0) * size,
      top: (zone.row || 0) * size,
      width: zone.w * size,
      height: zone.h * size,
    };
  }
  if (zone.side === "top") {
    return { left: zone.index * size, top: -zone.h * size, width: zone.w * size, height: zone.h * size };
  }
  if (zone.side === "bottom") {
    return { left: zone.index * size, top: state.rows * size, width: zone.w * size, height: zone.h * size };
  }
  if (zone.side === "left") {
    return { left: -zone.w * size, top: zone.index * size, width: zone.w * size, height: zone.h * size };
  }
  return { left: state.cols * size, top: zone.index * size, width: zone.w * size, height: zone.h * size };
}

function invalidateSolver(message = "布局已修改，请重新求解。") {
  solverMessage = message;
}

function closeMenu() {
  menu.hidden = true;
}

function openMenu(x, y, items) {
  menu.hidden = false;
  menuBox.innerHTML = "";
  items.forEach((item) => {
    const node = document.createElement("div");
    node.className = "menu-item";
    node.textContent = item.label;
    node.onclick = () => {
      closeMenu();
      item.onClick();
    };
    menuBox.appendChild(node);
  });
  menuBox.style.left = `${Math.max(8, Math.min(x, window.innerWidth - 220))}px`;
  menuBox.style.top = `${Math.max(8, Math.min(y, window.innerHeight - 220))}px`;
}

function openPrompt(title, fields, onOk) {
  modalTitle.textContent = title;
  modalBody.innerHTML = fields
    .map(
      (field) =>
        `<div style="margin-bottom:10px;"><label>${field.label}</label><input id="modal_${field.key}" type="${field.type || "text"}" value="${field.value ?? ""}" min="${field.min ?? ""}"></div>`,
    )
    .join("");
  modalHandler = () => {
    const result = {};
    fields.forEach((field) => {
      result[field.key] = $(`modal_${field.key}`).value;
    });
    onOk(result);
  };
  modalMask.classList.add("open");
  modalBody.querySelector("input")?.focus();
}

function closeModal() {
  modalMask.classList.remove("open");
  modalHandler = null;
}

function copyPiece(piece) {
  state.clipboard = { kind: "piece", data: { ...piece } };
}

function copyZone(zone) {
  state.clipboard = { kind: "zone", data: { ...zone } };
}

function pasteClipboard() {
  if (!state.clipboard) {
    return;
  }

  if (state.clipboard.kind === "piece") {
    const copy = clonePiece(state, state.clipboard.data);
    const spot = findSpot(state, copy, copy.row + 1, copy.col + 1, copy.w, copy.h);
    if (!spot) {
      alert("附近没有可用位置可粘贴对象。");
      return;
    }
    copy.row = spot[0];
    copy.col = spot[1];
    state.pieces.push(copy);
    state.selectedPieceId = copy.id;
  } else {
    const zone = {
      ...state.clipboard.data,
      id: `zone-${state.nextZoneId++}`,
      name: `${state.clipboard.data.name} Copy`,
    };
    state.zones.push(zone);
  }

  invalidateSolver();
  render();
}

function renameItem(item) {
  openPrompt("重命名", [{ key: "name", label: "名称", value: item.name }], ({ name }) => {
    item.name = name.trim() || item.name;
    invalidateSolver();
    render();
    closeModal();
  });
}

function recolorItem(item) {
  openPrompt(
    "更换颜色",
    [{ key: "color", label: "颜色", type: "color", value: item.color }],
    ({ color }) => {
      item.color = color || item.color;
      invalidateSolver();
      render();
      closeModal();
    },
  );
}

function resizePiece(piece) {
  openPrompt(
    "更改尺寸",
    [
      { key: "w", label: "宽", type: "number", value: piece.w, min: 1 },
      { key: "h", label: "高", type: "number", value: piece.h, min: 1 },
    ],
    ({ w, h }) => {
      const nextWidth = Math.max(1, Number(w) || 1);
      const nextHeight = Math.max(1, Number(h) || 1);
      const spot = canPlace(state, piece, piece.row, piece.col, nextWidth, nextHeight)
        ? [piece.row, piece.col]
        : findSpot(state, piece, piece.row, piece.col, nextWidth, nextHeight);
      if (!spot) {
        alert("找不到可放置的新尺寸位置。");
        return;
      }
      piece.w = nextWidth;
      piece.h = nextHeight;
      piece.row = spot[0];
      piece.col = spot[1];
      invalidateSolver();
      render();
      closeModal();
    },
  );
}

function resizeZone(zone) {
  const horizontal = zone.shapeKind === "edge" && (zone.side === "top" || zone.side === "bottom");
  const fieldKey = zone.shapeKind === "rect" ? "size" : horizontal ? "w" : "h";
  const fieldLabel = zone.shapeKind === "rect" ? "边长" : horizontal ? "宽" : "高";
  const fieldValue = zone.shapeKind === "rect" ? Math.max(zone.w, zone.h) : horizontal ? zone.w : zone.h;

  openPrompt(
    "更改 Zone 尺寸",
    [{ key: fieldKey, label: fieldLabel, type: "number", value: fieldValue, min: 1 }],
    (result) => {
      const value = Math.max(1, Number(result[fieldKey]) || 1);
      if (zone.shapeKind === "rect") {
        zone.w = value;
        zone.h = value;
      } else if (horizontal) {
        zone.w = value;
      } else {
        zone.h = value;
      }
      invalidateSolver();
      render();
      closeModal();
    },
  );
}

function editZonePlacement(zone) {
  if (zone.shapeKind === "rect") {
    openPrompt(
      "编辑内部终点",
      [
        { key: "row", label: "行", type: "number", value: zone.row ?? 0, min: 0 },
        { key: "col", label: "列", type: "number", value: zone.col ?? 0, min: 0 },
        { key: "w", label: "宽", type: "number", value: zone.w, min: 1 },
        { key: "h", label: "高", type: "number", value: zone.h, min: 1 },
      ],
      (result) => {
        zone.row = Math.max(0, Number(result.row) || 0);
        zone.col = Math.max(0, Number(result.col) || 0);
        zone.w = Math.max(1, Number(result.w) || 1);
        zone.h = Math.max(1, Number(result.h) || 1);
        invalidateSolver();
        render();
        closeModal();
      },
    );
    return;
  }

  const spanKey = zone.side === "top" || zone.side === "bottom" ? "w" : "h";
  openPrompt(
    "编辑边缘终点",
    [
      { key: "side", label: "边 (top/right/bottom/left)", value: zone.side || "right" },
      { key: "index", label: "起始格", type: "number", value: zone.index ?? 0, min: 0 },
      { key: spanKey, label: spanKey === "w" ? "宽" : "高", type: "number", value: zone[spanKey], min: 1 },
    ],
    (result) => {
      const side = ["top", "right", "bottom", "left"].includes(result.side) ? result.side : "right";
      zone.side = side;
      zone.index = Math.max(0, Number(result.index) || 0);
      zone.w = side === "top" || side === "bottom" ? Math.max(1, Number(result[spanKey]) || 1) : 1;
      zone.h = side === "left" || side === "right" ? Math.max(1, Number(result[spanKey]) || 1) : 1;
      invalidateSolver();
      render();
      closeModal();
    },
  );
}

function createInnerGoalZone() {
  openPrompt(
    "新增内部终点",
    [
      { key: "name", label: "名称", value: `Goal Zone ${state.nextZoneId}` },
      { key: "row", label: "行", type: "number", value: 0, min: 0 },
      { key: "col", label: "列", type: "number", value: 0, min: 0 },
      { key: "w", label: "宽", type: "number", value: 1, min: 1 },
      { key: "h", label: "高", type: "number", value: 1, min: 1 },
    ],
    (result) => {
      const zone = makeZone(state, "rect", {
        row: Math.max(0, Number(result.row) || 0),
        col: Math.max(0, Number(result.col) || 0),
      });
      zone.name = result.name.trim() || zone.name;
      zone.role = "goal";
      zone.row = Math.max(0, Number(result.row) || 0);
      zone.col = Math.max(0, Number(result.col) || 0);
      zone.w = Math.max(1, Number(result.w) || 1);
      zone.h = Math.max(1, Number(result.h) || 1);
      state.zones.push(zone);
      invalidateSolver();
      render();
      closeModal();
    },
  );
}

function createEdgeGoalZone() {
  openPrompt(
    "新增边缘终点",
    [
      { key: "name", label: "名称", value: `Edge Goal ${state.nextZoneId}` },
      { key: "side", label: "边 (top/right/bottom/left)", value: "right" },
      { key: "index", label: "起始格", type: "number", value: 0, min: 0 },
      { key: "span", label: "长度", type: "number", value: 1, min: 1 },
    ],
    (result) => {
      const side = ["top", "right", "bottom", "left"].includes(result.side) ? result.side : "right";
      const zone = makeZone(state, "edge", {
        side,
        index: Math.max(0, Number(result.index) || 0),
      });
      zone.name = result.name.trim() || zone.name;
      zone.role = "goal";
      zone.side = side;
      zone.index = Math.max(0, Number(result.index) || 0);
      zone.w = side === "top" || side === "bottom" ? Math.max(1, Number(result.span) || 1) : 1;
      zone.h = side === "left" || side === "right" ? Math.max(1, Number(result.span) || 1) : 1;
      state.zones.push(zone);
      invalidateSolver();
      render();
      closeModal();
    },
  );
}

function cycleZoneRole(zone) {
  const order = ["spawn", "goal", "portal"];
  zone.role = order[(order.indexOf(zone.role) + 1) % order.length];
  invalidateSolver();
  render();
}

function deletePiece(id) {
  state.pieces = state.pieces.filter((piece) => piece.id !== id);
  if (state.selectedPieceId === id) {
    state.selectedPieceId = state.pieces[0]?.id || null;
  }
  invalidateSolver();
  render();
}

function deleteZone(id) {
  state.zones = state.zones.filter((zone) => zone.id !== id);
  invalidateSolver();
  render();
}

function pieceMenu(piece, x, y) {
  openMenu(x, y, [
    { label: "复制", onClick: () => copyPiece(piece) },
    { label: "重命名", onClick: () => renameItem(piece) },
    { label: "更改尺寸", onClick: () => resizePiece(piece) },
    { label: "更换颜色", onClick: () => recolorItem(piece) },
    { label: `对象类型: ${piece.role === "target" ? "目标物" : "普通障碍物"}`, onClick: () => {
      piece.role = piece.role === "target" ? "normal" : "target";
      invalidateSolver();
      render();
    } },
    { label: `移动规则: ${moveRuleLabel(piece.moveRule)}`, onClick: () => {
      const order = ["free", "horizontal", "vertical", "blocked"];
      piece.moveRule = order[(order.indexOf(piece.moveRule) + 1) % order.length];
      invalidateSolver();
      render();
    } },
    { label: "删除", onClick: () => deletePiece(piece.id) },
  ]);
}

function zoneMenu(zone, x, y) {
  openMenu(x, y, [
    { label: "复制", onClick: () => copyZone(zone) },
    { label: "重命名", onClick: () => renameItem(zone) },
    { label: "编辑位置", onClick: () => editZonePlacement(zone) },
    { label: "更改尺寸", onClick: () => resizeZone(zone) },
    { label: "更换颜色", onClick: () => recolorItem(zone) },
    { label: `Zone 角色: ${zoneRoleLabel(zone.role)}`, onClick: () => cycleZoneRole(zone) },
    { label: "删除", onClick: () => deleteZone(zone.id) },
  ]);
}

function startDrag(piece, event) {
  if (event.button !== 0) {
    return;
  }
  state.selectedPieceId = piece.id;
  state.mainMode = "objects";
  const rect = board.getBoundingClientRect();
  state.dragging = {
    id: piece.id,
    offsetX: event.clientX - (rect.left + piece.col * state.cellSize),
    offsetY: event.clientY - (rect.top + piece.row * state.cellSize),
    startRow: piece.row,
    startCol: piece.col,
  };
  render();
}

function handleDrag(event) {
  if (!state.dragging) {
    return;
  }

  const piece = selectedPiece(state);
  if (!piece) {
    return;
  }

  const rect = board.getBoundingClientRect();
  const minCol = piece.role === "target" ? -piece.w : 0;
  const maxCol = piece.role === "target" ? state.cols : state.cols - piece.w;
  const minRow = piece.role === "target" ? -piece.h : 0;
  const maxRow = piece.role === "target" ? state.rows : state.rows - piece.h;
  const col = clamp(
    Math.round((event.clientX - rect.left - state.dragging.offsetX) / state.cellSize),
    minCol,
    maxCol,
  );
  const row = clamp(
    Math.round((event.clientY - rect.top - state.dragging.offsetY) / state.cellSize),
    minRow,
    maxRow,
  );
  if (canPlace(state, piece, row, col, piece.w, piece.h)) {
    piece.row = row;
    piece.col = col;
    render();
  }
}

function stopDrag() {
  if (!state.dragging) {
    return;
  }

  const piece = selectedPiece(state);
  if (piece && piece.id === state.dragging.id) {
    recordMove(state, state.dragging.startRow, state.dragging.startCol, piece.row, piece.col);
    invalidateSolver();
  }
  state.dragging = null;
  render();
}

function syncPieceForm() {
  const piece = selectedPiece(state);
  const disabled = !piece;
  [
    "pieceNameInput",
    "pieceRoleInput",
    "pieceWInput",
    "pieceHInput",
    "pieceRowInput",
    "pieceColInput",
    "pieceMoveRuleInput",
    "pieceColorInput",
    "pieceAffectedByWindInput",
    "pieceBlocksWindInput",
    "applyPieceBtn",
    "duplicatePieceBtn",
    "deletePieceBtn",
  ].forEach((id) => {
    $(id).disabled = disabled;
  });

  if (!piece) {
    return;
  }

  $("pieceNameInput").value = piece.name;
  $("pieceRoleInput").value = piece.role;
  $("pieceWInput").value = piece.w;
  $("pieceHInput").value = piece.h;
  $("pieceRowInput").value = piece.row;
  $("pieceColInput").value = piece.col;
  $("pieceMoveRuleInput").value = piece.moveRule;
  $("pieceColorInput").value = piece.color;
  $("pieceAffectedByWindInput").checked = Boolean(piece.affectedByWind);
  $("pieceBlocksWindInput").checked = piece.blocksWind !== false;
}

function applyPieceForm(piece) {
  const fromRow = piece.row;
  const fromCol = piece.col;
  const nextPiece = {
    ...piece,
    name: $("pieceNameInput").value.trim() || piece.name,
    role: $("pieceRoleInput").value,
    row: Number($("pieceRowInput").value) || 0,
    col: Number($("pieceColInput").value) || 0,
    w: Math.max(1, Number($("pieceWInput").value) || 1),
    h: Math.max(1, Number($("pieceHInput").value) || 1),
    moveRule: $("pieceMoveRuleInput").value,
    color: $("pieceColorInput").value || piece.color,
    affectedByWind: $("pieceAffectedByWindInput").checked,
    blocksWind: $("pieceBlocksWindInput").checked,
  };
  const spot = canPlace(state, nextPiece, nextPiece.row, nextPiece.col, nextPiece.w, nextPiece.h)
    ? [nextPiece.row, nextPiece.col]
    : findSpot(state, nextPiece, nextPiece.row, nextPiece.col, nextPiece.w, nextPiece.h);

  if (!spot) {
    alert("当前设置无法放置到棋盘中。");
    return;
  }

  Object.assign(piece, nextPiece, { row: spot[0], col: spot[1] });
  recordMove(state, fromRow, fromCol, piece.row, piece.col);
  invalidateSolver();
  render();
}

function updatePieceList() {
  const wrap = $("pieceList");
  wrap.innerHTML = "";
  state.pieces.forEach((piece) => {
    const row = document.createElement("div");
    row.className = `item${piece.id === state.selectedPieceId ? " active" : ""}`;
    row.innerHTML = `<div>${piece.name}<div class="hint">${piece.role === "target" ? "目标物" : "障碍物"} · ${piece.w}×${piece.h}</div></div><div>${piece.row},${piece.col}</div>`;
    row.onclick = () => {
      state.selectedPieceId = piece.id;
      render();
    };
    wrap.appendChild(row);
  });
}

function addEdgeSlot(side, index, rect) {
  const slot = document.createElement("div");
  slot.className = "edge-slot";
  styleRect(slot, rect);
  slot.oncontextmenu = (event) => {
    event.preventDefault();
    const zone = makeZone(state, "edge", { side, index });
    zone.name = `${zoneRoleLabel(zone.role)} Zone ${state.nextZoneId - 1}`;
    state.zones.push(zone);
    invalidateSolver();
    render();
    zoneMenu(zone, event.clientX, event.clientY);
  };
  board.appendChild(slot);
}

function renderEdgeSlots() {
  const size = state.cellSize;
  for (let col = 0; col < state.cols; col += 1) {
    addEdgeSlot("top", col, { left: col * size, top: -size, width: size, height: size });
    addEdgeSlot("bottom", col, {
      left: col * size,
      top: state.rows * size,
      width: size,
      height: size,
    });
  }
  for (let row = 0; row < state.rows; row += 1) {
    addEdgeSlot("left", row, { left: -size, top: row * size, width: size, height: size });
    addEdgeSlot("right", row, {
      left: state.cols * size,
      top: row * size,
      width: size,
      height: size,
    });
  }
}

function renderZones() {
  state.zones.forEach((zone) => {
    const node = document.createElement("div");
    node.className = "edge-region";
    node.style.background = zone.color;
    node.style.borderStyle = zone.role === "goal" ? "solid" : zone.role === "portal" ? "dashed" : "dotted";
    node.textContent = `${zoneRoleLabel(zone.role)} ${zone.name}`;
    styleRect(node, zoneRect(zone));
    node.oncontextmenu = (event) => {
      event.preventDefault();
      zoneMenu(zone, event.clientX, event.clientY);
    };
    board.appendChild(node);
  });
}

function renderPieces() {
  const size = state.cellSize;
  state.pieces.forEach((piece) => {
    const node = document.createElement("div");
    node.className = `piece${piece.id === state.selectedPieceId ? " selected" : ""}`;
    node.style.background = piece.color;
    node.innerHTML = `<div>${piece.name}<small>${piece.role === "target" ? "目标物" : moveRuleLabel(piece.moveRule)}</small></div>`;
    styleRect(node, {
      left: piece.col * size,
      top: piece.row * size,
      width: piece.w * size,
      height: piece.h * size,
    });
    node.onmousedown = (event) => startDrag(piece, event);
    node.onclick = () => {
      state.selectedPieceId = piece.id;
      state.mainMode = "objects";
      $("mainModeSelect").value = "objects";
      render();
    };
    node.oncontextmenu = (event) => {
      event.preventDefault();
      state.selectedPieceId = piece.id;
      render();
      pieceMenu(piece, event.clientX, event.clientY);
    };
    board.appendChild(node);
  });
}

function renderBoard() {
  board.style.width = `${state.cols * state.cellSize}px`;
  board.style.height = `${state.rows * state.cellSize}px`;
  board.style.margin = `${state.cellSize}px`;
  board.innerHTML = "";

  for (let row = 0; row < state.rows; row += 1) {
    for (let col = 0; col < state.cols; col += 1) {
      const cell = state.cells[row]?.[col];
      const node = document.createElement("div");
      node.className = `cell${(cell?.tags || []).includes("blocked") ? " blocked" : ""}`;
      styleRect(node, {
        left: col * state.cellSize,
        top: row * state.cellSize,
        width: state.cellSize,
        height: state.cellSize,
      });
      node.onmousedown = (event) => {
        if (event.button !== 0 || state.mainMode !== "cells") {
          return;
        }
        isPainting = true;
        mutateCell(state, row, col);
        invalidateSolver();
        render();
      };
      node.onmouseenter = () => {
        if (isPainting && state.mainMode === "cells") {
          mutateCell(state, row, col);
          invalidateSolver();
          render();
        }
      };

      const tagsNode = document.createElement("div");
      tagsNode.className = "cell-tags";
      (cell?.tags || []).forEach((tag) => {
        const badge = document.createElement("span");
        badge.className = `mini ${tagClass(tag)}`;
        badge.textContent = tagLabel(tag);
        tagsNode.appendChild(badge);
      });
      node.appendChild(tagsNode);

      if (state.showCoords) {
        const coord = document.createElement("div");
        coord.className = "coord";
        coord.textContent = `${row},${col}`;
        node.appendChild(coord);
      }

      board.appendChild(node);
    }
  }

  renderEdgeSlots();
  renderZones();
  renderPieces();
}

function formatSolverResult(result) {
  if (!result.solvable) {
    return `模式: ${result.mode}\n结果: 当前未找到可解路径。\n搜索节点: ${result.explored}${result.truncated ? "\n提示: 搜索被节点上限截断。" : ""}`;
  }

  const steps = result.steps.length
    ? result.steps
        .map(
          (step, index) =>
            `${index + 1}. ${step.pieceName} (${step.pieceId}) ${step.direction} -> (${step.toRow}, ${step.toCol})`,
        )
        .join("\n")
    : "0 步，当前布局已满足目标。";

  return `模式: ${result.mode}\n结果: 可解\n最优步数: ${result.steps.length}\n搜索节点: ${result.explored}\n\n${steps}`;
}

function runSolver() {
  const result = solvePuzzle(state);
  solverMessage = formatSolverResult(result);
  render();
}

function render() {
  renderBoard();
  updatePieceList();
  syncPieceForm();
  $("toggleCoordsBtn").textContent = `坐标显示: ${state.showCoords ? "开" : "关"}`;
  $("mainModeSelect").value = state.mainMode;
  $("tagSelect").value = state.selectedTag;
  $("opCount").textContent = String(state.stats.operations);
  $("distCount").textContent = String(state.stats.distance);
  $("windActiveInput").checked = Boolean(state.runtime.wind?.active);
  $("windDirectionInput").value = state.runtime.wind?.direction || "east";
  $("solveOutput").value = solverMessage;
}

function bindEvents() {
  $("applyBoardBtn").onclick = () => {
    state.rows = Math.max(2, Number($("rowsInput").value) || 6);
    state.cols = Math.max(2, Number($("colsInput").value) || 6);
    state.cellSize = Math.max(36, Number($("cellSizeInput").value) || 64);
    state.cells = createCells(state.rows, state.cols);
    state.pieces = state.pieces.filter((piece) =>
      canPlace(state, piece, piece.row, piece.col, piece.w, piece.h, piece.id),
    );
    state.zones = state.zones.filter((zone) => {
      if (zone.shapeKind === "rect") {
        return zone.row + zone.h <= state.rows && zone.col + zone.w <= state.cols;
      }
      if (zone.side === "top" || zone.side === "bottom") {
        return zone.index + zone.w <= state.cols;
      }
      return zone.index + zone.h <= state.rows;
    });
    invalidateSolver();
    render();
  };

  $("toggleCoordsBtn").onclick = () => {
    state.showCoords = !state.showCoords;
    render();
  };
  $("resetStatsBtn").onclick = () => {
    resetStats(state);
    render();
  };
  $("mainModeSelect").onchange = (event) => {
    state.mainMode = event.target.value;
    render();
  };
  $("tagSelect").onchange = (event) => {
    state.selectedTag = event.target.value;
  };

  $("paintAddBtn").onclick = () => {
    state.paintMode = "add";
  };
  $("paintRemoveBtn").onclick = () => {
    state.paintMode = "remove";
  };
  $("paintClearBtn").onclick = () => {
    state.paintMode = "clear";
  };

  $("addPieceBtn").onclick = () => {
    const piece = makePiece(state, "normal");
    state.pieces.push(piece);
    state.selectedPieceId = piece.id;
    invalidateSolver();
    render();
  };
  $("addTargetBtn").onclick = () => {
    const piece = makePiece(state, "target");
    state.pieces.push(piece);
    state.selectedPieceId = piece.id;
    invalidateSolver();
    render();
  };
  $("addInnerGoalBtn").onclick = createInnerGoalZone;
  $("addEdgeGoalBtn").onclick = createEdgeGoalZone;

  $("applyPieceBtn").onclick = () => {
    const piece = selectedPiece(state);
    if (piece) {
      applyPieceForm(piece);
    }
  };
  $("duplicatePieceBtn").onclick = () => {
    const piece = selectedPiece(state);
    if (piece) {
      copyPiece(piece);
      pasteClipboard();
    }
  };
  $("deletePieceBtn").onclick = () => {
    const piece = selectedPiece(state);
    if (piece) {
      deletePiece(piece.id);
    }
  };

  $("windActiveInput").onchange = (event) => {
    if (event.target.checked) {
      state.runtime.wind = {
        direction: $("windDirectionInput").value,
        active: true,
      };
    } else {
      state.runtime.wind = null;
    }
    invalidateSolver();
    render();
  };
  $("windDirectionInput").onchange = (event) => {
    if (!state.runtime.wind) {
      state.runtime.wind = { direction: event.target.value, active: false };
    } else {
      state.runtime.wind.direction = event.target.value;
    }
    invalidateSolver();
    render();
  };

  $("solveBtn").onclick = runSolver;

  $("exportBtn").onclick = () => {
    $("jsonBox").value = exportPuzzle(state);
  };
  $("importBtn").onclick = () => {
    const data = JSON.parse($("jsonBox").value);
    hydrateStateFromData(state, data);
    $("rowsInput").value = state.rows;
    $("colsInput").value = state.cols;
    $("cellSizeInput").value = state.cellSize;
    solverMessage = "已导入布局，请重新求解。";
    render();
  };

  $("modalCancelBtn").onclick = closeModal;
  $("modalOkBtn").onclick = () => modalHandler && modalHandler();
  modalMask.onclick = (event) => {
    if (event.target === modalMask) {
      closeModal();
    }
  };
  menu.onclick = closeMenu;

  document.addEventListener("mouseup", () => {
    isPainting = false;
  });
  document.addEventListener("mousemove", handleDrag);
  document.addEventListener("mouseup", stopDrag);
  document.addEventListener("keydown", (event) => {
    const inForm = ["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement?.tagName);
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "c" && !inForm) {
      const piece = selectedPiece(state);
      if (piece) {
        copyPiece(piece);
      }
      event.preventDefault();
    }
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "v" && !inForm) {
      pasteClipboard();
      event.preventDefault();
    }
    if (event.key === "Delete" && !inForm) {
      const piece = selectedPiece(state);
      if (piece) {
        deletePiece(piece.id);
      }
    }
    if (event.key === "Escape") {
      closeMenu();
      closeModal();
    }
    if (event.key === "Enter" && modalMask.classList.contains("open") && modalHandler) {
      modalHandler();
    }
  });
}

function init() {
  const starter = makePiece(state, "normal");
  starter.name = "Block 1";
  starter.w = 2;
  starter.color = "#ca6b4f";
  starter.affectedByWind = false;
  state.pieces.push(starter);
  state.selectedPieceId = starter.id;
  bindEvents();
  render();

  window.puzzleEditor = {
    state,
    exportPuzzle: () => exportPuzzle(state),
    solve: (options) => solvePuzzle(state, options),
  };
}

init();
