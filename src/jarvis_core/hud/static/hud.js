"use strict";

const SESSION_STORAGE_KEY = "jarvis.operator.session-id";

const elements = {
  activityList: document.querySelector("#activity-list"),
  chatForm: document.querySelector("#chat-form"),
  clearActivityButton: document.querySelector("#clear-activity-button"),
  coreState: document.querySelector("#core-state"),
  coreStateLabel: document.querySelector("#core-state-label"),
  footerStatus: document.querySelector("#footer-status"),
  messageInput: document.querySelector("#message-input"),
  modelName: document.querySelector("#model-name"),
  newSessionButton: document.querySelector("#new-session-button"),
  quickActions: Array.from(document.querySelectorAll("[data-prompt]")),
  sendButton: document.querySelector("#send-button"),
  serviceName: document.querySelector("#service-name"),
  serviceVersion: document.querySelector("#service-version"),
  sessionValue: document.querySelector("#session-value"),
  thinkingIndicator: document.querySelector("#thinking-indicator"),
  toastRegion: document.querySelector("#toast-region"),
  transcript: document.querySelector("#transcript"),
  turnState: document.querySelector("#turn-state"),
  welcomeState: document.querySelector("#welcome-state"),
};

const state = {
  busy: false,
  online: false,
  sessionId: readSessionId(),
};

function readSessionId() {
  try {
    return window.localStorage.getItem(SESSION_STORAGE_KEY);
  } catch (_error) {
    return null;
  }
}

function persistSessionId(sessionId) {
  try {
    if (sessionId) {
      window.localStorage.setItem(SESSION_STORAGE_KEY, sessionId);
    } else {
      window.localStorage.removeItem(SESSION_STORAGE_KEY);
    }
  } catch (_error) {
    showToast("Browser storage is unavailable. This session will not reopen automatically.");
  }
}

