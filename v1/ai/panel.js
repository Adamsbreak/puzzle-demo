(function () {
  const root = window.PuzzleV1;
  const USER_ID = "local-user";
  const SESSION_STORAGE_KEY = "puzzle.v1.ai.activeSessionId";
  const DEFAULT_SUGGESTIONS = [
    "Analyze this level",
    "Why is this level unsolved?",
    "Make this level harder",
    "What is the key mechanic here?",
  ];
  const STAGE_ORDER = ["start", "intent_compiler", "validate", "solve", "score", "compose"];
  const MODIFY_POLL_MS = 1200;
  const state = {
    userId: USER_ID,
    activeSessionId: null,
    sessions: [],
    isBusy: false,
    streamAbortController: null,
    pendingLevel: null,
    messages: [],
    modifyJob: null,
    modifyJobPollTimer: null,
    modifyJobAnnouncedId: null,
    suggestions: DEFAULT_SUGGESTIONS.slice(),
  };

  function el(id) {
    return document.getElementById(id);
  }

  function getAdapter() {
    return root.getAIAdapter && root.getAIAdapter();
  }

  function activateLegacySession() {
    state.activeSessionId = "v1-editor-session";
    persistActiveSessionId(state.activeSessionId);
    if (!state.messages.length) {
      state.messages = [];
    }
    renderSessionList();
    renderMessages();
    renderSuggestions(state.suggestions);
  }

  function sanitizeSuggestions(items) {
    const output = [];
    (items || []).forEach(function (item) {
      const value = String(item || "").trim();
      if (!value || output.indexOf(value) >= 0) return;
      output.push(value);
    });
    return output.slice(0, 4);
  }

  function readStoredSessionId() {
    try {
      return window.localStorage.getItem(SESSION_STORAGE_KEY) || "";
    } catch (_error) {
      return "";
    }
  }

  function persistActiveSessionId(sessionId) {
    try {
      if (!sessionId) {
        window.localStorage.removeItem(SESSION_STORAGE_KEY);
        return;
      }
      window.localStorage.setItem(SESSION_STORAGE_KEY, sessionId);
    } catch (_error) {
      // Ignore storage issues.
    }
  }

  function formatTimestamp(value) {
    if (!value) return "";
    try {
      return new Date(Number(value) * 1000).toLocaleString();
    } catch (_error) {
      return "";
    }
  }

  function setBusy(isBusy) {
    state.isBusy = Boolean(isBusy);
    if (el("aiAnalyzeBtn")) el("aiAnalyzeBtn").disabled = isBusy;
    if (el("aiRefineBtn")) el("aiRefineBtn").disabled = isBusy;
    if (el("aiSendBtn")) el("aiSendBtn").disabled = isBusy;
    if (el("aiNewSessionBtn")) el("aiNewSessionBtn").disabled = false;
    if (el("aiStopBtn")) el("aiStopBtn").disabled = !state.streamAbortController;
    if (el("aiApplyLevelBtn")) el("aiApplyLevelBtn").disabled = isBusy || !state.pendingLevel;
    document.querySelectorAll("#aiSuggestionChips .ai-chip").forEach(function (chip) {
      chip.disabled = isBusy;
    });
    document.querySelectorAll("#aiSessionList .ai-session-btn").forEach(function (button) {
      button.disabled = false;
    });
  }

  function setResultText(text) {
    if (el("aiResultText")) {
      el("aiResultText").textContent = text || "Waiting for AI response.";
    }
  }

  function renderMetrics(analysis, warnings) {
    const wrap = el("aiMetrics");
    if (!wrap) return;
    wrap.innerHTML = "";
    const solve = (analysis && analysis.solve) || {};
    const score = (analysis && analysis.score) || {};
    [
      ["solvable", solve.solvable == null ? "-" : String(solve.solvable)],
      ["min_steps", solve.min_steps == null ? "-" : String(solve.min_steps)],
      ["difficulty", score.difficulty || "-"],
      ["warnings", warnings && warnings.length ? String(warnings.length) : "0"],
    ].forEach(function (item) {
      const chip = document.createElement("div");
      chip.className = "metric-chip";
      chip.textContent = item[0] + ": " + item[1];
      wrap.appendChild(chip);
    });
  }

  function renderWarnings(warnings) {
    const wrap = el("aiWarnings");
    if (!wrap) return;
    wrap.textContent = warnings && warnings.length ? warnings.join("\n") : "No extra warnings.";
  }

  function renderTrace(toolTrace) {
    const traceBox = el("aiTrace");
    if (!traceBox) return;
    if (!toolTrace || toolTrace.length === 0) {
      traceBox.textContent = "";
      return;
    }
    traceBox.textContent = toolTrace.map(function (entry, index) {
      const lines = [];
      lines.push((index + 1) + ". " + entry.tool_name);
      if (entry.tool_name === "apply_level_edits") {
        const operations = (entry.arguments && entry.arguments.operations) || [];
        lines.push("   operations: " + operations.map(function (item) {
          return item.action;
        }).join(", "));
      } else if (entry.tool_name === "solve_level" && entry.result) {
        lines.push("   solvable: " + String(entry.result.solvable));
        lines.push("   min_steps: " + String(entry.result.min_steps));
      } else if (entry.tool_name === "score_level" && entry.result) {
        lines.push("   difficulty: " + String(entry.result.difficulty || "-"));
      } else if (entry.tool_name === "validate_level" && entry.result) {
        lines.push("   valid: " + String(entry.result.valid));
      } else {
        lines.push("   args: " + JSON.stringify(entry.arguments || {}));
      }
      return lines.join("\n");
    }).join("\n\n");
  }

  function clearModifyJobPolling() {
    if (state.modifyJobPollTimer) {
      window.clearTimeout(state.modifyJobPollTimer);
      state.modifyJobPollTimer = null;
    }
  }

  function resetTransientState() {
    if (state.streamAbortController) {
      try {
        state.streamAbortController.abort();
      } catch (_error) {
        // Ignore abort errors.
      }
      state.streamAbortController = null;
    }
    clearModifyJobPolling();
    state.modifyJob = null;
    state.modifyJobAnnouncedId = null;
    state.pendingLevel = null;
    renderModifyJob();
    if (el("aiApplyLevelBtn")) {
      el("aiApplyLevelBtn").hidden = true;
      el("aiApplyLevelBtn").disabled = true;
    }
    if (el("aiStopBtn")) {
      el("aiStopBtn").disabled = true;
    }
  }

  function finishStreamingUI(message) {
    state.streamAbortController = null;
    finalizeAssistantState();
    renderMessages();
    setBusy(false);
    if (message) {
      setResultText(message);
    }
  }

  function isAbortError(error) {
    return Boolean(
      error && (
        error.name === "AbortError"
        || String(error.message || "").toLowerCase().indexOf("abort") >= 0
      )
    );
  }

  function stopCurrentGeneration(reasonText) {
    if (!state.streamAbortController) return false;
    try {
      state.streamAbortController.abort();
    } catch (_error) {
      // Ignore abort errors.
    }
    finishStreamingUI(reasonText || "Stopped the current reply.");
    return true;
  }

  function renderModifyJob() {
    const card = el("aiModifyJobCard");
    const badge = el("aiModifyJobBadge");
    const statusBox = el("aiModifyJobStatus");
    const stagesWrap = el("aiModifyJobStages");
    const attemptsBox = el("aiModifyJobAttempts");
    if (!card || !badge || !statusBox || !stagesWrap || !attemptsBox) return;

    const job = state.modifyJob;
    if (!job) {
      card.hidden = true;
      return;
    }

    card.hidden = false;
    badge.textContent = String(job.status || "idle");
    statusBox.textContent = job.message || "Modify job is waiting for updates.";

    stagesWrap.innerHTML = "";
    (job.stageHistory || []).forEach(function (stage, index, list) {
      const chip = document.createElement("span");
      chip.className = "ai-stage-chip " + (index === list.length - 1 ? "is-active" : "is-done");
      chip.textContent = String(stage || "").replace(/_/g, " ");
      stagesWrap.appendChild(chip);
    });

    const attempts = Array.isArray(job.attempts) ? job.attempts : [];
    if (!attempts.length) {
      attemptsBox.textContent = job.attempt
        ? "Current attempt: " + String(job.attempt)
        : "Retry details will appear here when the modify agent evaluates candidates.";
      return;
    }

    attemptsBox.textContent = attempts.map(function (item) {
      return "Attempt " + String(item.attempt || "?") + ": " + String(item.reason || item.summary || "pending");
    }).join("\n");
  }

  function updateModifyJob(job) {
    if (!job || !job.jobId) return;
    const previous = state.modifyJob && state.modifyJob.jobId === job.jobId ? state.modifyJob : null;
    const history = previous && Array.isArray(previous.stageHistory) ? previous.stageHistory.slice() : [];
    if (job.stage) {
      if (history.length === 0 || history[history.length - 1] !== job.stage) {
        history.push(job.stage);
      }
    }
    state.modifyJob = Object.assign({}, previous || {}, job, { stageHistory: history });
    renderModifyJob();
  }

  function pushAssistantMessage(text) {
    const value = String(text || "").trim();
    if (!value) return;
    state.messages.push({ role: "assistant", content: value });
    renderMessages();
  }

  function ensureWelcomeMessage() {
    if (state.messages.length > 0) return;
    state.messages = [{
      role: "assistant",
      content: "Hello, I am your level assistant. Ask me about analysis, difficulty, or edit ideas for the current board.",
    }];
  }

  function ensureAssistantMessage() {
    if (state.messages.length === 0 || state.messages[state.messages.length - 1].role !== "assistant") {
      state.messages.push({ role: "assistant", content: "" });
    }
    return state.messages[state.messages.length - 1];
  }

  function buildStageItems(previousItems, stage, message) {
    const items = Array.isArray(previousItems) ? previousItems.map(function (item) {
      return {
        key: item.key,
        label: item.label,
        status: item.status,
      };
    }) : [];
    const currentIndex = STAGE_ORDER.indexOf(stage);

    if (currentIndex < 0) {
      return items;
    }

    items.forEach(function (item) {
      const itemIndex = STAGE_ORDER.indexOf(item.key);
      if (itemIndex < currentIndex) {
        item.status = "done";
      } else if (item.key === stage) {
        item.status = "active";
        if (message) item.label = message;
      } else if (itemIndex > currentIndex && item.status !== "pending") {
        item.status = "pending";
      }
    });

    const existing = items.some(function (item) {
      return item.key === stage;
    });
    if (!existing) {
      items.push({
        key: stage,
        label: message || stage,
        status: "active",
      });
    }

    return items.sort(function (left, right) {
      return STAGE_ORDER.indexOf(left.key) - STAGE_ORDER.indexOf(right.key);
    });
  }

  function updateAssistantProgress(stage, message) {
    const assistant = ensureAssistantMessage();
    assistant.thinking = true;
    assistant.statusText = message || "Thinking...";
    assistant.stageItems = buildStageItems(assistant.stageItems, stage, message);
    renderMessages();
  }

  function renderSessionList() {
    const wrap = el("aiSessionList");
    if (!wrap) return;
    wrap.innerHTML = "";

    if (!state.sessions.length) {
      const hint = document.createElement("div");
      hint.className = "ai-session-empty hint";
      hint.textContent = "No previous chats yet.";
      wrap.appendChild(hint);
      return;
    }

    state.sessions.forEach(function (session) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "ai-session-btn" + (session.sessionId === state.activeSessionId ? " is-active" : "");

      const title = document.createElement("span");
      title.className = "ai-session-title";
      title.textContent = session.title || "New chat";
      button.appendChild(title);

      const preview = document.createElement("span");
      preview.className = "ai-session-preview";
      preview.textContent = session.preview || "No messages yet.";
      button.appendChild(preview);

      const meta = document.createElement("span");
      meta.className = "ai-session-meta";
      meta.textContent = [
        session.messageCount != null ? String(session.messageCount) + " msgs" : "",
        formatTimestamp(session.updatedAt),
      ].filter(Boolean).join(" | ");
      button.appendChild(meta);

      button.onclick = function () {
        if (session.sessionId === state.activeSessionId) return;
        switchSession(session.sessionId);
      };
      wrap.appendChild(button);
    });
  }

  function renderMessages() {
    ensureWelcomeMessage();
    const wrap = el("aiMessages");
    if (!wrap) return;
    wrap.innerHTML = "";

    state.messages.forEach(function (message) {
      const row = document.createElement("div");
      row.className = "ai-message" + (message.role === "user" ? " user" : "");

      const meta = document.createElement("div");
      meta.className = "ai-message-meta";

      const dot = document.createElement("span");
      dot.className = "ai-message-dot";
      dot.textContent = message.role === "user" ? "ME" : "AI";
      meta.appendChild(dot);

      const label = document.createElement("span");
      label.textContent = message.role === "user" ? "You" : "Assistant";
      meta.appendChild(label);

      const bubble = document.createElement("div");
      bubble.className = "ai-bubble";

      if (message.role !== "user" && message.stageItems && message.stageItems.length > 0) {
        const progress = document.createElement("div");
        progress.className = "ai-stage-progress";

        const statusRow = document.createElement("div");
        statusRow.className = "ai-stage-status";

        const indicator = document.createElement("span");
        indicator.className = "ai-stage-indicator" + (message.thinking ? " is-thinking" : "");
        statusRow.appendChild(indicator);

        const statusText = document.createElement("span");
        statusText.className = "ai-stage-text";
        statusText.textContent = message.statusText || "Thinking...";
        statusRow.appendChild(statusText);
        progress.appendChild(statusRow);

        const stageList = document.createElement("div");
        stageList.className = "ai-stage-list";
        message.stageItems.forEach(function (item) {
          const chip = document.createElement("span");
          chip.className = "ai-stage-chip is-" + (item.status || "pending");
          chip.textContent = item.label || item.key;
          stageList.appendChild(chip);
        });
        progress.appendChild(stageList);
        bubble.appendChild(progress);
      }

      const content = document.createElement("div");
      content.className = "ai-bubble-text";
      if (message.content) {
        content.textContent = message.content;
      } else if (message.thinking) {
        content.classList.add("is-thinking-placeholder");

        const thinkingLabel = document.createElement("span");
        thinkingLabel.textContent = "Thinking";
        content.appendChild(thinkingLabel);

        const dots = document.createElement("span");
        dots.className = "ai-thinking-dots";
        for (let index = 0; index < 3; index += 1) {
          const dotPulse = document.createElement("span");
          dotPulse.className = "ai-thinking-dot";
          dots.appendChild(dotPulse);
        }
        content.appendChild(dots);
      } else {
        content.textContent = "";
      }
      bubble.appendChild(content);

      row.appendChild(meta);
      row.appendChild(bubble);
      wrap.appendChild(row);
    });

    wrap.scrollTop = wrap.scrollHeight;
  }

  function renderSuggestions(items) {
    const wrap = el("aiSuggestionChips");
    if (!wrap) return;
    state.suggestions = sanitizeSuggestions(items);
    if (!state.suggestions.length) {
      state.suggestions = DEFAULT_SUGGESTIONS.slice();
    }
    wrap.innerHTML = "";
    state.suggestions.forEach(function (text) {
      const chip = document.createElement("button");
      chip.type = "button";
      chip.className = "ai-chip";
      chip.textContent = text;
      chip.onclick = function () {
        if (el("aiRequestInput")) {
          el("aiRequestInput").value = text;
        }
        submitRequest({ text: text });
      };
      wrap.appendChild(chip);
    });
  }

  function setAssistantDraft(text) {
    const assistant = ensureAssistantMessage();
    assistant.content = text || "";
    assistant.thinking = false;
    renderMessages();
  }

  function finalizeAssistantState() {
    const assistant = ensureAssistantMessage();
    assistant.thinking = false;
    assistant.statusText = "";
    assistant.stageItems = [];
  }

  function pushUserMessage(text) {
    state.messages.push({ role: "user", content: text });
    renderMessages();
  }

  function applySessionDetail(detail) {
    state.activeSessionId = detail.sessionId || detail.session_id || null;
    persistActiveSessionId(state.activeSessionId);
    state.messages = Array.isArray(detail.messages) ? detail.messages.map(function (item) {
      return {
        role: item.role || "assistant",
        content: item.content || "",
      };
    }) : [];
    renderSuggestions(detail.suggestions || []);
    resetTransientState();
    renderMessages();
    renderSessionList();
  }

  function syncResponse(response) {
    state.activeSessionId = response.sessionId || state.activeSessionId;
    persistActiveSessionId(state.activeSessionId);
    state.pendingLevel = response.updatedLevel || null;
    if (Array.isArray(response.messages) && response.messages.length > 0) {
      state.messages = response.messages.map(function (item) {
        return {
          role: item.role || "assistant",
          content: item.content || "",
        };
      });
    } else {
      setAssistantDraft(response.message || "AI returned a response.");
      finalizeAssistantState();
    }
    renderMessages();
    renderSuggestions((response.suggestions && response.suggestions.length > 0) ? response.suggestions : state.suggestions);
    renderMetrics(response.analysis, response.warnings || []);
    renderWarnings(response.warnings || []);
    renderTrace(response.toolTrace || null);
    setResultText(response.analysis_summary || response.message || "AI returned a response.");

    if (el("aiApplyLevelBtn")) {
      el("aiApplyLevelBtn").hidden = !state.pendingLevel;
      el("aiApplyLevelBtn").disabled = !state.pendingLevel;
    }

    refreshSessionList().catch(function () {
      // Ignore background refresh issues.
    });
  }

  function buildPayload(userRequest) {
    const currentLevel = root.getCurrentPuzzleSpec();
    return {
      user_id: state.userId,
      session_id: state.activeSessionId || "v1-editor-session",
      message: userRequest,
      current_level: currentLevel,
      user_request: userRequest,
      level: currentLevel,
      rulePack: root.getActiveRulePack ? root.getActiveRulePack() : null,
      debug: Boolean(window.location.search && window.location.search.indexOf("debug_ai=1") >= 0),
    };
  }

  async function refreshSessionList() {
    const adapter = getAdapter();
    if (!adapter || typeof adapter.listSessions !== "function") return;
    const sessions = await adapter.listSessions({ user_id: state.userId });
    state.sessions = Array.isArray(sessions) ? sessions : [];
    renderSessionList();
  }

  async function loadSession(sessionId) {
    const adapter = getAdapter();
    if (!adapter || typeof adapter.getSession !== "function") {
      state.activeSessionId = sessionId || "v1-editor-session";
      persistActiveSessionId(state.activeSessionId);
      renderSessionList();
      renderMessages();
      return;
    }
    const detail = await adapter.getSession(sessionId, { user_id: state.userId });
    applySessionDetail(detail);
  }

  async function switchSession(sessionId) {
    resetTransientState();
    setBusy(true);
    try {
      await loadSession(sessionId);
      setResultText("Loaded the selected chat session.");
      renderMetrics(null, []);
      renderWarnings([]);
      renderTrace(null);
    } catch (error) {
      setResultText(error && error.message ? error.message : String(error));
    } finally {
      setBusy(false);
    }
  }

  async function createNewSession() {
    const adapter = getAdapter();
    if (!adapter || typeof adapter.createSession !== "function") {
      state.activeSessionId = "v1-editor-session";
      persistActiveSessionId(state.activeSessionId);
      state.messages = [];
      renderSuggestions(DEFAULT_SUGGESTIONS);
      resetTransientState();
      renderMessages();
      return;
    }

    const currentLevel = root.getCurrentPuzzleSpec ? root.getCurrentPuzzleSpec() : null;
    const detail = await adapter.createSession({
      user_id: state.userId,
      current_level: currentLevel,
    });
    applySessionDetail(detail);
    await refreshSessionList();
    setResultText("Started a new chat session.");
    renderMetrics(null, []);
    renderWarnings([]);
    renderTrace(null);
  }

  async function initializeSessions() {
    const adapter = getAdapter();
    if (!adapter || typeof adapter.listSessions !== "function" || typeof adapter.getSession !== "function") {
      activateLegacySession();
      return;
    }

    try {
      await refreshSessionList();
      const rememberedSessionId = readStoredSessionId();
      const hasRememberedSession = state.sessions.some(function (item) {
        return item.sessionId === rememberedSessionId;
      });
      const targetSessionId = hasRememberedSession
        ? rememberedSessionId
        : state.sessions.length > 0
          ? state.sessions[0].sessionId
          : "";

      if (!targetSessionId) {
        await createNewSession();
        return;
      }

      await loadSession(targetSessionId);
    } catch (_error) {
      activateLegacySession();
      setResultText("Session API is unavailable, so the chat fell back to single-session mode.");
    }
  }

  function handleModifyJobTerminal(job) {
    if (!job || !job.jobId || state.modifyJobAnnouncedId === job.jobId) return;
    const result = job.result || {};
    state.modifyJobAnnouncedId = job.jobId;

    if (result.updatedLevel) {
      state.pendingLevel = result.updatedLevel;
      if (el("aiApplyLevelBtn")) {
        el("aiApplyLevelBtn").hidden = false;
        el("aiApplyLevelBtn").disabled = false;
      }
      renderMetrics(result.analysis || null, result.warnings || []);
      renderWarnings(result.warnings || []);
      renderTrace(result.toolTrace || null);
      setResultText(job.message || "A validated board update is ready to apply.");
      pushAssistantMessage(job.message || "The background modify job finished. A validated board update is ready to apply.");
      return;
    }

    setResultText(job.message || "The background modify job finished without an applicable update.");
    pushAssistantMessage(job.message || "The background modify job finished, but no applicable board update was produced.");
  }

  async function pollModifyJob(jobId) {
    const adapter = getAdapter();
    if (!adapter || typeof adapter.getModifyJobStatus !== "function") return;

    try {
      const job = await adapter.getModifyJobStatus(jobId);
      updateModifyJob(job);
      const status = String(job.status || "").toLowerCase();
      if (status === "queued" || status === "running") {
        clearModifyJobPolling();
        state.modifyJobPollTimer = window.setTimeout(function () {
          pollModifyJob(jobId);
        }, MODIFY_POLL_MS);
        return;
      }
      clearModifyJobPolling();
      handleModifyJobTerminal(job);
    } catch (error) {
      clearModifyJobPolling();
      setResultText(error && error.message ? error.message : String(error));
      pushAssistantMessage(error && error.message ? error.message : String(error));
    }
  }

  async function startBackgroundModifyJob(payload, intent) {
    const adapter = getAdapter();
    if (!adapter || typeof adapter.startModifyJob !== "function") {
      return;
    }

    clearModifyJobPolling();
    state.pendingLevel = null;
    if (el("aiApplyLevelBtn")) {
      el("aiApplyLevelBtn").hidden = true;
      el("aiApplyLevelBtn").disabled = true;
    }

    const ticket = await adapter.startModifyJob(
      Object.assign({}, payload, {
        intent: intent || null,
      })
    );
    state.modifyJobAnnouncedId = null;
    updateModifyJob(ticket);
    setResultText(ticket.message || "The background modify job has started.");
    pushAssistantMessage("I have started a background board-edit job. You can keep chatting while I validate candidates.");
    pollModifyJob(ticket.jobId);
  }

  async function submitRequest(options) {
    const adapter = getAdapter();
    if (!adapter || typeof adapter.callLevelAgent !== "function") {
      setResultText("No AI adapter is available.");
      return;
    }
    if (!root.getCurrentPuzzleSpec) {
      setResultText("The current page does not expose a puzzle reader.");
      return;
    }
    if (!state.activeSessionId) {
      try {
        await initializeSessions();
      } catch (_error) {
        activateLegacySession();
      }
    }

    const mode = options && options.mode;
    const rawInput = (options && options.text) || (el("aiRequestInput") && el("aiRequestInput").value.trim()) || "";
    const fallbackRequest = mode === "analyze"
      ? "Analyze this level"
      : mode === "refine"
        ? "Give me edit suggestions for this level without enlarging the board"
        : "Analyze this level";
    const userRequest = rawInput || fallbackRequest;

    state.pendingLevel = null;
    pushUserMessage(userRequest);
    const assistant = ensureAssistantMessage();
    assistant.content = "";
    assistant.thinking = true;
    assistant.statusText = "Thinking...";
    assistant.stageItems = [];
    renderMessages();
    setBusy(true);
    setResultText("AI is analyzing the current level...");
    renderMetrics(null, []);
    renderWarnings([]);
    renderTrace(null);
    if (el("aiRequestInput")) {
      el("aiRequestInput").value = "";
    }

    const payload = buildPayload(userRequest);
    let completedResponse = null;

    try {
      if (typeof adapter.streamLevelAgent === "function") {
        const streamAbortController = typeof AbortController === "function" ? new AbortController() : null;
        state.streamAbortController = streamAbortController;
        setBusy(true);
        let streamedText = "";
        await adapter.streamLevelAgent(payload, {
          signal: streamAbortController ? streamAbortController.signal : undefined,
          onEvent: function (event) {
            if (!event || !event.type) return;
            if (event.type === "status") {
              setResultText(event.message || "AI is working...");
              updateAssistantProgress(event.stage, event.message || "AI is working...");
              return;
            }
            if (event.type === "message_start") {
              streamedText = "";
              const currentAssistant = ensureAssistantMessage();
              currentAssistant.thinking = true;
              currentAssistant.statusText = "Writing the reply...";
              currentAssistant.content = "";
              renderMessages();
              return;
            }
            if (event.type === "message_delta") {
              streamedText += event.delta || "";
              setAssistantDraft(streamedText);
              const currentAssistant = ensureAssistantMessage();
              currentAssistant.thinking = true;
              currentAssistant.statusText = "Writing the reply...";
              renderMessages();
              return;
            }
            if (event.type === "complete") {
              completedResponse = event.payload || {};
              syncResponse(completedResponse);
              finishStreamingUI(completedResponse.analysis_summary || completedResponse.message || "AI completed the reply.");
              return;
            }
            if (event.type === "error") {
              setAssistantDraft(event.message || "AI streaming failed.");
              setResultText(event.message || "AI streaming failed.");
              finishStreamingUI(event.message || "AI streaming failed.");
            }
          },
        });
        if (completedResponse && completedResponse.intent && completedResponse.intent.intent_type === "modify") {
          await startBackgroundModifyJob(payload, completedResponse.intent);
        }
      } else {
        completedResponse = await adapter.callLevelAgent(payload);
        syncResponse(completedResponse);
        if (completedResponse && completedResponse.intent && completedResponse.intent.intent_type === "modify") {
          await startBackgroundModifyJob(payload, completedResponse.intent);
        }
      }
    } catch (streamError) {
      if (isAbortError(streamError)) {
        finishStreamingUI("Stopped the current reply.");
        return;
      }
      try {
        state.streamAbortController = null;
        completedResponse = await adapter.callLevelAgent(payload);
        syncResponse(completedResponse);
        if (completedResponse && completedResponse.intent && completedResponse.intent.intent_type === "modify") {
          await startBackgroundModifyJob(payload, completedResponse.intent);
        }
        setResultText("Fell back to non-streaming mode.");
      } catch (error) {
        state.pendingLevel = null;
        setAssistantDraft(error && error.message ? error.message : String(error));
        setResultText(streamError && streamError.message ? streamError.message : String(streamError));
        if (el("aiApplyLevelBtn")) {
          el("aiApplyLevelBtn").hidden = true;
        }
      }
    } finally {
      state.streamAbortController = null;
      setBusy(false);
    }
  }

  async function bindPanel() {
    renderMessages();
    renderSuggestions(state.suggestions);
    renderModifyJob();
    renderSessionList();

    if (el("aiAnalyzeBtn")) {
      el("aiAnalyzeBtn").onclick = function () {
        submitRequest({ mode: "analyze" });
      };
    }
    if (el("aiRefineBtn")) {
      el("aiRefineBtn").onclick = function () {
        submitRequest({ mode: "refine" });
      };
    }
    if (el("aiSendBtn")) {
      el("aiSendBtn").onclick = function () {
        submitRequest({});
      };
    }
    if (el("aiStopBtn")) {
      el("aiStopBtn").onclick = function () {
        stopCurrentGeneration("Stopped the current reply.");
      };
      el("aiStopBtn").disabled = true;
    }
    if (el("aiNewSessionBtn")) {
      el("aiNewSessionBtn").onclick = function () {
        resetTransientState();
        setBusy(true);
        createNewSession()
          .catch(function (error) {
            setResultText(error && error.message ? error.message : String(error));
          })
          .finally(function () {
            setBusy(false);
          });
      };
    }
    if (el("aiRequestInput")) {
      el("aiRequestInput").addEventListener("keydown", function (event) {
        if (event.key === "Enter" && !event.shiftKey) {
          event.preventDefault();
          submitRequest({});
        }
      });
    }
    if (el("aiApplyLevelBtn")) {
      el("aiApplyLevelBtn").onclick = function () {
        if (!state.pendingLevel) return;
        root.loadPuzzleSpec(state.pendingLevel, "Applied AI-generated level changes.");
        state.pendingLevel = null;
        setAssistantDraft("The AI changes have been applied to the editor.");
        setResultText("The AI changes have been applied to the editor.");
        el("aiApplyLevelBtn").hidden = true;
      };
      el("aiApplyLevelBtn").hidden = true;
    }

    setBusy(true);
    try {
      await initializeSessions();
      setResultText("Chat history is ready.");
    } catch (error) {
      setResultText(error && error.message ? error.message : String(error));
    } finally {
      setBusy(false);
    }
  }

  window.addEventListener("beforeunload", clearModifyJobPolling);
  window.addEventListener("DOMContentLoaded", function () {
    bindPanel().catch(function (error) {
      setResultText(error && error.message ? error.message : String(error));
    });
  });
})();
