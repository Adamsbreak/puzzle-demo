(function () {
  const root = window.PuzzleV1;
  const backendUrl = window.PuzzleV1AIBackendUrl || "http://127.0.0.1:8011";

  async function callLevelAgent(payload) {
    const response = await fetch(backendUrl + "/api/ai/level-agent", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      const text = await response.text();
      throw new Error("AI backend request failed: " + response.status + " " + text);
    }

    return response.json();
  }

  async function streamLevelAgent(payload, handlers) {
    const response = await fetch(backendUrl + "/api/ai/level-agent/stream", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
      },
      body: JSON.stringify(payload),
      signal: handlers && handlers.signal ? handlers.signal : undefined,
    });

    if (!response.ok || !response.body) {
      const text = await response.text();
      throw new Error("AI backend stream failed: " + response.status + " " + text);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder("utf-8");
    let buffer = "";
    let shouldStop = false;

    function emitEventBlock(eventBlock) {
      if (!eventBlock) return;
      const lines = eventBlock.split("\n");
      lines.forEach(function (line) {
        if (!line.startsWith("data: ")) return;
        const payloadText = line.slice(6);
        if (!payloadText) return;
        const event = JSON.parse(payloadText);
        if (handlers && typeof handlers.onEvent === "function") {
          handlers.onEvent(event);
        }
        if (event && (event.type === "complete" || event.type === "error")) {
          shouldStop = true;
        }
      });
    }

    while (true) {
      const result = await reader.read();
      if (result.done) {
        buffer += decoder.decode();
        break;
      }

      buffer += decoder.decode(result.value, { stream: true });
      const events = buffer.split("\n\n");
      buffer = events.pop() || "";

      events.forEach(emitEventBlock);
      if (shouldStop) {
        try {
          await reader.cancel();
        } catch (_error) {
          // Ignore cancellation errors.
        }
        break;
      }
    }

    if (buffer.trim()) {
      emitEventBlock(buffer.trim());
    }
  }

  async function startModifyJob(payload) {
    const response = await fetch(backendUrl + "/api/ai/modify-jobs", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      const text = await response.text();
      throw new Error("AI modify job start failed: " + response.status + " " + text);
    }

    return response.json();
  }

  async function listSessions(payload) {
    const userId = encodeURIComponent((payload && (payload.user_id || payload.userId)) || "local-user");
    const response = await fetch(backendUrl + "/api/ai/sessions?user_id=" + userId, {
      method: "GET",
      headers: {
        "Accept": "application/json",
      },
    });

    if (!response.ok) {
      const text = await response.text();
      throw new Error("AI session list failed: " + response.status + " " + text);
    }

    return response.json();
  }

  async function createSession(payload) {
    const response = await fetch(backendUrl + "/api/ai/sessions", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload || {}),
    });

    if (!response.ok) {
      const text = await response.text();
      throw new Error("AI session create failed: " + response.status + " " + text);
    }

    return response.json();
  }

  async function getSession(sessionId, payload) {
    const userId = encodeURIComponent((payload && (payload.user_id || payload.userId)) || "local-user");
    const response = await fetch(
      backendUrl + "/api/ai/sessions/" + encodeURIComponent(sessionId) + "?user_id=" + userId,
      {
        method: "GET",
        headers: {
          "Accept": "application/json",
        },
      }
    );

    if (!response.ok) {
      const text = await response.text();
      throw new Error("AI session load failed: " + response.status + " " + text);
    }

    return response.json();
  }

  async function getModifyJobStatus(jobId) {
    const response = await fetch(backendUrl + "/api/ai/modify-jobs/" + encodeURIComponent(jobId), {
      method: "GET",
      headers: {
        "Accept": "application/json",
      },
    });

    if (!response.ok) {
      const text = await response.text();
      throw new Error("AI modify job status failed: " + response.status + " " + text);
    }

    return response.json();
  }

  root.setAIAdapter({
    id: "langgraph-qwen-level-agent",
    description: "LangGraph-based AI orchestration with a Qwen-powered main chat agent.",
    capabilities: [
      "analyze-level",
      "refine-level",
      "validate-solve-loop",
      "chat-intent-compile",
      "modify-agent-async-loop",
      "rule-refactor-placeholder",
      "streaming-chat",
      "async-modify-jobs",
    ],
    backendUrl: backendUrl,
    callLevelAgent: callLevelAgent,
    streamLevelAgent: streamLevelAgent,
    startModifyJob: startModifyJob,
    listSessions: listSessions,
    createSession: createSession,
    getSession: getSession,
    getModifyJobStatus: getModifyJobStatus,
  });
})();
