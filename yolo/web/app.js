const form = document.querySelector("#settings-form");
const statusElement = document.querySelector("#status");
const targetClassSelect = document.querySelector("#targetClass");
const queueTargetSelect = document.querySelector("#queueTarget");
const targetBadge = document.querySelector("#target-badge");
const queueBadge = document.querySelector("#queue-badge");
const singlePanel = document.querySelector("#single-panel");
const queuePanel = document.querySelector("#queue-panel");
const queueList = document.querySelector("#queue-list");
const addQueueTargetButton = document.querySelector("#add-queue-target");
const startQueueButton = document.querySelector("#start-queue");
const stopQueueButton = document.querySelector("#stop-queue");
const connectionCard = document.querySelector("#connection-card");
const connectionTitle = document.querySelector("#connection-title");
const connectionDetail = document.querySelector("#connection-detail");

let sendTimer;
let availableClasses = [];
let queueTargets = [];
let queueActive = false;

function toLabel(value) {
  return value
    .split(" ")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function selectedMode() {
  return form.controlMode.value;
}

function setStatus(message, isError = false) {
  statusElement.textContent = message;
  statusElement.classList.toggle("error", isError);
}

function setTargetBadge(value) {
  targetBadge.textContent = value ? toLabel(value) : "--";
}

function populateSelect(select, classes, selectedClass) {
  select.innerHTML = "";
  for (const item of classes) {
    const option = document.createElement("option");
    option.value = item;
    option.textContent = toLabel(item);
    option.selected = item === selectedClass;
    select.appendChild(option);
  }
}

function populateClasses(classes, selectedClass) {
  availableClasses = classes;
  populateSelect(targetClassSelect, classes, selectedClass);
  populateSelect(queueTargetSelect, classes, selectedClass);
}

function renderMode() {
  const queueMode = selectedMode() === "queue";
  singlePanel.hidden = queueMode;
  queuePanel.hidden = !queueMode;
  targetBadge.hidden = queueMode;
  queueBadge.hidden = !queueMode;
  targetClassSelect.disabled = queueMode;
  queueTargetSelect.disabled = !queueMode || queueActive;
  addQueueTargetButton.disabled = !queueMode || queueActive;
  startQueueButton.disabled = !queueMode || queueTargets.length === 0 || queueActive;
  stopQueueButton.disabled = !queueMode || !queueActive;
}

function renderQueueList() {
  queueList.innerHTML = "";

  if (queueTargets.length === 0) {
    const empty = document.createElement("p");
    empty.className = "queue-empty";
    empty.textContent = "No queued objects.";
    queueList.appendChild(empty);
  } else {
    queueTargets.forEach((target, index) => {
      const item = document.createElement("div");
      item.className = "queue-item";

      const name = document.createElement("span");
      name.textContent = `${index + 1}. ${toLabel(target)}`;

      const removeButton = document.createElement("button");
      removeButton.type = "button";
      removeButton.textContent = "Remove";
      removeButton.disabled = queueActive;
      removeButton.addEventListener("click", () => {
        queueTargets.splice(index, 1);
        renderQueueList();
        sendSettings();
      });

      item.append(name, removeButton);
      queueList.appendChild(item);
    });
  }

  startQueueButton.disabled =
    selectedMode() !== "queue" || queueTargets.length === 0 || queueActive;
  stopQueueButton.disabled = selectedMode() !== "queue" || !queueActive;
  addQueueTargetButton.disabled = selectedMode() !== "queue" || queueActive;
  queueTargetSelect.disabled = selectedMode() !== "queue" || queueActive;
  queueBadge.textContent = queueActive
    ? `Queue running · ${queueTargets.length}`
    : `Queue ready · ${queueTargets.length}`;
}

function showSettings(settings) {
  if (availableClasses.length > 0) {
    targetClassSelect.value = settings.targetClass;
    queueTargetSelect.value = settings.targetClass;
  }

  form.confidence.value = settings.confidence;
  document.querySelector("#confidence-value").value = settings.confidence.toFixed(2);

  form.controlMode.value = settings.controlMode || "single";
  queueTargets = Array.isArray(settings.queueTargets) ? [...settings.queueTargets] : [];
  queueActive = Boolean(settings.queueActive);

  setTargetBadge(settings.targetClass);
  renderMode();
  renderQueueList();
}

function readSettings(extra = {}) {
  return {
    controlMode: selectedMode(),
    targetClass: form.targetClass.value,
    confidence: Number(form.confidence.value),
    queueTargets,
    ...extra,
  };
}

async function loadClasses() {
  const response = await fetch("/api/classes", { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }
  const data = await response.json();
  populateClasses(data.classes, targetClassSelect.value);
}

async function loadSettings() {
  try {
    await loadClasses();
    const response = await fetch("/api/settings", { cache: "no-store" });
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    showSettings(await response.json());
    setStatus("Settings loaded.");
  } catch (error) {
    setStatus(`Cannot reach web server: ${error.message}`, true);
  }
}

async function postSettings(extra = {}) {
  const response = await fetch("/api/settings", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(readSettings(extra)),
  });
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.error || `HTTP ${response.status}`);
  }
  showSettings(data);
  return data;
}

