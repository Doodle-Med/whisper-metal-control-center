const state = {
  capabilities: null,
  jobs: [],
  groups: {},
  pollHandle: null,
  selectedJobId: null,
  selectedGroupId: null,
  showArchived: false,
  mediaRecorder: null,
  recordedChunks: [],
};

const jobForm = document.getElementById("jobForm");
const engineSelect = document.getElementById("engineSelect");
const modelSelect = document.getElementById("modelSelect");
const modelMeta = document.getElementById("modelMeta");
const languageInput = document.getElementById("languageInput");
const presetSelect = document.getElementById("presetSelect");
const temperatureInput = document.getElementById("temperatureInput");
const temperatureValue = document.getElementById("temperatureValue");
const beamSizeInput = document.getElementById("beamSizeInput");
const bestOfInput = document.getElementById("bestOfInput");
const translateToggle = document.getElementById("translateToggle");
const vadToggle = document.getElementById("vadToggle");
const diarizeToggle = document.getElementById("diarizeToggle");
const tinydiarizeToggle = document.getElementById("tinydiarizeToggle");
const noTimestampsToggle = document.getElementById("noTimestampsToggle");
const cleanFillersToggle = document.getElementById("cleanFillersToggle");
const detectLanguageToggle = document.getElementById("detectLanguageToggle");
const promptInput = document.getElementById("promptInput");
const cloudOptions = document.getElementById("cloudOptions");
const cloudModelInput = document.getElementById("cloudModelInput");
const cloudKeyInput = document.getElementById("cloudKeyInput");
const combineToggle = document.getElementById("combineToggle");
const dropzone = document.getElementById("dropzone");
const fileInput = document.getElementById("fileInput");
const browseButton = document.getElementById("browseButton");
const queuedFiles = document.getElementById("queuedFiles");
const startButton = document.getElementById("startButton");
const recordButton = document.getElementById("recordButton");
const statusMessage = document.getElementById("statusMessage");
const refreshJobsButton = document.getElementById("refreshJobsButton");
const archiveCompletedButton = document.getElementById("archiveCompletedButton");
const toggleArchivedButton = document.getElementById("toggleArchivedButton");
const jobTableBody = document.getElementById("jobTableBody");
const transcriptTitle = document.getElementById("transcriptTitle");
const transcriptMeta = document.getElementById("transcriptMeta");
const transcriptOutput = document.getElementById("transcriptOutput");
const segmentsContainer = document.getElementById("segmentsContainer");
const downloadButtons = document.getElementById("downloadButtons");
const modelStatus = document.getElementById("modelStatus");
let modelPollHandle = null;

const formatToggles = Array.from(document.querySelectorAll(".formatToggle"));

window.addEventListener("DOMContentLoaded", () => {
  initialize().catch((error) => console.error(error));
});

async function initialize() {
  try {
    startModelPolling();
    await loadCapabilities();
    await refreshJobs();
    attachEventListeners();
    state.pollHandle = window.setInterval(refreshJobs, 2500);
    showStatus("Ready to transcribe.", "info");
  } catch (error) {
    console.error(error);
    showStatus(`Failed to initialize: ${error.message || error}`, "error");
  }
}

function startModelPolling() {
  if (modelPollHandle) return;
  pollModelStatus();
  modelPollHandle = window.setInterval(pollModelStatus, 2000);
}

async function pollModelStatus() {
  try {
    const response = await fetch("/api/model-status");
    if (!response.ok) throw new Error("Unable to fetch model status");
    const payload = await response.json();
    renderModelStatus(payload.models || {});
  } catch (error) {
    console.error(error);
  }
}

