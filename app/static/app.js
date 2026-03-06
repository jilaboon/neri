const screens = {
  launcher: document.getElementById("launcher-screen"),
  bert: document.getElementById("bert-screen"),
  execution: document.getElementById("execution-screen"),
  system: document.getElementById("system-screen"),
};

const projectSelect = document.getElementById("project-select");
const projectName = document.getElementById("project-name");
const projectDut = document.getElementById("project-dut");
const saveProjectBtn = document.getElementById("save-project");
const loadProjectBtn = document.getElementById("load-project");
const newProjectBtn = document.getElementById("new-project");
const topologyFileInput = document.getElementById("topology-file");
const importTopologyBtn = document.getElementById("import-topology-btn");
const topologySummary = document.getElementById("topology-summary");

const connectBtn = document.getElementById("connect-btn");
const disconnectBtn = document.getElementById("disconnect-btn");
const resetBtn = document.getElementById("reset-btn");
const bertMap = document.getElementById("bert-map");
const execMap = document.getElementById("exec-map");
const bertStatus = document.getElementById("bert-status");
const execStatus = document.getElementById("exec-status");
const bertLog = document.getElementById("bert-log");
const execLog = document.getElementById("exec-log");

const runBtn = document.getElementById("run-btn");
const runState = document.getElementById("run-state");
const runTimer = document.getElementById("run-timer");
const dutSerial = document.getElementById("dut-serial");
const testNotes = document.getElementById("test-notes");

const laneTable = document.getElementById("lane-table");

let selectedProjectId = null;
let selectedProject = null;
let currentRunId = null;
let elapsedTimer = null;
let elapsedSec = 0;
const mapZoom = { "bert-map": 1, "exec-map": 1 };

function setTopologySummary(p) {
  if (!p) {
    topologySummary.textContent = "Topology: not loaded";
    return;
  }
  topologySummary.textContent =
    `Topology: trays=${p.trays}, bports/tray=${p.bports_per_tray}, lanes/bport=${p.lanes_per_bport}`;
}

function setClock() {
  const now = new Date();
  document.getElementById("clock").textContent = now.toLocaleTimeString();
}
setInterval(setClock, 1000);
setClock();

for (let i = 0; i < 24; i += 1) {
  const tr = document.createElement("tr");
  tr.innerHTML = "<td></td>".repeat(14);
  laneTable.appendChild(tr);
}

function logTo(target, line) {
  target.textContent += `${new Date().toLocaleTimeString()} ${line}\n`;
  target.scrollTop = target.scrollHeight;
}

function showScreen(screenId) {
  Object.values(screens).forEach((s) => s.classList.remove("active"));
  document.getElementById(screenId).classList.add("active");
}

document.querySelectorAll(".mode-btn").forEach((btn) => {
  btn.addEventListener("click", () => showScreen(btn.dataset.target));
});
document.querySelectorAll(".back-btn").forEach((btn) => {
  btn.addEventListener("click", () => showScreen(btn.dataset.target));
});
document.querySelectorAll(".map-zoom-in").forEach((btn) => {
  btn.addEventListener("click", () => {
    const mapId = btn.dataset.map;
    mapZoom[mapId] = Math.min(3, (mapZoom[mapId] || 1) + 0.25);
    applyMapZoom(mapId);
  });
});
document.querySelectorAll(".map-zoom-out").forEach((btn) => {
  btn.addEventListener("click", () => {
    const mapId = btn.dataset.map;
    mapZoom[mapId] = Math.max(0.5, (mapZoom[mapId] || 1) - 0.25);
    applyMapZoom(mapId);
  });
});
document.querySelectorAll(".map-zoom-reset").forEach((btn) => {
  btn.addEventListener("click", () => {
    const mapId = btn.dataset.map;
    mapZoom[mapId] = 1;
    applyMapZoom(mapId);
  });
});

async function api(path, options = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    throw new Error(await res.text());
  }
  return res.json();
}

