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
};

const AUTH_KEY = "gohanpass_web_validator_auth";
const RUN_STATE_KEY = "gohanpass_web_validator_run_state";

function isAuthenticated() {
  return window.sessionStorage.getItem(AUTH_KEY) === "qa";
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

    label.className = "scenario";

    label.innerHTML = `
      <input
        type="checkbox"
        data-scenario
        value="${escapeHtml(scenario.name)}"
        ${selectedSet.has(scenario.name) ? "checked" : ""}
      />
      <span>${escapeHtml(scenario.name)}</span>
      <small>${escapeHtml(scenario.type || "WEB")}</small>
    `;

    list.appendChild(label);
  }

  list.querySelectorAll("[data-scenario]").forEach((checkbox) => {
    checkbox.addEventListener("change", updateScenarioSummary);
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

  const summary = {
    total: state.activeRun.summary?.total || 0,
    pass: state.activeRun.summary?.pass || 0,
    fail: state.activeRun.summary?.fail || 0,
    na: state.activeRun.summary?.na || 0,
    error: Math.max(1, Number(state.activeRun.summary?.error || 0)),
  };

  state.activeRun = {
    ...state.activeRun,
    status: "failed",
    summary,
    finished_at: new Date().toISOString(),
    progress: {
      ...(state.activeRun.progress || {}),
      percent: 100,
      label: "서버 재시작 또는 실행 중단 감지",
    },
    logs: [
      ...(state.activeRun.logs || []),
      "⚠️ 서버 재시작 또는 실행 프로세스 중단으로 실행 상태를 더 이상 확인할 수 없습니다.",
    ],
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
  const serverRuns = runData.runs || [];
  const activeMissing =
    state.activeRun?.status === "running" &&
    !serverRuns.some((run) => run.id === state.activeRun.id);

  if (activeMissing) {
    markActiveRunMissingFromServer();
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

function handleLogin(event) {
  event.preventDefault();

  const id =
    document.querySelector("#loginId").value.trim();

  const password =
    document.querySelector("#loginPassword").value;

  const error =
    document.querySelector("#loginError");

  if (id === "qa" && password === "qa") {
    window.sessionStorage.setItem(AUTH_KEY, "qa");

    error.hidden = true;

    document.querySelector("#loginForm").reset();

    showApp();

    return;
  }

  error.hidden = false;

  document.querySelector("#loginPassword").select();
}

function logout() {
  window.sessionStorage.removeItem(AUTH_KEY);
  window.sessionStorage.removeItem(RUN_STATE_KEY);

  setPolling(false);

  showLoginAfterIntro();
}

document
  .querySelector("#loginForm")
  .addEventListener("submit", handleLogin);

document
  .querySelector("#logoutBtn")
  .addEventListener("click", logout);

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
  .querySelector("#refreshBtn")
  .addEventListener("click", refresh);

window.localStorage.removeItem(AUTH_KEY);

if (isAuthenticated()) {
  loadRunState();
  showApp();
} else {
  showLoginAfterIntro();
}
