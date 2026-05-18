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
};

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text);
  }
  return response.json();
}

function selectedScenarios() {
  return Array.from(document.querySelectorAll("[data-scenario]:checked")).map((item) => item.value);
}

function renderScenarios() {
  const list = document.querySelector("#scenarioList");
  list.innerHTML = "";
  for (const scenario of state.scenarios) {
    const label = document.createElement("label");
    label.className = "scenario";
    label.innerHTML = `<input type="checkbox" data-scenario value="${scenario.name}"><span>${scenario.name}</span>`;
    list.appendChild(label);
  }
}

function renderDays(selected = []) {
  const days = document.querySelector("#days");
  days.innerHTML = "";
  for (const [value, label] of dayLabels) {
    const item = document.createElement("label");
    item.className = "day";
    item.innerHTML = `<input type="checkbox" data-day value="${value}" ${selected.includes(value) ? "checked" : ""}> ${label}`;
    days.appendChild(item);
  }
}

function applyScheduleToForm(schedule) {
  document.querySelector("#scheduleEnabled").checked = schedule.enabled;
  document.querySelector("#scheduleTime").value = schedule.time || "09:00";
  document.querySelector("#notionUpload").checked = schedule.notion_upload !== false;
  renderDays(schedule.days || []);

  for (const checkbox of document.querySelectorAll("[data-scenario]")) {
    checkbox.checked = Boolean(schedule.scenarios?.length && schedule.scenarios.includes(checkbox.value));
  }

  document.querySelector("#scheduleState").textContent = schedule.enabled
    ? `스케줄 활성: ${schedule.time}`
    : "스케줄 비활성";
}

function renderRuns(runs) {
  const target = document.querySelector("#runs");
  target.innerHTML = "";
  if (!runs.length) {
    target.innerHTML = `<p class="copy">아직 실행 기록이 없습니다.</p>`;
    return;
  }

  for (const run of runs) {
    const item = document.createElement("div");
    item.className = `run ${run.status === "running" ? "live" : ""}`;
    const logs = (run.logs || []).slice(-18).join("\n");
    const latestSnapshot = (run.snapshots || []).slice(-1)[0] || "";
    item.innerHTML = `
      <div>
        <strong>${run.id}</strong>
        <p class="copy">${run.started_at || ""}</p>
      </div>
      <div>
        <span class="badge ${run.status}">${run.status}</span>
        <p class="copy">Total ${run.summary?.total || 0} / PASS ${run.summary?.pass || 0} / FAIL ${run.summary?.fail || 0} / N/A ${run.summary?.na || 0}</p>
        ${latestSnapshot ? `<a class="snapshot-link" href="${latestSnapshot}" target="_blank" rel="noreferrer"><img class="snapshot" src="${latestSnapshot}" alt="latest snapshot" /></a>` : ""}
        <pre>${logs}</pre>
      </div>
      <div>${run.notion?.uploaded ? "Notion 등록" : ""}</div>
    `;
    target.appendChild(item);
  }
}

function updateScheduleStateText(run, schedule) {
  const target = document.querySelector("#scheduleState");
  if (run?.status === "running") {
    target.textContent = `실행중: ${run.id}`;
    target.classList.add("live");
    return;
  }

  target.classList.remove("live");
  target.textContent = schedule?.enabled ? `스케줄 활성: ${schedule.time}` : "스케줄 비활성";
}

function setPolling(enabled) {
  if (enabled) {
    if (!state.refreshTimer) {
      state.refreshTimer = window.setInterval(() => {
        refresh().catch(() => {});
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
  const [scenarioData, schedule, runData] = await Promise.all([
    api("/api/scenarios"),
    api("/api/schedule"),
    api("/api/runs"),
  ]);
  state.scenarios = scenarioData.scenarios;
  state.schedule = schedule;
  renderScenarios();
  applyScheduleToForm(schedule);
  renderRuns(runData.runs);
  const runningRun = runData.runs.find((run) => run.status === "running");
  updateScheduleStateText(runningRun, schedule);
  setPolling(Boolean(runningRun));
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
        notion_upload: document.querySelector("#notionUpload").checked,
      }),
    });
    if (run?.id) {
      updateScheduleStateText(run, state.schedule);
      setPolling(true);
    }
    await refresh();
  } finally {
    button.disabled = false;
    button.textContent = "즉시 실행";
  }
}

async function saveSchedule() {
  const days = Array.from(document.querySelectorAll("[data-day]:checked")).map((item) => item.value);
  const schedule = {
    enabled: document.querySelector("#scheduleEnabled").checked,
    time: document.querySelector("#scheduleTime").value || "09:00",
    days,
    scenarios: selectedScenarios(),
    notion_upload: document.querySelector("#notionUpload").checked,
  };
  await api("/api/schedule", { method: "POST", body: JSON.stringify(schedule) });
  await refresh();
}

document.querySelector("#runBtn").addEventListener("click", runNow);
document.querySelector("#saveScheduleBtn").addEventListener("click", saveSchedule);
document.querySelector("#refreshBtn").addEventListener("click", refresh);

refresh().catch((error) => {
  document.querySelector("#runs").innerHTML = `<pre>${error.message}</pre>`;
});
