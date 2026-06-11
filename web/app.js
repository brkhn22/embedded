const form = document.querySelector("#settings-form");
const statusElement = document.querySelector("#status");
const swatch = document.querySelector("#swatch");
const connectionCard = document.querySelector("#connection-card");
const connectionTitle = document.querySelector("#connection-title");
const connectionDetail = document.querySelector("#connection-detail");
const fields = [
  "targetColor",
  "hueTolerance",
  "saturationTolerance",
  "valueTolerance",
  "minContourArea",
];

let sendTimer;

function showSettings(settings) {
  for (const name of fields) {
    const input = document.querySelector(`#${name}`);
    input.value = settings[name];

    const output = document.querySelector(`#${name}-value`);
    if (output) {
      output.value = settings[name];
    }
  }

  document.querySelector("#hex-value").value = settings.targetColor;
  swatch.style.backgroundColor = settings.targetColor;
}

function readSettings() {
  return {
    targetColor: form.targetColor.value,
    hueTolerance: Number(form.hueTolerance.value),
    saturationTolerance: Number(form.saturationTolerance.value),
    valueTolerance: Number(form.valueTolerance.value),
    minContourArea: Number(form.minContourArea.value),
  };
}

async function loadSettings() {
  try {
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
      connectionTitle.textContent = "OpenCV connected";
      const target = status.targetDetected ? "target detected" : "searching";
      const command = status.command ? `Command ${status.command}` : "No command yet";
      connectionDetail.textContent = `${command} · ${target}`;
    } else {
      connectionTitle.textContent = "OpenCV disconnected";
      connectionDetail.textContent =
        status.lastSeenSeconds === null
          ? "Waiting for the vision process..."
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
  showSettings(readSettings());
  statusElement.textContent = "Applying...";
  clearTimeout(sendTimer);
  sendTimer = setTimeout(sendSettings, 120);
});

loadSettings();
loadConnectionStatus();
setInterval(loadConnectionStatus, 1000);
