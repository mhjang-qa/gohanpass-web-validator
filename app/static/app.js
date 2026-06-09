const dayLabels = [
  ["mon", "월"],
  ["tue", "화"],
  ["wed", "수"],
  ["thu", "목"],
  ["fri", "금"],
  ["sat", "토"],
  ["sun", "일"],
];

const state = {
  scenarios: [],
  schedule: null,
  refreshTimer: null,
  activeRun: null,
  lastRuns: [],
  auth: null,
  allowedOrigin: "",
};

const AUTH_KEY = "gohanpass_web_validator_auth";
const RUN_STATE_KEY = "gohanpass_web_validator_run_state";
const CONSOLE_WINDOW_NAME = "qa-console-sso";

function selectedEnvironment() {
  return (
    document.querySelector("input[name='targetEnvironment']:checked")?.value ||
    "prod"
  );
}

function setEnvironment(value = "prod") {
  const normalized = value === "dev" ? "dev" : "prod";
  const input = document.querySelector(
    `input[name='targetEnvironment'][value='${normalized}']`
  );
  if (input) {
    input.checked = true;
  }
}

function nowSeconds() {
  return Math.floor(Date.now() / 1000);
}

function readCachedAuth() {
  const stored =
    window.localStorage.getItem(AUTH_KEY) ||
    window.sessionStorage.getItem(AUTH_KEY);

  if (!stored) {
    return null;
  }

  try {
    const parsed = JSON.parse(stored);
    if (!parsed?.exp || Number(parsed.exp) <= nowSeconds()) {
      clearCachedAuth();
      return null;
    }
    return parsed;
  } catch (_error) {
    clearCachedAuth();
    return null;
  }
}

function persistAuth(session) {
  state.auth = session;
  const value = JSON.stringify(session);
  window.localStorage.setItem(AUTH_KEY, value);
  window.sessionStorage.setItem(AUTH_KEY, value);
}

function clearCachedAuth() {
  state.auth = null;
  window.localStorage.removeItem(AUTH_KEY);
  window.sessionStorage.removeItem(AUTH_KEY);
}

function isEmbeddedFromConsole() {
  if (window.top === window.self) {
    return false;
  }
  return Boolean(
    state.allowedOrigin &&
      document.referrer &&
      document.referrer.startsWith(state.allowedOrigin)
  );
}

function isConsoleWindow() {
  return window.name === CONSOLE_WINDOW_NAME;
}

function isSessionUsable(session) {
  if (!session?.exp || Number(session.exp) <= nowSeconds()) {
    return false;
  }

  if (session.mode === "manual") {
    return true;
  }

  if (session.mode === "console") {
    return isEmbeddedFromConsole() || isConsoleWindow();
  }

  return false;
}

function isAuthenticated() {
  return isSessionUsable(state.auth);
}

function setScreen(screen) {
  document.body.dataset.screen = screen;
  document.querySelector("#loginScreen").hidden = screen !== "login";
  document.querySelector("#appShell").hidden = screen !== "app";
}

function showLoginAfterIntro() {
  setScreen("login");
  document.querySelector("#loginId").focus();
}

function showApp() {
  setScreen("app");
  refresh().catch((error) => {
    document.querySelector("#runs").innerHTML = `<pre>${escapeHtml(error.message)}</pre>`;
  });
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `API 요청 실패: ${response.status}`);
  }

  return response.json();
}

function showLoginMessage(message) {
  const error = document.querySelector("#loginError");
  if (!message) {
    error.hidden = true;
    error.textContent = "";
    return;
  }

  error.textContent = message;
  error.hidden = false;
}

function authErrorMessage(reason) {
  if (reason === "expired") {
    return "로그인이 만료되었습니다. 다시 로그인해주세요.";
  }
  if (reason === "invalid" || reason === "forbidden") {
    return "통합 콘솔 인증 검증에 실패했습니다. 다시 로그인해주세요.";
  }
  return "";
}