function renderModelStatus(state) {
  if (!modelStatus) return;
  const entries = Object.entries(state);
  if (!entries.length) {
    modelStatus.innerHTML = "<p class='status-note'>Checking models…</p>";
    return;
  }

  const list = document.createElement("ul");
  list.className = "model-status-list";

  let hasActiveDownload = false;

  entries.forEach(([name, info]) => {
    const item = document.createElement("li");
    const status = info.status;
    const bytes = info.bytes_downloaded || 0;
    const total = info.total_bytes;
    const progress = typeof info.progress === "number" ? Math.round(info.progress * 100) : null;

    let label = `<strong>${name}</strong>`;
    if (status === "ready") {
      label += " • Ready";
    } else if (status === "downloading") {
      hasActiveDownload = true;
      const downloadedMB = (bytes / (1024 * 1024)).toFixed(1);
      const totalMB = total ? (total / (1024 * 1024)).toFixed(1) : "?";
      label += ` • Downloading ${downloadedMB} / ${totalMB} MB`;
      if (progress !== null) label += ` (${progress}%)`;
    } else if (status === "error") {
      label += " • Failed";
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = "Retry";
      button.onclick = () => retryModelDownload(name);
      item.appendChild(button);
    } else {
      label += " • Pending";
    }

    item.insertAdjacentHTML("afterbegin", `<span>${label}</span>`);
    list.appendChild(item);
  });

  modelStatus.innerHTML = "";
  modelStatus.appendChild(list);

  if (hasActiveDownload) {
    showStatus("Downloading models…", "info");
  }
}

async function retryModelDownload(name) {
  try {
    const response = await fetch(`/api/model-status/${encodeURIComponent(name)}/retry`, { method: "POST" });
    if (!response.ok) throw new Error("Retry failed");
    showStatus(`Retrying download for ${name}.`, "info");
  } catch (error) {
    console.error(error);
    showStatus(`Retry failed: ${error.message || error}`, "error");
  }
}

function attachEventListeners() {
  jobForm.addEventListener("submit", handleSubmit);
  engineSelect.addEventListener("change", handleEngineChange);
  modelSelect.addEventListener("change", updateModelMeta);
  presetSelect.addEventListener("change", applyPreset);
  temperatureInput.addEventListener("input", () => {
    temperatureValue.textContent = Number(temperatureInput.value).toFixed(2);
  });
  browseButton.addEventListener("click", () => fileInput.click());
  fileInput.addEventListener("change", updateQueuedFileList);
  dropzone.addEventListener("dragover", handleDragOver);
  dropzone.addEventListener("dragleave", () => dropzone.classList.remove("dragover"));
  dropzone.addEventListener("drop", handleDrop);
  refreshJobsButton.addEventListener("click", refreshJobs);
  archiveCompletedButton.addEventListener("click", archiveCompletedJobs);
  toggleArchivedButton.addEventListener("click", toggleArchivedView);
  jobTableBody.addEventListener("click", handleJobTableClick);
  recordButton.addEventListener("click", handleRecordButton);
}

async function loadCapabilities() {
  const response = await fetch("/api/capabilities");
  if (!response.ok) throw new Error("Unable to fetch server capabilities");
  const capabilities = await response.json();
  state.capabilities = capabilities;

  populateModels(capabilities.available_models || []);
  updateModelMeta();
  handleEngineChange();
  temperatureValue.textContent = Number(temperatureInput.value).toFixed(2);
}

function populateModels(models) {
  modelSelect.innerHTML = "";
  const autoOption = document.createElement("option");
  autoOption.value = "";
  autoOption.textContent = "Auto (server default)";
  modelSelect.appendChild(autoOption);

  models.forEach((model) => {
    const option = document.createElement("option");
    option.value = model.path;
    const quant = model.quantization ? ` • ${model.quantization}` : "";
    option.textContent = `${model.name} • ${model.size_mb} MB${quant}`;
    modelSelect.appendChild(option);
  });

  if (models.length === 0) {
    modelMeta.textContent = "No local models detected. Run setup script.";
  } else {
    modelSelect.selectedIndex = 1;
    updateModelMeta();
  }
}

function updateModelMeta() {
  const selected = modelSelect.options[modelSelect.selectedIndex];
  if (!selected) return;
  if (!selected.value) {
    modelMeta.textContent = "Using server default model.";
  } else {
    modelMeta.textContent = selected.textContent;
  }
}

function handleEngineChange() {
  const isCloud = engineSelect.value !== "local";
  cloudOptions.hidden = !isCloud;
  if (isCloud && engineSelect.value === "gemini") {
    showStatus("Gemini offload will raise an error until configured.", "warn");
  }
}

function applyPreset() {
  const preset = presetSelect.value;
  if (preset === "speed") {
    temperatureInput.value = "0.0";
    beamSizeInput.value = "1";
    bestOfInput.value = "1";
    temperatureValue.textContent = "0.00";
    translateToggle.checked = false;
    diarizeToggle.checked = false;
  } else if (preset === "accuracy") {
    temperatureInput.value = "0.1";
    beamSizeInput.value = "5";
    bestOfInput.value = "5";
    temperatureValue.textContent = "0.10";
    translateToggle.checked = false;
  } else {
    temperatureInput.value = "0.0";
    beamSizeInput.value = "2";
    bestOfInput.value = "2";
    temperatureValue.textContent = "0.00";
  }
}