function statusClass(s) {
  if (s === "passed" || s === "pass") return "pass";
  if (s === "failed" || s === "fail") return "fail";
  if (s === "error") return "error";
  if (s === "connected") return "connected";
  if (s === "not_defined") return "not_defined";
  return "not_connected";
}

function updateStatusPill(el, text, state) {
  el.textContent = text;
  const bg = {
    connecting: "#d3d3d3",
    running: "#dbe700",
    passed: "#63d913",
    failed: "#ff1515",
    error: "#f5ad00",
    connected: "#ddd900",
    status: "#e7a807",
  };
  el.style.background = bg[state] || "#e7a807";
}

function renderMap(container, lanes = []) {
  container.innerHTML = "";

  const useBportSummary = lanes.length > 400;
  const cells = [];

  if (useBportSummary) {
    const grouped = new Map();
    for (const lane of lanes) {
      const key = `${lane.tray}-${lane.bport}`;
      const existing = grouped.get(key) || { tray: lane.tray, bport: lane.bport, statuses: [] };
      existing.statuses.push(lane.status);
      grouped.set(key, existing);
    }

    const summarize = (statuses) => {
      if (statuses.some((s) => s === "error" || s === "not_connected")) return "error";
      if (statuses.some((s) => s === "fail" || s === "failed")) return "fail";
      if (statuses.length > 0 && statuses.every((s) => s === "pass" || s === "passed")) return "pass";
      if (statuses.some((s) => s === "connected")) return "connected";
      return "not_connected";
    };

    const ordered = [...grouped.values()].sort((a, b) => (a.tray - b.tray) || (a.bport - b.bport));
    for (const g of ordered) {
      cells.push({
        status: summarize(g.statuses),
        title: `T${g.tray} P${g.bport}`,
        label: `T${g.tray}/P${g.bport}`,
      });
    }
    const cols = Math.max(1, Math.min(8, Math.max(...ordered.map((x) => x.bport))));
    container.style.gridTemplateColumns = `repeat(${cols}, var(--map-cell-size))`;
  } else {
    for (const lane of lanes) {
      cells.push({
        status: statusClass(lane.status),
        title: `T${lane.tray} P${lane.bport} L${lane.lane} ${lane.status}`,
        label: "",
      });
    }
    container.style.gridTemplateColumns = "repeat(8, var(--map-cell-size))";
  }

  const renderCount = Math.max(64, cells.length);
  for (let i = 0; i < renderCount; i += 1) {
    const cell = cells[i];
    const d = document.createElement("div");
    d.className = `map-cell ${cell ? cell.status : ""}`;
    if (cell) {
      d.title = cell.title;
      d.textContent = cell.label;
    }
    container.appendChild(d);
  }
}

function applyMapZoom(mapId) {
  const mapEl = document.getElementById(mapId);
  if (!mapEl) return;
  const z = mapZoom[mapId] || 1;
  const sizePx = Math.round(38 * z);
  mapEl.style.setProperty("--map-cell-size", `${sizePx}px`);
}

function renderTopologyPreview(project) {
  if (!project) return;
  const cells = [];
  for (let tray = 1; tray <= project.trays; tray += 1) {
    for (let bport = 1; bport <= project.bports_per_tray; bport += 1) {
      cells.push({
        status: "not_defined",
        title: `Tray ${tray}, BPort ${bport}`,
        label: `T${tray}/P${bport}`,
      });
    }
  }

  const renderIn = [bertMap, execMap];
  for (const container of renderIn) {
    container.innerHTML = "";
    container.style.gridTemplateColumns = `repeat(${Math.max(1, Math.min(8, project.bports_per_tray))}, var(--map-cell-size))`;
    for (const cell of cells) {
      const d = document.createElement("div");
      d.className = `map-cell ${cell.status}`;
      d.title = cell.title;
      d.textContent = cell.label;
      container.appendChild(d);
    }
  }
}

function hhmmss(sec) {
  const h = String(Math.floor(sec / 3600)).padStart(2, "0");
  const m = String(Math.floor((sec % 3600) / 60)).padStart(2, "0");
  const s = String(sec % 60).padStart(2, "0");
  return `${h}:${m}:${s}`;
}

