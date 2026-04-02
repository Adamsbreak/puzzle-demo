(function () {
  const root = window.PuzzleV1;

  root.registerRulePack({
    id: "basic-static",
    name: "基础静态谜题",
    version: "1.0.0",
    board: {
      rows: { min: 2, max: 20, default: 6 },
      cols: { min: 2, max: 20, default: 6 },
      cellSize: { min: 36, max: 96, default: 64 },
    },
    cellTags: [
      { id: "free", label: "自由移动", color: "#5f6ee5" },
      { id: "horizontal", label: "横向限制", color: "#3f7dd1" },
      { id: "vertical", label: "纵向限制", color: "#31926d" },
      { id: "block-lane", label: "障碍物轨道", color: "#8c6dcb" },
      { id: "target-lane", label: "目标轨道", color: "#c48f18" },
      { id: "blocked", label: "禁止进入", color: "#666666" },
    ],
    pieceTypes: [
      {
        id: "target",
        label: "目标物",
        role: "target",
        defaultSize: { w: 1, h: 1 },
        defaultColor: "#bc8d16",
        movable: true,
        moveRule: "free",
      },
      {
        id: "block",
        label: "障碍物",
        role: "block",
        defaultSize: { w: 1, h: 1 },
        defaultColor: "#d26a4c",
        movable: true,
        moveRule: "free",
      },
      {
        id: "fixed",
        label: "固定块",
        role: "fixed",
        defaultSize: { w: 1, h: 1 },
        defaultColor: "#5a5148",
        movable: false,
        moveRule: "blocked",
      },
    ],
    zones: [
      {
        id: "spawn",
        label: "出生区",
        role: "spawn",
        allowedShapes: ["rect", "edge"],
        style: { color: "#6b9f5a", borderStyle: "dotted" },
      },
      {
        id: "goal",
        label: "终点区",
        role: "goal",
        allowedShapes: ["rect", "edge"],
        goalMode: "full",
        targetFilter: { roles: ["target"] },
        style: { color: "#3f7dd1", borderStyle: "solid" },
      },
    ],
    goals: [{ type: "all-targets-reach-goals" }],
    editor: {
      defaults: {
        selectedCellTag: "free",
        selectedPieceTypeId: "block",
      },
      tools: {
        cellPainter: true,
        pieceEditor: true,
        zoneEditor: true,
        importExport: true,
      },
      showSolverButton: true,
      showSolutionSteps: false,
    },
    solver: {
      enabled: true,
      objective: "min-operations",
      maxNodes: 50000,
      behavior: {
        targetLanePriority: "absolute",
        edgeGoalRelaxation: "final-step-only",
        stopGeneration: "all-legal-stops",
      },
      interfaces: {
        movePolicy: "static-v1",
        goalPolicy: "static-v1",
        validator: "static-v1",
      },
      extensionConfig: {},
    },
  });
})();