function handleDragOver(event) {
  event.preventDefault();
  dropzone.classList.add("dragover");
}

function handleDrop(event) {
  event.preventDefault();
  dropzone.classList.remove("dragover");
  const files = Array.from(event.dataTransfer.files || []);
  if (files.length) {
    appendFilesToInput(files);
    updateQueuedFileList();
  }
}

function appendFilesToInput(files) {
  const dataTransfer = new DataTransfer();
  Array.from(fileInput.files).forEach((file) => dataTransfer.items.add(file));
  files.forEach((file) => dataTransfer.items.add(file));
  fileInput.files = dataTransfer.files;
}

function updateQueuedFileList() {
  queuedFiles.innerHTML = "";
  const files = Array.from(fileInput.files);
  if (!files.length) {
    const li = document.createElement("li");
    li.textContent = "No files queued";
    queuedFiles.appendChild(li);
    return;
  }
  files.forEach((file) => {
    const li = document.createElement("li");
    li.textContent = `${file.name} (${formatBytes(file.size)})`;
    queuedFiles.appendChild(li);
  });
}

function formatBytes(bytes) {
  if (!Number.isFinite(bytes) || bytes <= 0) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  const exponent = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  const value = bytes / 1024 ** exponent;
  return `${value.toFixed(value < 10 && exponent > 0 ? 1 : 0)} ${units[exponent]}`;
}