function setRunState(text, cls) {
  runState.className = `run-state ${cls}`;
  runState.textContent = text;
}

function renderFlowCards(activeState, timeValue) {
  const flowCards = document.getElementById("flow-cards");
  if (!flowCards) return;
  const cardStates = [
    { key: "testing", label: "Testing" },
    { key: "passed", label: "Pass" },
    { key: "failed", label: "Fail" },
    { key: "connecting", label: "Connecting" },
    { key: "error", label: "Error" },
  ];

  flowCards.innerHTML = cardStates.map((c) => {
    const text = c.label === "Pass" ? "PASS" : c.label;
    const cls = c.key;
    const fill = activeState === cls ? cls : "connecting";
    return `
      <div class="flow-card">
        <div>${c.label}</div>
        <div class="state ${fill}">${text}</div>
        <div class="flow-time">${timeValue}</div>
      </div>`;
  }).join("");
}

async function loadProjects() {
  const projects = await api("/api/projects");
  projectSelect.innerHTML = "";
  projects.forEach((p) => {
    const op = document.createElement("option");
    op.value = String(p.id);
    op.textContent = `#${p.id} ${p.name}`;
    projectSelect.appendChild(op);
  });
  if (projects.length > 0) {
    selectedProjectId = projects[0].id;
    projectSelect.value = String(selectedProjectId);
    selectedProject = projects[0];
    setTopologySummary(selectedProject);
    renderTopologyPreview(selectedProject);
  } else {
    setTopologySummary(null);
    selectedProject = null;
  }
}

async function refreshSelectedProject() {
  if (!selectedProjectId) return;
  const p = await api(`/api/projects/${selectedProjectId}`);
  selectedProject = p;
  setTopologySummary(p);
  renderTopologyPreview(p);
}

saveProjectBtn.addEventListener("click", async () => {
  const name = projectName.value.trim();
  if (!name) {
    alert("Enter project name");
    return;
  }
  const payload = {
    name,
    dut_profile: projectDut.value || "reference-dut",
    trays: 1,
    bports_per_tray: 1,
    lanes_per_bport: 1,
  };
  try {
    const p = await api("/api/projects", { method: "POST", body: JSON.stringify(payload) });
    selectedProjectId = p.id;
    await loadProjects();
    projectSelect.value = String(selectedProjectId);
    logTo(bertLog, `Project saved #${selectedProjectId} ${name}`);
  } catch (e) {
    alert(`Save failed: ${e.message}`);
  }
});

loadProjectBtn.addEventListener("click", () => {
  selectedProjectId = Number(projectSelect.value);
  refreshSelectedProject();
  logTo(bertLog, `Project loaded #${selectedProjectId}`);
});

newProjectBtn.addEventListener("click", () => {
  projectName.value = "";
  projectDut.value = "reference-dut";
});

projectSelect.addEventListener("change", () => {
  selectedProjectId = Number(projectSelect.value);
  refreshSelectedProject();
});

importTopologyBtn.addEventListener("click", async () => {
  if (!selectedProjectId) {
    alert("Create or load a project first");
    return;
  }
  const file = topologyFileInput.files && topologyFileInput.files[0];
  if (!file) {
    alert("Select a topology file (.json or .csv)");
    return;
  }

  const body = new FormData();
  body.append("file", file);
  try {
    const res = await fetch(`/api/projects/${selectedProjectId}/topology`, {
      method: "POST",
      body,
    });
    if (!res.ok) throw new Error(await res.text());
    const data = await res.json();
    const p = data.project;
    selectedProject = p;
    setTopologySummary(p);
    renderTopologyPreview(p);
    logTo(
      bertLog,
      `Topology imported: trays=${p.trays}, bports/tray=${p.bports_per_tray}, lanes/bport=${p.lanes_per_bport}`,
    );
    alert("Topology imported successfully");
  } catch (e) {
    logTo(bertLog, `Topology import failed: ${e.message}`);
    alert(`Topology import failed: ${e.message}`);
  }
});

