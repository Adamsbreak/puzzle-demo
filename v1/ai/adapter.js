(function () {
  const root = window.PuzzleV1;

  root.setAIAdapter({
    id: "future-ai-adapter",
    description: "未来接入 AI agent 的预留层。当前只暴露安全接口，不直接修改基础层代码。",
    capabilities: [
      "propose-rulepack",
      "propose-ui-extension",
      "image-to-puzzle-spec",
    ],
    proposeRulePack: function proposeRulePack() {
      return {
        status: "not-implemented",
        message: "AI 层已经预留。未来只允许通过接口生成规则包草稿或扩展草稿，不直接改底层。",
      };
    },
  });
})();
