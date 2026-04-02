(function () {
  const root = window.PuzzleV1;

  function createCells(rows, cols) {
    return Array.from({ length: rows }, function () {
      return Array.from({ length: cols }, function () {
        return { tags: [] };
      });
    });
  }

  function clone(data) {
    return JSON.parse(JSON.stringify(data));
  }

  function createPieceFromType(rulePack, typeId, nextIndex) {
    const template = rulePack.pieceTypes.find(function (item) {
      return item.id === typeId;
    });
    if (!template) return null;

    return {
      id: "piece-" + nextIndex,
      name: template.label + " " + nextIndex,
      typeId: template.id,
      role: template.role,
      row: 0,
      col: 0,
      w: template.defaultSize.w,
      h: template.defaultSize.h,
      moveRule: template.moveRule,
      movable: template.movable,
      color: template.defaultColor,
      metadata: {},
    };
  }

  function createZoneFromTemplate(rulePack, zoneId, nextIndex, shapeKind) {
    const template = rulePack.zones.find(function (item) {
      return item.id === zoneId;
    });
    if (!template) return null;
    const resolvedShapeKind = shapeKind || template.allowedShapes[0];
    const defaultGoalMode =
      template.role === "goal" && resolvedShapeKind === "edge"
        ? "partial"
        : (template.goalMode || "full");

    return {
      id: "zone-" + nextIndex,
      templateId: template.id,
      name: template.label + " " + nextIndex,
      role: template.role,
      shapeKind: resolvedShapeKind,
      row: 0,
      col: 0,
      side: "right",
      index: 0,
      w: 1,
      h: 1,
      color: template.style.color,
      goalMode: defaultGoalMode,
      targetFilter: clone(template.targetFilter || null),
    };
  }

  root.createDesignState = function createDesignState(rulePack) {
    return {
      meta: {
        title: "未命名谜题",
        rulePackId: rulePack.id,
      },
      board: {
        rows: rulePack.board.rows.default,
        cols: rulePack.board.cols.default,
        cellSize: rulePack.board.cellSize.default,
        cells: createCells(rulePack.board.rows.default, rulePack.board.cols.default),
      },
      pieces: [],
      zones: [],
      ui: {
        selectedTagId: rulePack.editor.defaults.selectedCellTag,
        selectedPieceId: null,
        selectedZoneId: null,
        paintMode: "add",
        boardMode: "interact",
        dragMode: "grid",
        clipboard: null,
        message: "规则包已加载，可以开始设计静态谜题。",
        solveOutput: "求解器接口已预留，当前 v1 先不内置算法实现。",
        solutionPlayback: {
          result: null,
          snapshots: [],
          currentIndex: 0,
          playing: false,
          timerId: null,
          sourceKey: null,
        },
      },
      counters: {
        nextPieceId: 1,
        nextZoneId: 1,
      },
    };
  };

  root.createCells = createCells;
  root.cloneData = clone;
  root.createPieceFromType = createPieceFromType;
  root.createZoneFromTemplate = createZoneFromTemplate;
})();