connectBtn.addEventListener("click", async () => {
  if (!selectedProjectId) {
    alert("Create or load a project first");
    return;
  }
  updateStatusPill(bertStatus, "Connecting", "connecting");
  try {
    const res = await api(`/api/connect/${selectedProjectId}`, { method: "POST" });
    renderMap(bertMap, res.lanes);
    renderMap(execMap, res.lanes);
    updateStatusPill(bertStatus, "Connected", "connected");
    updateStatusPill(execStatus, "Connected", "connected");
    logTo(bertLog, `Connected ${res.connected_lanes}/${res.total_lanes} lanes`);
  } catch (e) {
    updateStatusPill(bertStatus, "Error", "error");
    logTo(bertLog, `Connect failed: ${e.message}`);
  }
});

disconnectBtn.addEventListener("click", () => {
  renderTopologyPreview(selectedProject);
  updateStatusPill(bertStatus, "Status", "status");
  updateStatusPill(execStatus, "Status", "status");
  logTo(bertLog, "Disconnected");
});

resetBtn.addEventListener("click", () => {
  bertLog.textContent = "";
  execLog.textContent = "";
  setRunState("RUN", "neutral");
  runTimer.textContent = "00:00:00";
});

function startElapsedTimer() {
  stopElapsedTimer();
  elapsedSec = 0;
  runTimer.textContent = hhmmss(elapsedSec);
  elapsedTimer = setInterval(() => {
    elapsedSec += 1;
    runTimer.textContent = hhmmss(elapsedSec);
  }, 1000);
}

function stopElapsedTimer() {
  if (elapsedTimer) {
    clearInterval(elapsedTimer);
    elapsedTimer = null;
  }
}

async function pollRun(runId) {
  const run = await api(`/api/tests/${runId}`);
  renderMap(execMap, run.lanes || []);
  renderMap(bertMap, run.lanes || []);

  if (run.status === "running") {
    setRunState("Testing...", "testing");
    updateStatusPill(execStatus, "Testing", "running");
    setTimeout(() => pollRun(runId), 1000);
    return;
  }

  stopElapsedTimer();
  if (run.status === "passed") {
    setRunState("PASS", "passed");
    updateStatusPill(execStatus, "Passed", "passed");
  } else if (run.status === "failed") {
    setRunState("Fail", "failed");
    updateStatusPill(execStatus, "Fail", "failed");
  } else {
    setRunState("Error", "error");
    updateStatusPill(execStatus, "Error", "error");
  }
  logTo(execLog, `Run #${runId} done. pass=${run.pass_count || 0} fail=${run.fail_count || 0} error=${run.error_count || 0}`);
}

runBtn.addEventListener("click", async () => {
  if (!selectedProjectId) {
    alert("Create or load a project first");
    return;
  }
  showScreen("execution-screen");
  setRunState("Connecting...", "connecting");
  updateStatusPill(execStatus, "Connecting", "connecting");

  try {
    const serial = dutSerial.value.trim() || `SN-${Date.now()}`;
    const run = await api("/api/tests/start", {
      method: "POST",
      body: JSON.stringify({
        project_id: selectedProjectId,
        dut_serial: serial,
        prbs_type: "PRBS31",
        duration_sec: 10,
        notes: testNotes.value || "",
      }),
    });

    currentRunId = run.run_id;
    startElapsedTimer();
    setRunState("Testing...", "testing");
    updateStatusPill(execStatus, "Testing", "running");
    logTo(execLog, `Run #${currentRunId} started for ${serial}`);
    pollRun(currentRunId);
  } catch (e) {
    setRunState("Error", "error");
    updateStatusPill(execStatus, "Error", "error");
    logTo(execLog, `Run start failed: ${e.message}`);
  }
});

(async function init() {
  await loadProjects();
  await refreshSelectedProject();
  renderTopologyPreview(selectedProject);
  applyMapZoom("bert-map");
  applyMapZoom("exec-map");
})();