function createCorrelationId() {
  if (window.crypto && typeof window.crypto.randomUUID === "function") {
    return window.crypto.randomUUID();
  }
  return `hud-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function setConnection(status, label) {
  elements.coreState.dataset.state = status;
  elements.coreStateLabel.textContent = label;
  state.online = status === "online";
  updateControls();
}

function setBusy(busy) {
  state.busy = busy;
  elements.thinkingIndicator.hidden = !busy;
  elements.turnState.textContent = busy ? "Processing" : "Standing by";
  updateControls();
}

function updateControls() {
  const hasMessage = elements.messageInput.value.trim().length > 0;
  elements.sendButton.disabled = state.busy || !state.online || !hasMessage;
  elements.newSessionButton.disabled = state.busy;
  for (const button of elements.quickActions) {
    button.disabled = state.busy || !state.online;
  }
}

function updateSessionLabel() {
  elements.sessionValue.textContent = state.sessionId || "New conversation";
}

function clearTranscript() {
  elements.transcript.replaceChildren();
  const welcome = document.createElement("div");
  welcome.className = "welcome-state";
  welcome.id = "welcome-state";

  const kicker = document.createElement("p");
  kicker.className = "welcome-kicker";
  kicker.textContent = state.online ? "Core online" : "Core link pending";

  const title = document.createElement("p");
  title.className = "welcome-title";
  title.textContent = "Standing by.";

  const detail = document.createElement("p");
  detail.className = "welcome-detail";
  detail.textContent = "What do you need?";

  welcome.append(kicker, title, detail);
  elements.transcript.append(welcome);
  elements.welcomeState = welcome;
}

function appendMessage(role, content) {
  if (elements.welcomeState && elements.welcomeState.isConnected) {
    elements.welcomeState.remove();
  }

  const message = document.createElement("article");
  message.className = "message";
  message.dataset.role = role;

  const roleLabel = document.createElement("p");
  roleLabel.className = "message-role";
  roleLabel.textContent = role === "assistant" ? "JARVIS" : "You";

  const messageContent = document.createElement("div");
  messageContent.className = "message-content";
  messageContent.textContent = content;

  message.append(roleLabel, messageContent);
  elements.transcript.append(message);
  elements.transcript.scrollTop = elements.transcript.scrollHeight;
}

function resetActivity() {
  elements.activityList.replaceChildren();
  const empty = document.createElement("li");
  empty.className = "activity-empty";
  empty.textContent = "No tool activity";
  elements.activityList.append(empty);
}

function addToolActivity(toolName) {
  const empty = elements.activityList.querySelector(".activity-empty");
  if (empty) {
    empty.remove();
  }

  const item = document.createElement("li");
  const tool = document.createElement("span");
  const timestamp = document.createElement("span");

  tool.className = "activity-tool";
  tool.textContent = toolName;
  timestamp.className = "activity-time";
  timestamp.textContent = new Intl.DateTimeFormat(undefined, {
    hour: "numeric",
    minute: "2-digit",
    second: "2-digit",
  }).format(new Date());

  item.append(tool, timestamp);
  elements.activityList.prepend(item);
}

function showToast(message) {
  const toast = document.createElement("div");
  toast.className = "toast";
  toast.setAttribute("role", "alert");
  toast.textContent = message;
  elements.toastRegion.append(toast);
  window.setTimeout(() => toast.remove(), 6500);
}

async function parseJsonResponse(response) {
  try {
    return await response.json();
  } catch (_error) {
    return null;
  }
}

function safeErrorMessage(payload, fallback) {
  if (
    payload &&
    payload.error &&
    typeof payload.error.message === "string" &&
    payload.error.message.trim()
  ) {
    return payload.error.message;
  }
  return fallback;
}

async function checkHealth() {
  setConnection("connecting", "Connecting");
  elements.footerStatus.textContent = "Contacting JARVIS Core";
  try {
    const response = await fetch("/v1/health", {
      headers: { Accept: "application/json" },
      cache: "no-store",
    });
    const payload = await parseJsonResponse(response);
    if (!response.ok || !payload) {
      throw new Error("Health response was unavailable.");
    }
    elements.serviceName.textContent = payload.service;
    elements.serviceVersion.textContent = payload.version;
    elements.footerStatus.textContent = `${payload.service} ${payload.version}`;
    setConnection("online", "Core online");
    return true;
  } catch (_error) {
    elements.serviceName.textContent = "Unavailable";
    elements.serviceVersion.textContent = "--";
    elements.footerStatus.textContent = "JARVIS Core is offline";
    setConnection("offline", "Core offline");
    return false;
  }
}

async function restoreTranscript() {
  if (!state.sessionId) {
    updateSessionLabel();
    return;
  }

  elements.turnState.textContent = "Restoring";
  try {
    const response = await fetch(
      `/v1/conversations/${encodeURIComponent(state.sessionId)}/messages?limit=100`,
      { headers: { Accept: "application/json" }, cache: "no-store" },
    );
    const payload = await parseJsonResponse(response);
    if (!response.ok || !payload) {
      const errorCode = payload && payload.error ? payload.error.code : null;
      if (response.status === 404 && errorCode === "session_not_found") {
        state.sessionId = null;
        persistSessionId(null);
        updateSessionLabel();
        clearTranscript();
        showToast("The previous session is no longer available. A new conversation is ready.");
        return;
      }
      throw new Error(safeErrorMessage(payload, "The transcript could not be restored."));
    }

    elements.transcript.replaceChildren();
    elements.welcomeState = null;
    for (const message of payload.messages) {
      appendMessage(message.role, message.content);
    }
    if (payload.messages.length === 0) {
      clearTranscript();
    }
    elements.footerStatus.textContent = "Durable session restored";
    updateSessionLabel();
  } catch (error) {
    showToast(error instanceof Error ? error.message : "The transcript could not be restored.");
  } finally {
    elements.turnState.textContent = "Standing by";
  }
}

function startNewSession() {
  if (state.busy) {
    return;
  }
  state.sessionId = null;
  persistSessionId(null);
  updateSessionLabel();
  clearTranscript();
  resetActivity();
  elements.modelName.textContent = "Not contacted";
  elements.footerStatus.textContent = "New conversation ready";
  elements.messageInput.focus();
}

async function sendMessage(message) {
  const normalizedMessage = message.trim();
  if (!normalizedMessage || state.busy || !state.online) {
    return;
  }

  appendMessage("user", normalizedMessage);
  elements.messageInput.value = "";
  resizeComposer();
  setBusy(true);

  const payload = {
    message: normalizedMessage,
    correlation_id: createCorrelationId(),
  };
  if (state.sessionId) {
    payload.session_id = state.sessionId;
  }

  try {
    const response = await fetch("/v1/chat", {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    });
    const responsePayload = await parseJsonResponse(response);
    if (!response.ok || !responsePayload) {
      if (response.status === 404 && responsePayload?.error?.code === "session_not_found") {
        state.sessionId = null;
        persistSessionId(null);
        updateSessionLabel();
      }
      throw new Error(
        safeErrorMessage(responsePayload, `JARVIS returned HTTP ${response.status}.`),
      );
    }

    state.sessionId = responsePayload.session_id;
    persistSessionId(state.sessionId);
    updateSessionLabel();
    elements.modelName.textContent = `${responsePayload.provider} / ${responsePayload.model}`;
    appendMessage("assistant", responsePayload.message);
    for (const toolName of responsePayload.tools_used || []) {
      addToolActivity(toolName);
    }
    const toolCount = responsePayload.tools_used?.length || 0;
    elements.footerStatus.textContent = toolCount
      ? `Completed with ${toolCount} ${toolCount === 1 ? "tool" : "tools"}`
      : "Response complete";
  } catch (error) {
    const messageText = error instanceof Error ? error.message : "JARVIS could not respond.";
    showToast(messageText);
    elements.turnState.textContent = "Request failed";
    elements.footerStatus.textContent = "Request failed safely";
  } finally {
    setBusy(false);
    elements.messageInput.focus();
  }
}

function resizeComposer() {
  elements.messageInput.style.height = "auto";
  elements.messageInput.style.height = `${Math.min(elements.messageInput.scrollHeight, 150)}px`;
  updateControls();
}

elements.chatForm.addEventListener("submit", (event) => {
  event.preventDefault();
  void sendMessage(elements.messageInput.value);
});

elements.messageInput.addEventListener("input", resizeComposer);
elements.messageInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    if (!elements.sendButton.disabled) {
      elements.chatForm.requestSubmit();
    }
  }
});

elements.newSessionButton.addEventListener("click", startNewSession);
elements.clearActivityButton.addEventListener("click", resetActivity);
for (const button of elements.quickActions) {
  button.addEventListener("click", () => {
    const prompt = button.dataset.prompt;
    if (prompt) {
      void sendMessage(prompt);
    }
  });
}

async function initialize() {
  updateSessionLabel();
  resizeComposer();
  const online = await checkHealth();
  if (online) {
    await restoreTranscript();
  }
  window.setInterval(() => void checkHealth(), 30000);
}

void initialize();
