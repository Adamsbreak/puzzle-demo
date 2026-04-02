(function () {
  const root = (window.PuzzleV1 = window.PuzzleV1 || {});

  root.registry = {
    rulePacks: {},
    activeRulePackId: null,
    solverAdapter: null,
    aiAdapter: null,
    ruleInterfaces: {
      movePolicies: {},
      goalPolicies: {},
      validators: {},
      custom: {},
    },
  };

  root.registerRulePack = function registerRulePack(rulePack) {
    root.registry.rulePacks[rulePack.id] = rulePack;
    if (!root.registry.activeRulePackId) {
      root.registry.activeRulePackId = rulePack.id;
    }
  };

  root.getActiveRulePack = function getActiveRulePack() {
    return root.registry.rulePacks[root.registry.activeRulePackId] || null;
  };

  root.setActiveRulePack = function setActiveRulePack(rulePackId) {
    if (root.registry.rulePacks[rulePackId]) {
      root.registry.activeRulePackId = rulePackId;
    }
  };

  root.setSolverAdapter = function setSolverAdapter(adapter) {
    root.registry.solverAdapter = adapter;
  };

  root.getSolverAdapter = function getSolverAdapter() {
    return root.registry.solverAdapter;
  };

  root.setAIAdapter = function setAIAdapter(adapter) {
    root.registry.aiAdapter = adapter;
  };

  root.getAIAdapter = function getAIAdapter() {
    return root.registry.aiAdapter;
  };

  root.registerRuleInterface = function registerRuleInterface(group, id, implementation) {
    if (!root.registry.ruleInterfaces[group]) {
      root.registry.ruleInterfaces[group] = {};
    }
    root.registry.ruleInterfaces[group][id] = implementation;
  };

  root.getRuleInterface = function getRuleInterface(group, id) {
    if (!group || !id) return null;
    const bucket = root.registry.ruleInterfaces[group];
    return bucket ? bucket[id] || null : null;
  };

  root.listRuleInterfaces = function listRuleInterfaces(group) {
    const bucket = root.registry.ruleInterfaces[group];
    return bucket ? Object.keys(bucket) : [];
  };

  root.getSolverBehavior = function getSolverBehavior(rulePack) {
    const solver = (rulePack && rulePack.solver) || {};
    const behavior = solver.behavior || {};
    const interfaces = solver.interfaces || {};
    return {
      targetLanePriority: behavior.targetLanePriority || "absolute",
      edgeGoalRelaxation: behavior.edgeGoalRelaxation || "final-step-only",
      stopGeneration: behavior.stopGeneration || "all-legal-stops",
      interfaces: {
        movePolicy: interfaces.movePolicy || "static-v1",
        goalPolicy: interfaces.goalPolicy || "static-v1",
        validator: interfaces.validator || "static-v1",
      },
      extensionConfig: solver.extensionConfig || {},
    };
  };

  root.registerRuleInterface("movePolicies", "static-v1", {
    id: "static-v1",
    description: "Static movement policy for v1 puzzles.",
  });
  root.registerRuleInterface("goalPolicies", "static-v1", {
    id: "static-v1",
    description: "Static goal evaluation policy for v1 puzzles.",
  });
  root.registerRuleInterface("validators", "static-v1", {
    id: "static-v1",
    description: "Static structural validation policy for v1 puzzles.",
  });
})();
