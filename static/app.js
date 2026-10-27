const preview = document.querySelector("#preview");
const capture = document.querySelector("#capture");
const countdown = document.querySelector("#countdown");
const shotLabel = document.querySelector("#shot-label");
const countEl = document.querySelector("#count");
const hold = document.querySelector("#hold");
const dressing = document.querySelector("#dressing");
const flash = document.querySelector("#flash");
const cameraNote = document.querySelector("#camera-note");
const errorEl = document.querySelector("#error");
const live = document.querySelector("#live");
const results = document.querySelector("#results");
const grid = document.querySelector("#grid");
const share = document.querySelector("#share");
const qr = document.querySelector("#qr");
const driveLink = document.querySelector("#drive-link");
const aiNote = document.querySelector("#ai-note");
const driveNote = document.querySelector("#drive-note");
const newGuest = document.querySelector("#new-guest");
const cameraSelect = document.querySelector("#camera");
const refresh = document.querySelector("#refresh");
const aiLabel = document.querySelector("#ai-label");
const aiBox = document.querySelector("#ai");
const setup = document.querySelector("#setup");

let config = { hold_still_seconds: 2, photo_count: 3, ai_available: false };
let session = { active: false };
let clockOffset = 0;
let lastShots = 0;
let renderedKey = "";

preview.src = "/api/preview.mjpeg";

capture.addEventListener("click", async () => {
  capture.disabled = true;
  errorEl.hidden = true;
  const body = { ai: Boolean(aiBox.checked && config.ai_available) };
  if (cameraSelect.value !== "") body.camera_index = Number(cameraSelect.value);
  const response = await fetch("/api/session", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    errorEl.textContent = payload.detail || "Could not start the session.";
    errorEl.hidden = false;
    capture.disabled = false;
    return;
  }
  session = await response.json();
  syncClock();
  render();
});

newGuest.addEventListener("click", async () => {
  await fetch("/api/session/reset", { method: "POST" });
  session = { active: false };
  renderedKey = "";
  lastShots = 0;
  render();
});

cameraSelect.addEventListener("change", () => {
  fetch("/api/camera", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ index: Number(cameraSelect.value) }),
  });
});

refresh.addEventListener("click", async () => {
  const response = await fetch("/api/cameras/refresh", { method: "POST" });
  if (response.ok) fillCameras(await response.json());
});

function syncClock() {
  if (session.server_now) clockOffset = session.server_now - Date.now() / 1000;
}

function render() {
  const status = session.status;
  const busy = session.active && (status === "countdown" || status === "processing");
  const showingResults = session.active && (status === "ready" || (session.results || []).length > 0 && status !== "countdown");

  live.hidden = Boolean(showingResults && status !== "error");
  results.hidden = !showingResults || status === "error";
  setup.hidden = busy;
  capture.hidden = busy || showingResults;
  capture.disabled = busy;
  cameraSelect.disabled = busy;
  refresh.disabled = busy;

  countdown.hidden = status !== "countdown";
  dressing.hidden = status !== "processing";
  if (status === "countdown") {
    shotLabel.textContent = `Photo ${session.shot} of ${session.photo_count || config.photo_count}`;
  }

  if (session.shots_taken > lastShots) {
    flash.classList.remove("play");
    void flash.offsetWidth;
    flash.classList.add("play");
    lastShots = session.shots_taken;
  }
  if (!session.active) lastShots = 0;

  const failed = status === "error";
  errorEl.hidden = !failed;
  if (failed) {
    errorEl.textContent = session.error || "The session stopped.";
    capture.hidden = true;
    results.hidden = false;
    live.hidden = false;
  }

  if (showingResults) paintResults();
}

function paintResults() {
  const key = JSON.stringify({
    results: session.results,
    ai: session.ai_results,
    pending: session.ai_pending,
    aiError: session.ai_error,
    drive: session.drive_url,
    driveError: session.drive_error,
  });
  if (key === renderedKey) return;
  renderedKey = key;

  grid.replaceChildren();
  for (const item of [...(session.results || []), ...(session.ai_results || [])]) {
    const card = document.createElement("figure");
    card.className = "card";
    const img = document.createElement("img");
    img.src = item.url;
    img.alt = `${item.label}, photo ${item.shot}`;
    const caption = document.createElement("figcaption");
    caption.textContent = `Photo ${item.shot} · ${item.label}`;
    card.append(img, caption);
    grid.append(card);
  }

  aiNote.hidden = !(session.ai_pending || session.ai_error);
  aiNote.textContent = session.ai_pending
    ? "Making an extra Diwali scene…"
    : session.ai_error || "";

  const linked = Boolean(session.drive_url);
  share.hidden = !linked;
  if (linked) {
    qr.src = `/api/session/qr.png?session=${session.id}`;
    driveLink.href = session.drive_url;
  }
  driveNote.hidden = !session.drive_error;
  driveNote.textContent = session.drive_error || "";
}

function paintCountdown() {
  if (session.active && session.status === "countdown" && session.countdown_ends_at) {
    const now = Date.now() / 1000 + clockOffset;
    const remain = Math.ceil(session.countdown_ends_at - now);
    countEl.textContent = String(Math.max(1, remain));
    hold.hidden = remain > (config.hold_still_seconds || 2);
  }
  requestAnimationFrame(paintCountdown);
}

async function poll() {
  try {
    const response = await fetch("/api/session");
    if (response.ok) {
      const next = await response.json();
      const changed = JSON.stringify(next) !== JSON.stringify(session);
      session = next;
      if (session.active) syncClock();
      if (changed) render();
    }
  } catch (_err) {
    /* keep the last screen if a poll fails */
  }
}

async function watchCamera() {
  try {
    const response = await fetch("/api/cameras");
    if (!response.ok) return;
    const status = await response.json();
    if (!cameraSelect.options.length) fillCameras(status);
    const blocked = session.active && (session.status === "countdown" || session.status === "processing");
    cameraNote.hidden = blocked || status.open;
    cameraNote.textContent = status.open ? "" : status.error || "No camera is open.";
  } catch (_err) {
    cameraNote.hidden = false;
    cameraNote.textContent = "The booth cannot see a camera yet.";
  }
}

function fillCameras(status) {
  const current = cameraSelect.value;
  cameraSelect.replaceChildren();
  for (const item of status.cameras || []) {
    const option = document.createElement("option");
    option.value = String(item.index);
    option.textContent = item.name;
    cameraSelect.append(option);
  }
  const selected = status.selected != null ? String(status.selected) : current;
  if ([...cameraSelect.options].some((option) => option.value === selected)) {
    cameraSelect.value = selected;
  }
}

async function boot() {
  const response = await fetch("/api/config");
  config = await response.json();
  aiLabel.hidden = !config.ai_available;
  const cameras = await fetch("/api/cameras");
  if (cameras.ok) fillCameras(await cameras.json());
  await poll();
  render();
  setInterval(poll, 250);
  setInterval(watchCamera, 2000);
  requestAnimationFrame(paintCountdown);
}

boot();