async function handleSubmit(event) {
  event.preventDefault();
  const files = Array.from(fileInput.files);
  if (!files.length) {
    showStatus("Please choose at least one audio file.", "warn");
    return;
  }

  startButton.disabled = true;
  showStatus("Uploading audio and queueing jobs…", "info");

  const formData = new FormData();
  files.forEach((file) => formData.append("files", file, file.name));
  formData.append("engine", engineSelect.value);
  formData.append("model", modelSelect.value);
  formData.append("language", languageInput.value || "auto");
  formData.append("translate", translateToggle.checked);
  formData.append("temperature", temperatureInput.value);
  formData.append("beam_size", beamSizeInput.value);
  formData.append("best_of", bestOfInput.value);
  formData.append("initial_prompt", promptInput.value);
  formData.append("vad", vadToggle.checked);
  formData.append("diarize", diarizeToggle.checked);
  formData.append("tinydiarize", tinydiarizeToggle.checked);
  formData.append("no_timestamps", noTimestampsToggle.checked);
  formData.append("detect_language", detectLanguageToggle.checked);
  formData.append("combine", combineToggle.checked);

  const cleaners = ["collapse_spaces"];
  if (cleanFillersToggle.checked) cleaners.push("remove_fillers");
  formData.append("cleaners", cleaners.join(","));

  const selectedFormats = formatToggles.filter((toggle) => toggle.checked).map((toggle) => toggle.value);
  formData.append("output_formats", selectedFormats.join(","));

  formData.append("cloud_model", cloudModelInput.value);
  if (cloudKeyInput.value) {
    formData.append("cloud_api_key", cloudKeyInput.value.trim());
  }

  try {
    const response = await fetch("/api/jobs", {
      method: "POST",
      body: formData,
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      throw new Error(error.detail || response.statusText);
    }

    const payload = await response.json();
    const jobs = Array.isArray(payload) ? payload : payload.jobs || [];
    const groupInfo = !Array.isArray(payload) ? payload.group : null;

    showStatus(`Queued ${jobs.length} job(s).`, "success");
    updateQueuedFileList();
    fileInput.value = "";
    await refreshJobs();

    if (groupInfo && groupInfo.id) {
      state.groups[groupInfo.id] = {
        id: groupInfo.id,
        job_ids: groupInfo.job_ids || [],
        downloads: groupInfo.downloads || {},
      };
      await fetchGroup(groupInfo.id);
      await selectGroup(groupInfo.id, { silent: true });
    }
  } catch (error) {
    console.error(error);
    showStatus(`Failed to queue jobs: ${error.message || error}`, "error");
  } finally {
    startButton.disabled = false;
  }
}

async function refreshJobs() {
  try {
    const response = await fetch(`/api/jobs?archived=${state.showArchived ? "true" : "false"}`);
    if (!response.ok) throw new Error("Failed to fetch jobs");
    state.jobs = await response.json();
    syncGroupsFromJobs();
    toggleArchivedButton.textContent = state.showArchived ? "Show Active" : "Show Archived";
    archiveCompletedButton.disabled = state.showArchived;
    renderJobs();
    await refreshGroups();
    if (state.selectedJobId) {
      const job = state.jobs.find((item) => item.id === state.selectedJobId);
      if (job && job.status === "completed") {
        await selectJob(job.id, { silent: true });
      }
    } else if (state.selectedGroupId) {
      const group = state.groups[state.selectedGroupId];
      if (group) {
        renderGroupViewer();
      }
    }
  } catch (error) {
    console.error(error);
    showStatus(`Refresh failed: ${error.message || error}`, "error");
  }
}

function syncGroupsFromJobs() {
  state.jobs.forEach((job) => {
    const groupId = job.group_id;
    if (!groupId) return;
    if (!state.groups[groupId]) {
      state.groups[groupId] = { id: groupId, jobs: [], job_ids: [] };
    }
  });
}

function renderJobs() {
  jobTableBody.innerHTML = "";
  const fragment = document.createDocumentFragment();

  const groupEntries = Object.entries(state.groups)
    .filter(([groupId, group]) => {
      if (!group) return false;
      const jobs = group.jobs || [];
      if (!jobs.length) {
        // Placeholder entry while the group metadata loads; surface it only in the active view.
        return !state.showArchived;
      }
      const hasArchived = jobs.some((job) => job.archived);
      const hasActive = jobs.some((job) => !job.archived);
      return state.showArchived ? hasArchived : hasActive;
    })
    .sort(([, a], [, b]) => {
      const aTime = new Date(a.updated_at || a.created_at || 0).getTime();
      const bTime = new Date(b.updated_at || b.created_at || 0).getTime();
      return bTime - aTime;
    });

  groupEntries.forEach(([groupId, group]) => {
    const row = document.createElement("tr");
    row.className = "group-row";
    if (state.selectedGroupId === groupId) row.classList.add("selected-row");
    row.dataset.groupId = groupId;
    row.dataset.type = "group";

    const jobCount = (group.jobs && group.jobs.length) || group.job_ids?.length || 0;
    const jobCell = document.createElement("td");
    jobCell.innerHTML = `<strong>Combined Transcript</strong><br><small>${jobCount} files • ${groupId.slice(0, 8)}</small>`;

    const statusCell = document.createElement("td");
    const badge = document.createElement("span");
    badge.className = "status-badge";
    badge.dataset.state = group.complete ? "completed" : "running";
    badge.textContent = group.complete ? "COMPLETED" : "IN PROGRESS";
    statusCell.appendChild(badge);

    const progressCell = document.createElement("td");
    const progressBar = document.createElement("div");
    progressBar.className = "progress";
    const progressInner = document.createElement("span");
    const progressValue = computeGroupProgress(group);
    progressInner.style.width = `${progressValue}%`;
    progressBar.appendChild(progressInner);
    const progressLabel = document.createElement("div");
    progressLabel.textContent = `${progressValue}%`;
    progressLabel.style.fontSize = "0.8rem";
    progressLabel.style.marginTop = "0.35rem";
    progressLabel.style.color = "var(--text-muted)";
    progressCell.appendChild(progressBar);
    progressCell.appendChild(progressLabel);

    const actionCell = document.createElement("td");
    const actions = document.createElement("div");
    actions.className = "row-actions";
    const viewButton = document.createElement("button");
    viewButton.type = "button";
    viewButton.className = "secondary view-group";
    viewButton.dataset.groupId = groupId;
    viewButton.textContent = "View Combined";
    actions.appendChild(viewButton);

    if (group.downloads) {
      Object.entries(group.downloads).forEach(([fmt, url]) => {
        const link = document.createElement("a");
        link.href = url;
        link.target = "_blank";
        link.rel = "noopener";
        link.textContent = fmt.toUpperCase();
        actions.appendChild(link);
      });
    }

    actionCell.appendChild(actions);
    row.appendChild(jobCell);
    row.appendChild(statusCell);
    row.appendChild(progressCell);
    row.appendChild(actionCell);
    fragment.appendChild(row);
  });

  state.jobs.forEach((job) => {
    const row = document.createElement("tr");
    row.dataset.jobId = job.id;
    if (state.selectedJobId === job.id) row.classList.add("selected-row");

    const jobCell = document.createElement("td");
    jobCell.innerHTML = `<strong>${job.filename}</strong><br><small>${job.id.slice(0, 8)} • ${job.engine}</small>`;

    const statusCell = document.createElement("td");
    const badge = document.createElement("span");
    badge.className = "status-badge";
    badge.dataset.state = job.status;
    badge.textContent = job.status.toUpperCase();
    statusCell.appendChild(badge);

    const progressCell = document.createElement("td");
    const progressBar = document.createElement("div");
    progressBar.className = "progress";
    const progressInner = document.createElement("span");
    progressInner.style.width = `${job.progress ?? 0}%`;
    progressBar.appendChild(progressInner);
    const progressLabel = document.createElement("div");
    progressLabel.textContent = `${job.progress ?? 0}%`;
    progressLabel.style.fontSize = "0.8rem";
    progressLabel.style.marginTop = "0.35rem";
    progressLabel.style.color = "var(--text-muted)";
    progressCell.appendChild(progressBar);
    progressCell.appendChild(progressLabel);

    const actionCell = document.createElement("td");
    const actions = document.createElement("div");
    actions.className = "row-actions";

    const viewButton = document.createElement("button");
    viewButton.type = "button";
    viewButton.className = "secondary view-job";
    viewButton.dataset.jobId = job.id;
    viewButton.textContent = job.status === "completed" ? "View" : "Details";
    actions.appendChild(viewButton);

    if (job.status === "queued" || job.status === "running") {
      const cancelButton = document.createElement("button");
      cancelButton.type = "button";
      cancelButton.className = "secondary cancel-job";
      cancelButton.dataset.jobId = job.id;
      cancelButton.textContent = "Cancel";
      actions.appendChild(cancelButton);
    } else if (job.status === "completed" && !job.archived) {
      const archiveButton = document.createElement("button");
      archiveButton.type = "button";
      archiveButton.className = "secondary archive-job";
      archiveButton.dataset.jobId = job.id;
      archiveButton.textContent = "Archive";
      actions.appendChild(archiveButton);
    } else if (job.archived) {
      const restoreButton = document.createElement("button");
      restoreButton.type = "button";
      restoreButton.className = "secondary restore-job";
      restoreButton.dataset.jobId = job.id;
      restoreButton.textContent = "Restore";
      actions.appendChild(restoreButton);
    }

    if (job.downloads && Object.keys(job.downloads).length) {
      Object.entries(job.downloads).forEach(([fmt, url]) => {
        const link = document.createElement("a");
        link.href = url;
        link.target = "_blank";
        link.rel = "noopener";
        link.textContent = fmt.toUpperCase();
        actions.appendChild(link);
      });
    }

    actionCell.appendChild(actions);

    row.appendChild(jobCell);
    row.appendChild(statusCell);
    row.appendChild(progressCell);
    row.appendChild(actionCell);
    fragment.appendChild(row);
  });

  if (!fragment.childNodes.length) {
    const row = document.createElement("tr");
    row.className = "empty";
    const cell = document.createElement("td");
    cell.colSpan = 4;
    cell.textContent = state.showArchived ? "No archived jobs." : "Queue is empty.";
    row.appendChild(cell);
    fragment.appendChild(row);
  }

  jobTableBody.appendChild(fragment);
}

async function handleJobTableClick(event) {
  const target = event.target;
  if (target.matches(".view-job")) {
    const jobId = target.dataset.jobId;
    await selectJob(jobId);
  } else if (target.matches(".view-group")) {
    const groupId = target.dataset.groupId || target.closest("tr")?.dataset.groupId;
    if (groupId) {
      await selectGroup(groupId);
    }
  } else if (target.matches(".cancel-job")) {
    const jobId = target.dataset.jobId;
    await cancelJob(jobId);
  } else if (target.matches(".archive-job")) {
    const jobId = target.dataset.jobId;
    await archiveJob(jobId);
  } else if (target.matches(".restore-job")) {
    const jobId = target.dataset.jobId;
    await unarchiveJob(jobId);
  }
}

async function selectJob(jobId, { silent = false } = {}) {
  state.selectedGroupId = null;
  try {
    const response = await fetch(`/api/jobs/${jobId}`);
    if (!response.ok) throw new Error("Unable to fetch job");
    const job = await response.json();
    state.selectedJobId = jobId;
    renderTranscript(job);
    if (!silent) {
      showStatus(`Loaded transcript for ${job.filename}.`, "success");
    }
  } catch (error) {
    console.error(error);
    showStatus(`Failed to load job: ${error.message || error}`, "error");
  }
}

function renderTranscript(job) {
  state.selectedGroupId = null;
  transcriptTitle.textContent = job.filename;
  transcriptMeta.textContent = `${job.status.toUpperCase()} • Job ${job.id.slice(0, 8)}`;

  downloadButtons.innerHTML = "";
  if (job.downloads) {
    Object.entries(job.downloads).forEach(([fmt, url]) => {
      const link = document.createElement("a");
      link.href = url;
      link.target = "_blank";
      link.rel = "noopener";
      link.textContent = fmt.toUpperCase();
      downloadButtons.appendChild(link);
    });
  }

  const result = job.result;
  if (!result || !result.text) {
    transcriptOutput.textContent = job.status === "completed" ? "No text returned." : "Waiting for transcription…";
    segmentsContainer.innerHTML = "";
    return;
  }

  transcriptOutput.textContent = result.text;

  segmentsContainer.innerHTML = "";
  (result.segments || []).forEach((segment) => {
    const card = document.createElement("div");
    card.className = "segment-card";
    const timeEl = document.createElement("time");
    timeEl.textContent = `${formatTime(segment.start)} → ${formatTime(segment.end)}`;
    const textEl = document.createElement("div");
    textEl.textContent = segment.text;
    card.appendChild(timeEl);
    card.appendChild(textEl);
    segmentsContainer.appendChild(card);
  });
}

function formatTime(value) {
  if (!Number.isFinite(value)) return "00:00";
  const totalSeconds = Math.max(0, value);
  const minutes = Math.floor(totalSeconds / 60)
    .toString()
    .padStart(2, "0");
  const seconds = Math.floor(totalSeconds % 60)
    .toString()
    .padStart(2, "0");
  return `${minutes}:${seconds}`;
}

async function cancelJob(jobId) {
  try {
    const response = await fetch(`/api/jobs/${jobId}`, { method: "DELETE" });
    if (!response.ok) throw new Error("Cancel request failed");
    showStatus(`Cancelled job ${jobId.slice(0, 8)}.`, "warn");
    await refreshJobs();
  } catch (error) {
    console.error(error);
    showStatus(`Failed to cancel: ${error.message || error}`, "error");
  }
}

function showStatus(message, tone = "info") {
  statusMessage.textContent = message;
  statusMessage.dataset.tone = tone;
}

async function refreshGroups() {
  const groupIds = Object.keys(state.groups);
  if (!groupIds.length) return;
  await Promise.all(
    groupIds.map(async (groupId) => {
      try {
        await fetchGroup(groupId);
      } catch (error) {
        console.error(error);
      }
    }),
  );
  if (state.selectedGroupId) {
    renderGroupViewer();
  }
}

async function fetchGroup(groupId) {
  const response = await fetch(`/api/groups/${groupId}`);
  if (!response.ok) {
    if (response.status === 404) {
      delete state.groups[groupId];
      if (state.selectedGroupId === groupId) {
        state.selectedGroupId = null;
        transcriptOutput.textContent = "Combined transcript unavailable.";
      }
    }
    return null;
  }
  const payload = await response.json();
  state.groups[groupId] = payload;
  return payload;
}

function computeGroupProgress(group) {
  const jobs = group?.jobs || [];
  if (!jobs.length) return 0;
  const total = jobs.reduce((sum, job) => sum + (job.progress ?? 0), 0);
  return Math.round(total / jobs.length);
}

async function selectGroup(groupId, { silent = false } = {}) {
  state.selectedJobId = null;
  const group = (await fetchGroup(groupId)) || state.groups[groupId];
  if (!group) {
    if (!silent) showStatus("Combined transcript not found.", "error");
    return;
  }
  state.selectedGroupId = groupId;
  renderGroupViewer();
  if (!silent) {
    showStatus(`Loaded combined transcript (${group.jobs?.length || 0} files).`, "success");
  }
}

function renderGroupViewer() {
  const group = state.groups[state.selectedGroupId];
  if (!group) return;

  const total = group.jobs?.length || group.job_ids?.length || 0;
  const completed = (group.jobs || []).filter((job) => job.status === "completed").length;
  transcriptTitle.textContent = "Combined Transcript";
  transcriptMeta.textContent = `Group ${state.selectedGroupId.slice(0, 8)} • ${completed}/${total} completed`;

  const text = group.combined_text || "";
  transcriptOutput.textContent = text || (group.complete ? "No transcripts available." : "Waiting for jobs to finish…");

  downloadButtons.innerHTML = "";
  if (group.downloads) {
    Object.entries(group.downloads).forEach(([fmt, url]) => {
      const link = document.createElement("a");
      link.href = url;
      link.target = "_blank";
      link.rel = "noopener";
      link.textContent = fmt.toUpperCase();
      downloadButtons.appendChild(link);
    });
  }

  segmentsContainer.innerHTML = "";
  (group.jobs || []).forEach((job) => {
    const card = document.createElement("div");
    card.className = "segment-card";
    const title = document.createElement("div");
    title.innerHTML = `<strong>${job.filename}</strong>`;
    const status = document.createElement("time");
    status.textContent = `Status: ${job.status.toUpperCase()} (${job.progress ?? 0}%)`;
    card.appendChild(title);
    card.appendChild(status);
    segmentsContainer.appendChild(card);
  });
}

async function archiveCompletedJobs() {
  try {
    const response = await fetch("/api/jobs/archive-completed", { method: "POST" });
    if (!response.ok) throw new Error("Archive request failed");
    const payload = await response.json();
    showStatus(`Archived ${payload.archived ?? 0} job(s).`, "success");
    await refreshJobs();
  } catch (error) {
    console.error(error);
    showStatus(`Archive failed: ${error.message || error}`, "error");
  }
}

function toggleArchivedView() {
  state.showArchived = !state.showArchived;
  state.selectedJobId = null;
  state.selectedGroupId = null;
  refreshJobs();
}

async function archiveJob(jobId) {
  try {
    const response = await fetch(`/api/jobs/${jobId}/archive`, { method: "POST" });
    if (!response.ok) throw new Error("Archive request failed");
    showStatus(`Archived job ${jobId.slice(0, 8)}.`, "success");
    await refreshJobs();
  } catch (error) {
    console.error(error);
    showStatus(`Failed to archive job: ${error.message || error}`, "error");
  }
}

async function unarchiveJob(jobId) {
  try {
    const response = await fetch(`/api/jobs/${jobId}/unarchive`, { method: "POST" });
    if (!response.ok) throw new Error("Unarchive request failed");
    showStatus(`Restored job ${jobId.slice(0, 8)}.`, "success");
    await refreshJobs();
  } catch (error) {
    console.error(error);
    showStatus(`Failed to restore job: ${error.message || error}`, "error");
  }
}

async function handleRecordButton() {
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    showStatus("Recording not supported in this browser.", "warn");
    return;
  }

  if (!state.mediaRecorder || state.mediaRecorder.state === "inactive") {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      state.recordedChunks = [];
      state.mediaRecorder = new MediaRecorder(stream);
      state.mediaRecorder.ondataavailable = (event) => {
        if (event.data?.size > 0) state.recordedChunks.push(event.data);
      };
      state.mediaRecorder.onstop = () => {
        stream.getTracks().forEach((track) => track.stop());
        if (!state.recordedChunks.length) return;
        const blob = new Blob(state.recordedChunks, { type: "audio/webm" });
        const file = new File([blob], `recording-${Date.now()}.webm`, { type: blob.type });
        appendFilesToInput([file]);
        updateQueuedFileList();
        showStatus("Recording ready—added to queue.", "success");
        recordButton.textContent = "Record Quick Note";
      };
      state.mediaRecorder.start();
      recordButton.textContent = "Stop Recording";
      showStatus("Recording… click stop when done.", "info");
    } catch (error) {
      console.error(error);
      showStatus("Microphone access denied.", "error");
    }
  } else if (state.mediaRecorder.state === "recording") {
    state.mediaRecorder.stop();
  }
}