async function sendSettings() {
  try {
    await postSettings();
    setStatus("Settings saved.");
  } catch (error) {
    setStatus(`Update failed: ${error.message}`, true);
  }
}

function scheduleSettings() {
  setTargetBadge(form.targetClass.value);
  document.querySelector("#confidence-value").value = Number(form.confidence.value).toFixed(2);
  setStatus("Applying...");
  clearTimeout(sendTimer);
  sendTimer = setTimeout(sendSettings, 120);
}

async function startQueue() {
  try {
    await postSettings({
      controlMode: "queue",
      queueAction: "start",
    });
    setStatus("Queue started.");
  } catch (error) {
    setStatus(`Queue start failed: ${error.message}`, true);
  }
}

async function stopQueue() {
  try {
    await postSettings({
      controlMode: "queue",
      queueAction: "stop",
    });
    setStatus("Queue stopped.");
  } catch (error) {
    setStatus(`Queue stop failed: ${error.message}`, true);
  }
}

async function loadConnectionStatus() {
  try {
    const response = await fetch("/api/status", { cache: "no-store" });
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const status = await response.json();
    connectionCard.classList.toggle("connected", status.visionConnected);
    connectionCard.classList.toggle("disconnected", !status.visionConnected);

    if (status.visionConnected) {
      connectionTitle.textContent = "YOLO connected";
      const command = status.command ? `Command ${status.command}` : "No command yet";
      const fps = Number.isFinite(status.fps) ? `${status.fps} FPS` : "FPS --";
      const confidence = Number.isFinite(status.confidence)
        ? `conf ${status.confidence.toFixed(2)}`
        : "conf --";
      const area = Number.isFinite(status.candidateArea)
        ? `area ${status.candidateArea}`
        : "area --";
      const state = status.detectionState || "UNKNOWN";
      const target = status.targetClass ? toLabel(status.targetClass) : "--";
      const queueInfo =
        status.controlMode === "queue" && Number.isFinite(status.queueTotal)
          ? `queue ${Math.min(status.queueIndex + 1, status.queueTotal)}/${status.queueTotal}`
          : "single";
      connectionDetail.textContent =
        `${target} · ${queueInfo} · ${command} · ${state} · ${fps} · ${confidence} · ${area}`;
    } else {
      connectionTitle.textContent = "YOLO disconnected";
      connectionDetail.textContent =
        status.lastSeenSeconds === null
          ? "Waiting for the detector process..."
          : `Last heartbeat ${status.lastSeenSeconds}s ago`;
    }
  } catch (error) {
    connectionCard.classList.remove("connected");
    connectionCard.classList.add("disconnected");
    connectionTitle.textContent = "Web server unavailable";
    connectionDetail.textContent = error.message;
  }
}

form.addEventListener("input", (event) => {
  if (event.target.name === "queueTarget") {
    return;
  }
  if (event.target.name === "controlMode") {
    renderMode();
  }
  scheduleSettings();
});

addQueueTargetButton.addEventListener("click", () => {
  const target = queueTargetSelect.value;
  if (!target || queueTargets.includes(target)) {
    return;
  }
  queueTargets.push(target);
  renderQueueList();
  sendSettings();
});

startQueueButton.addEventListener("click", startQueue);
stopQueueButton.addEventListener("click", stopQueue);

loadSettings();
loadConnectionStatus();
setInterval(loadConnectionStatus, 1000);
