const statusJson = document.getElementById("status-json");
const schemaJson = document.getElementById("schema-json");
const controlResult = document.getElementById("control-result");

const healthLevel = document.getElementById("health-level");
const healthDetail = document.getElementById("health-detail");
const wakeMode = document.getElementById("wake-mode");
const sleepState = document.getElementById("sleep-state");
const personaStyle = document.getElementById("persona-style");
const backchannelStyle = document.getElementById("backchannel-style");
const featureFlags = document.getElementById("feature-flags");
const operatorMode = document.getElementById("operator-mode");

const refreshButton = document.getElementById("refresh");
const stopButton = document.getElementById("stop-app");
const actionButtons = Array.from(document.querySelectorAll("[data-action]"));

function renderJson(target, payload) {
  target.textContent = JSON.stringify(payload, null, 2);
}

function statusLine(status, fallback = "Unavailable") {
  if (status === undefined || status === null || status === "") {
    return fallback;
  }
  return String(status);
}

function setBusy(button, busy) {
  button.disabled = busy;
}

function summarizeStatus(payload) {
  const health = payload.health || {};
  const voice = payload.voice || {};
  const operator = payload.operator || {};
  const controls = payload.operator_controls || {};
  const runtimeProfile = controls.runtime_profile || {};

  healthLevel.textContent = statusLine(health.health_level, "Unknown");
  healthDetail.textContent = Array.isArray(health.reasons) && health.reasons.length
    ? health.reasons.slice(0, 2).join(" | ")
    : "No health reasons reported.";

  wakeMode.textContent = statusLine(voice.mode || runtimeProfile.wake_mode, "Unknown");
  sleepState.textContent = `sleeping=${statusLine(voice.sleeping, "unknown")} | room=${statusLine(voice.active_room, "unknown")}`;

  personaStyle.textContent = statusLine(runtimeProfile.persona_style, "Unknown");
  backchannelStyle.textContent = `backchannel=${statusLine(runtimeProfile.backchannel_style, "unknown")}`;

  const flags = [
    `motion=${statusLine(runtimeProfile.motion_enabled, "unknown")}`,
    `tts=${statusLine(runtimeProfile.tts_enabled, "unknown")}`,
    `home=${statusLine(runtimeProfile.home_enabled, "unknown")}`,
  ];
  featureFlags.textContent = flags.join(" | ");
  operatorMode.textContent = `operator auth=${statusLine(operator.auth_mode, "n/a")} | enabled=${statusLine(operator.enabled, "n/a")}`;
}

async function fetchJson(path, options = {}) {
  const response = await fetch(path, {
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
    ...options,
  });

  const payload = await response.json().catch(() => ({
    ok: false,
    error: `Non-JSON response from ${path}`,
  }));

  if (!response.ok) {
    throw new Error(payload.detail || payload.message || `${path} failed with ${response.status}`);
  }

  return payload;
}

async function refreshStatus() {
  const [statusPayload, schemaPayload] = await Promise.all([
    fetchJson("/api/status"),
    fetchJson("/api/control-schema"),
  ]);

  renderJson(statusJson, statusPayload);
  renderJson(schemaJson, schemaPayload);
  summarizeStatus(statusPayload);
}

async function sendControl(action, payload) {
  const result = await fetchJson("/api/control", {
    method: "POST",
    body: JSON.stringify({ action, payload }),
  });
  renderJson(controlResult, result);
  await refreshStatus();
}

refreshButton.addEventListener("click", async () => {
  setBusy(refreshButton, true);
  try {
    await refreshStatus();
  } catch (error) {
    renderJson(controlResult, { ok: false, error: String(error) });
  } finally {
    setBusy(refreshButton, false);
  }
});

stopButton.addEventListener("click", async () => {
  setBusy(stopButton, true);
  try {
    const result = await fetchJson("/api/stop", { method: "POST" });
    renderJson(controlResult, result);
  } catch (error) {
    renderJson(controlResult, { ok: false, error: String(error) });
  } finally {
    setBusy(stopButton, false);
  }
});

actionButtons.forEach((button) => {
  button.addEventListener("click", async () => {
    const action = button.dataset.action || "";
    const payload = JSON.parse(button.dataset.payload || "{}");
    setBusy(button, true);
    try {
      await sendControl(action, payload);
    } catch (error) {
      renderJson(controlResult, { ok: false, error: String(error), action, payload });
    } finally {
      setBusy(button, false);
    }
  });
});

refreshStatus().catch((error) => {
  renderJson(controlResult, { ok: false, error: String(error) });
});