async function fetchRunById(runId) {
  if (!runId) return null;

  try {
    return await api(`/api/runs/${encodeURIComponent(runId)}`);
  } catch (error) {
    return null;
  }
}

function selectedScenarios() {
  return Array.from(
    document.querySelectorAll("[data-scenario]:checked")
  ).map((item) => item.value);
}

function setScenarioSelection(names = []) {
  const selected = new Set(names);

  for (const checkbox of document.querySelectorAll("[data-scenario]")) {
    checkbox.checked = selected.has(checkbox.value);
  }

  updateScenarioSummary();
}

function syncScheduleDetailsVisibility() {
  const enabled = document.querySelector("#scheduleEnabled").checked;
  const details = document.querySelector("#scheduleDetails");

  if (details) {
    details.hidden = !enabled;
  }
}

function updateScenarioSummary() {
  const summary = document.querySelector("#scenarioSummary");

  if (!summary) return;

  const selected = selectedScenarios();

  summary.textContent = selected.length
    ? `${selected.length}개 시나리오 선택됨`
    : "시나리오 선택";
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function loadRunState() {
  try {
    const saved = JSON.parse(
      window.sessionStorage.getItem(RUN_STATE_KEY) || "{}"
    );
    state.activeRun = saved.activeRun || null;
    state.lastRuns = Array.isArray(saved.lastRuns) ? saved.lastRuns : [];
  } catch {
    state.activeRun = null;
    state.lastRuns = [];
  }
}

function saveRunState() {
  window.sessionStorage.setItem(
    RUN_STATE_KEY,
    JSON.stringify({
      activeRun: state.activeRun,
      lastRuns: state.lastRuns.slice(0, 30),
    })
  );
}

function clearRunStateIfIdle() {
  if (state.activeRun?.status === "running") {
    return;
  }
  saveRunState();
}

function progressHtml(run) {
  if (run.status !== "running") {
    return "";
  }

  const progress = run.progress || {};

  const percent = Math.max(
    0,
    Math.min(100, Number(progress.percent || 0))
  );

  const current = Number(progress.current || 0);

  const total = Number(
    progress.total || run.requested_scenarios?.length || 0
  );

  const label = progress.label || "실행 중";

  const countText = total ? `${current}/${total}` : "진행 중";

  return `
    <div
      class="run-progress"
      role="progressbar"
      aria-valuemin="0"
      aria-valuemax="100"
      aria-valuenow="${percent}"
    >
      <div class="progress-meta">
        <span>${escapeHtml(label)}</span>
        <strong>${countText} · ${percent}%</strong>
      </div>

      <div class="progress-track">
        <div class="progress-fill" style="width:${percent}%"></div>
      </div>
    </div>
  `;
}

function renderScenarios(selected = []) {
  const list = document.querySelector("#scenarioList");

  if (!list) return;

  list.innerHTML = "";

  const selectedSet = new Set(selected);

  for (const scenario of state.scenarios) {
    const label = document.createElement("label");
    const selected = selectedSet.has(scenario.name);

    label.className = `scenario ${selected ? "selected" : ""}`;

    label.innerHTML = `
      <input
        type="checkbox"
        data-scenario
        value="${escapeHtml(scenario.name)}"
        ${selected ? "checked" : ""}
      />
      <span>${escapeHtml(scenario.name)}</span>
      <small>${escapeHtml(scenario.type || "WEB")}</small>
    `;

    list.appendChild(label);
  }

  list.querySelectorAll("[data-scenario]").forEach((checkbox) => {
    checkbox.addEventListener("change", () => {
      checkbox.closest(".scenario")?.classList.toggle("selected", checkbox.checked);
      updateScenarioSummary();
    });
  });

  updateScenarioSummary();
}

function renderDays(selected = []) {
  const days = document.querySelector("#days");

  days.innerHTML = "";

  for (const [value, label] of dayLabels) {
    const item = document.createElement("label");

    item.className = "day";

    item.innerHTML = `
      <input
        type="checkbox"
        data-day
        value="${value}"
        ${selected.includes(value) ? "checked" : ""}
      />
      ${label}
    `;

    days.appendChild(item);
  }
}

function applyScheduleToForm(schedule) {
  setEnvironment(schedule.target_environment || "prod");

  document.querySelector("#scheduleEnabled").checked =
    Boolean(schedule.enabled);

  syncScheduleDetailsVisibility();

  document.querySelector("#scheduleTime").value =
    schedule.time || "09:00";

  document.querySelector("#notionUpload").checked =
    schedule.notion_upload !== false;

  document.querySelector("#snapshotInterval").value =
    schedule.snapshot_interval_seconds || 30;

  renderDays(schedule.days || []);

  setScenarioSelection(schedule.scenarios || []);

  document.querySelector("#scheduleState").textContent =
    schedule.enabled
      ? `스케줄 활성: ${schedule.time}`
      : "스케줄 비활성";
}

function renderRuns(runs) {
  const target = document.querySelector("#runs");

  target.innerHTML = "";

  if (!runs.length) {
    target.innerHTML =
      `<p class="copy">아직 실행 기록이 없습니다.</p>`;
    return;
  }

  for (const run of runs) {
    const item = document.createElement("div");

    item.className =
      `run ${run.status === "running" ? "live" : ""}`;

    const logs = escapeHtml(
      (run.logs || []).slice(-18).join("\n")
    );

    const latestSnapshot =
      (run.snapshots || []).slice(-1)[0] || "";

    item.innerHTML = `
      <div>
        <strong>${escapeHtml(run.id)}</strong>
        <p class="copy">${escapeHtml(run.started_at || "")}</p>
      </div>

      <div>
        <span class="badge ${escapeHtml(run.status)}">
          ${escapeHtml(run.status)}
        </span>

        <p class="copy">
          Total ${run.summary?.total || 0}
          / PASS ${run.summary?.pass || 0}
          / FAIL ${run.summary?.fail || 0}
          / N/A ${run.summary?.na || 0}
          / ERROR ${run.summary?.error || 0}
        </p>

        ${progressHtml(run)}

        ${
          latestSnapshot
            ? `
          <a
            class="snapshot-link"
            href="${escapeHtml(latestSnapshot)}"
            target="_blank"
            rel="noreferrer"
          >
            <img
              class="snapshot"
              src="${escapeHtml(latestSnapshot)}"
              alt="latest snapshot"
            />
          </a>
        `
            : ""
        }

        <pre>${logs}</pre>
      </div>
    `;

    target.appendChild(item);
  }
}

function mergeRuns(serverRuns = []) {
  const merged = [];
  const seen = new Set();

  for (const run of serverRuns) {
    if (!run?.id) continue;
    merged.push(run);
    seen.add(run.id);
  }

  if (
    state.activeRun?.id &&
    !seen.has(state.activeRun.id)
  ) {
    merged.unshift(state.activeRun);
    seen.add(state.activeRun.id);
  }

  for (const run of state.lastRuns || []) {
    if (!run?.id || seen.has(run.id)) continue;
    merged.push(run);
    seen.add(run.id);
  }

  return merged;
}

function markActiveRunMissingFromServer() {
  if (!state.activeRun || state.activeRun.status !== "running") {
    return;
  }

  state.activeRun._serverMisses = Number(state.activeRun._serverMisses || 0) + 1;

  if (state.activeRun._serverMisses < 3) {
    return;
  }

  const logs = state.activeRun.logs || [];
  const message =
    "⚠️ 실행 상태가 목록 응답에서 잠시 누락되어 개별 상태를 재확인 중입니다.";

  state.activeRun = {
    ...state.activeRun,
    progress: {
      ...(state.activeRun.progress || {}),
      label: "실행 상태 재확인 중",
    },
    logs: logs.includes(message) ? logs : [...logs, message],
  };
}

function rememberRuns(runs = []) {
  state.lastRuns = runs.slice(0, 30);

  const runningRun = runs.find((run) => run.status === "running");
  if (runningRun) {
    state.activeRun = {...runningRun, _serverMisses: 0};
    saveRunState();
    return;
  }

  if (
    state.activeRun?.id &&
    runs.some((run) => run.id === state.activeRun.id)
  ) {
    state.activeRun = null;
  }

  clearRunStateIfIdle();
}

async function refreshRunsOnly() {
  if (!isAuthenticated()) {
    return;
  }

  const runData = await api("/api/runs");
  let serverRuns = runData.runs || [];
  let activeMissing =
    state.activeRun?.status === "running" &&
    !serverRuns.some((run) => run.id === state.activeRun.id);

  if (activeMissing) {
    const recoveredRun = await fetchRunById(state.activeRun.id);
    if (recoveredRun?.id) {
      serverRuns = [
        recoveredRun,
        ...serverRuns.filter((run) => run.id !== recoveredRun.id),
      ];
      state.activeRun = {...recoveredRun, _serverMisses: 0};
      activeMissing = false;
    } else {
      markActiveRunMissingFromServer();
    }
  }

  const runs = mergeRuns(serverRuns);
  const runningRun = runs.find((run) => run.status === "running");

  if (activeMissing) {
    state.lastRuns = runs.slice(0, 30);
  } else {
    rememberRuns(runs);
  }

  renderRuns(runs);
  updateScheduleStateText(runningRun, state.schedule);
  setPolling(Boolean(runningRun));
  saveRunState();
}

function updateScheduleStateText(run, schedule) {
  const target = document.querySelector("#scheduleState");

  if (run?.status === "running") {
    target.textContent = `실행중: ${run.id}`;
    target.classList.add("live");
    return;
  }

  target.classList.remove("live");

  target.textContent = schedule?.enabled
    ? `스케줄 활성: ${schedule.time}`
    : "스케줄 비활성";
}

function setPolling(enabled) {
  if (enabled) {
    if (!state.refreshTimer) {
      state.refreshTimer = window.setInterval(() => {
        refreshRunsOnly().catch(() => {});
      }, 2000);
    }

    return;
  }

  if (state.refreshTimer) {
    window.clearInterval(state.refreshTimer);
    state.refreshTimer = null;
  }
}

async function refresh() {
  if (!isAuthenticated()) {
    return;
  }

  const currentSelection = selectedScenarios();

  const [scenarioData, schedule, runData] =
    await Promise.all([
      api("/api/scenarios"),
      api("/api/schedule"),
      api("/api/runs"),
    ]);

  state.scenarios = scenarioData.scenarios || [];
  state.schedule = schedule;

  const runs = mergeRuns(runData.runs || []);

  const runningRun = runs.find(
    (run) => run.status === "running"
  );

  const runningSelection =
    runningRun?.requested_scenarios || [];

  const initialSelection = currentSelection.length
    ? currentSelection
    : (
        runningSelection.length
          ? runningSelection
          : (schedule.scenarios || [])
      );

  renderScenarios(initialSelection);

  applyScheduleToForm({
    ...schedule,
    scenarios: initialSelection,
  });

  if (runningSelection.length) {
    setScenarioSelection(runningSelection);
  }

  rememberRuns(runs);

  renderRuns(runs);

  updateScheduleStateText(runningRun, schedule);

  setPolling(Boolean(runningRun));
  saveRunState();
}

async function runNow() {
  const button = document.querySelector("#runBtn");

  button.disabled = true;
  button.textContent = "실행중";

  try {
    const run = await api("/api/runs", {
      method: "POST",
      body: JSON.stringify({
        scenarios: selectedScenarios(),
        target_environment: selectedEnvironment(),
        notion_upload:
          document.querySelector("#notionUpload").checked,
        snapshot_interval_seconds: Number(
          document.querySelector("#snapshotInterval").value || 30
        ),
      }),
    });

    if (run?.id) {
      state.activeRun = run;
      state.lastRuns = mergeRuns([run]);
      saveRunState();
      updateScheduleStateText(run, state.schedule);
      setPolling(true);
      renderRuns(mergeRuns([run]));
    }

    await refresh();
  } finally {
    button.disabled = false;
    button.textContent = "즉시 실행";
  }
}

async function saveSchedule() {
  const days = Array.from(
    document.querySelectorAll("[data-day]:checked")
  ).map((item) => item.value);

  const schedule = {
    enabled:
      document.querySelector("#scheduleEnabled").checked,

    time:
      document.querySelector("#scheduleTime").value || "09:00",

    days,

    scenarios: selectedScenarios(),
    target_environment: selectedEnvironment(),

    notion_upload:
      document.querySelector("#notionUpload").checked,

    snapshot_interval_seconds: Number(
      document.querySelector("#snapshotInterval").value || 30
    ),
  };

  await api("/api/schedule", {
    method: "POST",
    body: JSON.stringify(schedule),
  });

  await refresh();
}

async function handleLogin(event) {
  event.preventDefault();

  const id =
    document.querySelector("#loginId").value.trim();

  const password =
    document.querySelector("#loginPassword").value;

  const error =
    document.querySelector("#loginError");

  try {
    const result = await api("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({
        username: id,
        password,
      }),
    });
    persistAuth(result.session);
    error.hidden = true;
    document.querySelector("#loginForm").reset();
    showApp();
    return;
  } catch (_requestError) {
    error.textContent = "ID 또는 Password가 올바르지 않습니다.";
    error.hidden = false;
  }

  document.querySelector("#loginPassword").select();
}

