const form = document.querySelector("#settings-form");
const statusElement = document.querySelector("#status");
const targetClassSelect = document.querySelector("#targetClass");
const targetBadge = document.querySelector("#target-badge");
const connectionCard = document.querySelector("#connection-card");
const connectionTitle = document.querySelector("#connection-title");
const connectionDetail = document.querySelector("#connection-detail");

let sendTimer;
let availableClasses = [];

function toLabel(value) {
  return value
    .split(" ")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function setTargetBadge(value) {
  targetBadge.textContent = value ? toLabel(value) : "--";
}

function populateClasses(classes, selectedClass) {
  availableClasses = classes;
  targetClassSelect.innerHTML = "";
  for (const item of classes) {
    const option = document.createElement("option");
    option.value = item;
    option.textContent = toLabel(item);
    option.selected = item === selectedClass;
    targetClassSelect.appendChild(option);
  }
}

function showSettings(settings) {
  if (availableClasses.length > 0) {
    targetClassSelect.value = settings.targetClass;
  }
  form.confidence.value = settings.confidence;
  document.querySelector("#confidence-value").value = settings.confidence.toFixed(2);
  setTargetBadge(settings.targetClass);
}

function readSettings() {
  return {
    targetClass: form.targetClass.value,
    confidence: Number(form.confidence.value),
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
    statusElement.textContent = "Settings loaded.";
    statusElement.classList.remove("error");
  } catch (error) {
    statusElement.textContent = `Cannot reach web server: ${error.message}`;
    statusElement.classList.add("error");
  }
}

async function sendSettings() {
  try {
    const response = await fetch("/api/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(readSettings()),
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || `HTTP ${response.status}`);
    }
    showSettings(data);
    statusElement.textContent = "Settings saved.";
    statusElement.classList.remove("error");
  } catch (error) {
    statusElement.textContent = `Update failed: ${error.message}`;
    statusElement.classList.add("error");
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
      connectionDetail.textContent =
        `${target} · ${command} · ${state} · ${fps} · ${confidence} · ${area}`;
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

form.addEventListener("input", () => {
  setTargetBadge(form.targetClass.value);
  document.querySelector("#confidence-value").value = Number(form.confidence.value).toFixed(2);
  statusElement.textContent = "Applying...";
  clearTimeout(sendTimer);
  sendTimer = setTimeout(sendSettings, 120);
});

loadSettings();
loadConnectionStatus();
setInterval(loadConnectionStatus, 1000);