async function logout() {
  try {
    await api("/api/auth/logout", { method: "POST" });
  } catch (_requestError) {}

  clearCachedAuth();
  window.sessionStorage.removeItem(RUN_STATE_KEY);
  window.name = "";

  setPolling(false);

  showLoginMessage("");
  showLoginAfterIntro();
}

document
  .querySelector("#loginForm")
  .addEventListener("submit", handleLogin);

document
  .querySelector("#logoutBtn")
  .addEventListener("click", () => {
    logout().catch(() => {
      showLoginAfterIntro();
    });
  });

document
  .querySelector("#runBtn")
  .addEventListener("click", runNow);

document
  .querySelector("#saveScheduleBtn")
  .addEventListener("click", saveSchedule);

document
  .querySelector("#scheduleEnabled")
  .addEventListener("change", syncScheduleDetailsVisibility);

document
  .querySelectorAll("input[name='targetEnvironment']")
  .forEach((input) => {
    input.addEventListener("change", () => {
      if (state.schedule) {
        state.schedule = {
          ...state.schedule,
          target_environment: selectedEnvironment(),
        };
      }
    });
  });

document
  .querySelector("#refreshBtn")
  .addEventListener("click", refresh);

async function bootstrapAuth() {
  let bootstrap = {
    authenticated: false,
    session: null,
    allowedOrigin: "",
    reason: null,
  };

  try {
    bootstrap = await api("/api/auth/bootstrap");
  } catch (_requestError) {}

  state.allowedOrigin = bootstrap.allowedOrigin || "";

  const authError = new URLSearchParams(window.location.search).get("auth_error");
  const errorMessage = authErrorMessage(authError || bootstrap.reason);

  if (bootstrap.session) {
    persistAuth(bootstrap.session);
  } else if (!bootstrap.authenticated && !bootstrap.reason) {
    const cached = readCachedAuth();
    if (cached) {
      state.auth = cached;
    }
  } else {
    clearCachedAuth();
  }

  if (!isAuthenticated()) {
    clearCachedAuth();
    setPolling(false);
    showLoginMessage(errorMessage);
    showLoginAfterIntro();
    return;
  }

  showLoginMessage("");
  loadRunState();
  showApp();
}

bootstrapAuth().catch(() => {
  showLoginMessage("");
  showLoginAfterIntro();
});
