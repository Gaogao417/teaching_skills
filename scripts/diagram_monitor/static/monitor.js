const STATUS_LABELS = {
  pending: "等待中",
  running: "运行中",
  stalled: "疑似卡住",
  failed: "失败",
  incomplete: "产物不完整",
  success: "成功",
  conflict: "状态冲突",
};

const STAGES = [
  ["collect", "收集"],
  ["agent", "Agent"],
  ["wolfram", "Wolfram"],
  ["renderer_spec", "Spec"],
  ["tikz", "TikZ"],
  ["preview", "预览"],
  ["audit", "审核"],
  ["resolve", "Resolve"],
];

const TABS = [
  ["overview", "概览"],
  ["rounds", "轮次"],
  ["events", "事件"],
  ["artifacts", "产物"],
  ["performance", "性能"],
];

const REVIEW_LABELS = {
  unreviewed: "未复核",
  accepted: "已接受",
  queued: "排队中",
  revision_running: "Agent 修订中",
  revision_completed: "新版本待复核",
  revision_failed: "修订失败",
};

const CODEX_TASK_LABELS = {
  creating: "正在创建",
  created: "已创建",
  failed: "创建失败",
};

const state = {
  folders: [],
  folder: null,
  job: null,
  jobDetail: null,
  tab: "overview",
  timer: null,
  loading: false,
  reviewDrafts: {},
  reviewActions: {},
  reviewSubmitting: false,
  reviewSubmittingDecision: "",
};

const el = (id) => document.getElementById(id);

document.addEventListener("DOMContentLoaded", () => {
  const query = new URLSearchParams(location.search).get("q") || "";
  el("search-input").value = query;
  el("search-form").addEventListener("submit", (event) => { event.preventDefault(); refreshAll(true); });
  el("search-input").addEventListener("input", debounce(() => refreshAll(true), 280));
  el("status-filter").addEventListener("change", () => refreshAll(true));
  el("problems-only").addEventListener("change", () => refreshAll(true));
  el("auto-refresh").addEventListener("change", configureTimer);
  el("manual-refresh").addEventListener("click", () => refreshAll(false));
  el("copy-path").addEventListener("click", copySelectedPath);
  el("artifact-close").addEventListener("click", () => el("artifact-dialog").close());
  el("artifact-dialog").addEventListener("click", (event) => {
    if (event.target === el("artifact-dialog")) el("artifact-dialog").close();
  });
  renderTabs();
  configureTimer();
  refreshAll(true);
});

function configureTimer() {
  if (state.timer) clearInterval(state.timer);
  state.timer = null;
  if (el("auto-refresh").checked) state.timer = setInterval(() => refreshAll(false), 2000);
}

async function refreshAll(resetSelection) {
  if (state.loading) return;
  state.loading = true;
  try {
    const params = new URLSearchParams({
      query: el("search-input").value.trim(),
      status: el("status-filter").value,
      problems_only: String(el("problems-only").checked),
    });
    const payload = await api(`/api/folders?${params}`);
    state.folders = payload.items;
    if (resetSelection || !state.folders.some((item) => item.path === state.folder?.path)) {
      state.folder = state.folders[0] || null;
      state.job = null;
      state.jobDetail = null;
    }
    el("result-count").textContent = `${payload.count} 个目录`;
    el("refresh-time").textContent = `刷新于 ${formatClock(new Date())}`;
    renderFolders();
    if (state.folder) await loadFolder(state.folder.path, false);
    else renderEmptyWorkspace();
    clearAlert();
  } catch (error) {
    showAlert(`刷新失败：${error.message}`);
  } finally {
    state.loading = false;
  }
}

async function loadFolder(path, selectFirst = true) {
  const previousJobId = state.job?.job_id;
  state.folder = await api(`/api/folder?path=${encodeURIComponent(path)}`);
  if (selectFirst || !state.folder.jobs.some((item) => item.job_id === previousJobId)) {
    state.job = state.folder.jobs[0] || null;
  } else {
    state.job = state.folder.jobs.find((item) => item.job_id === previousJobId);
  }
  renderFolders();
  renderFolderSummary();
  renderJobs();
  if (state.job) await loadJob(state.job.job_id, false);
  else renderJobEmpty();
}

async function loadJob(jobId, resetTab = false) {
  preserveCurrentReviewDraft();
  if (resetTab) state.tab = "overview";
  state.job = state.folder.jobs.find((item) => item.job_id === jobId) || state.job;
  renderJobs();
  renderTabs();
  state.jobDetail = await api(`/api/job?folder=${encodeURIComponent(state.folder.path)}&job_id=${encodeURIComponent(jobId)}`);
  el("copy-path").disabled = false;
  renderDetail();
}

function renderFolders() {
  const container = el("folder-list");
  if (!state.folders.length) {
    container.innerHTML = emptyState("⌕", el("search-input").value ? "没有找到匹配的作业目录" : "输入关键词查找作业目录", "可以搜索专题、学生或知识点名称");
    return;
  }
  container.innerHTML = state.folders.map((folder) => {
    const counts = folder.job_counts || {};
    return `<button class="folder-card ${folder.path === state.folder?.path ? "is-selected" : ""}" data-folder="${escapeAttr(folder.path)}">
      <span class="folder-card-head"><span class="folder-name">${escapeHtml(folder.name)}</span><span class="badge-stack">${statusBadge(folder.status)}${folder.has_conflict ? warningBadge("汇总不一致") : ""}</span></span>
      <code class="folder-path">${escapeHtml(folder.path)}</code>
      <span class="folder-stats">
        <span class="mini-stat"><b>${counts.total || 0}</b><span>Jobs</span></span>
        <span class="mini-stat"><b>${counts.success || 0}</b><span>成功</span></span>
        <span class="mini-stat"><b>${folder.preview_count || 0}</b><span>最终图</span></span>
      </span>
      <time class="activity-time" title="${escapeAttr(folder.latest_activity)}">活动于 ${formatRelative(folder.latest_activity_epoch)}</time>
    </button>`;
  }).join("");
  container.querySelectorAll("[data-folder]").forEach((button) => button.addEventListener("click", () => loadFolder(button.dataset.folder, true)));
}

function renderFolderSummary() {
  const folder = state.folder;
  const counts = folder.job_counts || {};
  const reasons = (folder.status_reasons || []).slice(0, 2);
  const warnings = (folder.status_warnings || []).slice(0, 2);
  el("folder-summary").innerHTML = `<div class="summary-row">
    <div><p class="summary-title">${escapeHtml(folder.name)}</p><div class="summary-meta">
      <span class="meta-chip">${counts.total || 0} jobs</span>
      <span class="meta-chip">${folder.preview_count || 0} previews</span>
      <span class="meta-chip">${folder.has_resolved_yaml ? "resolved YAML ✓" : "未 resolve"}</span>
      <span class="meta-chip">${folder.has_final_pdf ? "PDF ✓" : "无最终 PDF"}</span>
    </div></div><span class="badge-stack">${statusBadge(folder.status)}${folder.has_conflict ? warningBadge("汇总不一致") : ""}</span>
  </div>${reasons.length ? `<p class="summary-error">${reasons.map(escapeHtml).join(" · ")}</p>` : ""}${warnings.length ? `<p class="summary-warning">${warnings.map(escapeHtml).join(" · ")}</p>` : ""}`;
}

function renderJobs() {
  const container = el("job-grid");
  if (!state.folder?.jobs?.length) {
    container.innerHTML = emptyState("◇", "这个目录还没有 diagram job", "manifest 或 job 目录出现后会自动刷新");
    return;
  }
  container.innerHTML = state.folder.jobs.map((job) => {
    const preview = job.preview_path ? `<img src="${fileUrl(job.preview_path)}" alt="${escapeAttr(job.job_id)} 最终预览" loading="lazy">` : `<div class="preview-placeholder"><strong>${STATUS_LABELS[job.status] || job.status}</strong><span>${escapeHtml(job.status_reasons?.[0] || "尚未生成预览图")}</span></div>`;
    const stageDots = STAGES.map(([key, label]) => `<i class="stage-dot ${escapeAttr(job.stages?.[key] || "pending")}" title="${label}：${escapeAttr(job.stages?.[key] || "pending")}"></i>`).join("");
    return `<button class="job-card ${job.job_id === state.job?.job_id ? "is-selected" : ""}" data-job="${escapeAttr(job.job_id)}">
      <span class="preview-well">${preview}<span class="preview-round">${job.round_count || 0} round</span></span>
      <span class="job-content"><span class="job-title-row"><span class="job-name">${escapeHtml(job.job_id)}</span><span class="badge-stack">${statusBadge(job.status)}${job.has_conflict ? warningBadge("汇总不一致") : ""}</span></span>
      <span class="job-meta">${escapeHtml(job.variant || "—")} · ${escapeHtml(job.engine || "—")} · ${escapeHtml(job.diagram_kind || "—")}</span>
      <span class="stage-rail">${stageDots}</span><span class="stage-labels"><span>收集</span><span>Resolve</span></span></span>
    </button>`;
  }).join("");
  container.querySelectorAll("[data-job]").forEach((button) => button.addEventListener("click", () => loadJob(button.dataset.job, true)));
}

function renderTabs() {
  el("detail-tabs").innerHTML = TABS.map(([key, label]) => `<button class="detail-tab ${state.tab === key ? "is-active" : ""}" data-tab="${key}" type="button">${label}</button>`).join("");
  el("detail-tabs").querySelectorAll("[data-tab]").forEach((button) => button.addEventListener("click", () => { state.tab = button.dataset.tab; renderTabs(); renderDetail(); }));
}

function renderDetail() {
  const job = state.jobDetail;
  if (!job) { renderJobEmpty(); return; }
  el("detail-title").textContent = job.job_id;
  if (state.tab === "overview") renderOverview(job);
  if (state.tab === "rounds") renderRounds(job);
  if (state.tab === "events") renderEvents(job);
  if (state.tab === "artifacts") renderArtifacts(job);
  if (state.tab === "performance") renderPerformance(job);
}

function renderOverview(job) {
  const candidateRound = selectedCandidateRound(job);
  const candidatePreview = DiagramReviewState.candidatePreview(job, candidateRound);
  const preview = candidatePreview ? `<img src="${fileUrl(candidatePreview)}" alt="${escapeAttr(job.job_id)} 当前候选 Round ${candidateRound}">` : `<div class="preview-placeholder"><strong>${STATUS_LABELS[job.status] || job.status}</strong><span>Round ${candidateRound} 尚未生成可预览图片</span></div>`;
  const stem = typeof job.stem_latex === "string" && job.stem_latex.trim()
    ? `<section class="question-stem"><h3>题干</h3><div class="question-stem-body">${escapeHtml(job.stem_latex)}</div></section>`
    : "";
  const reasons = job.status_reasons?.length ? `<section class="detail-section"><h3>状态说明</h3><ul class="reason-list">${job.status_reasons.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul></section>` : "";
  const warnings = job.status_warnings?.length ? `<section class="detail-section evidence-warning"><h3>证据提醒</h3><ul>${job.status_warnings.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul></section>` : "";
  el("detail-body").innerHTML = `${stem}<div class="candidate-label"><strong>当前候选 Round ${candidateRound}</strong><span>确定性审核：${escapeHtml(candidateAudit(job))}</span></div><div class="detail-preview">${preview}</div>
    ${humanReviewPanel(job, candidateRound)}
    <section class="detail-section"><h3><span>运行摘要</span>${statusBadge(job.status)}</h3><div class="key-grid">
      ${keyItem("Slot", job.slot_id || "—")}${keyItem("Variant", job.variant || "—")}${keyItem("Engine", job.engine || "—")}${keyItem("Diagram kind", job.diagram_kind || "—")}
      ${keyItem("Rounds", String(job.round_count || 0))}${keyItem("Selected", job.selected_round ?? "—")}${keyItem("Agent", formatDuration(job.agent_duration_ms))}${keyItem("Wolfram", job.wolfram_solve_time_s != null ? `${job.wolfram_solve_time_s}s` : "—")}
    </div></section>${reasons}${warnings}<section class="detail-section"><h3>阶段证据</h3>${stageDetail(job.stages)}</section>`;
  bindHumanReviewActions(job, candidateRound);
}

function humanReviewPanel(job, candidateRound) {
  const review = job.human_review || {};
  const status = review.status || "unreviewed";
  const deterministicAudit = candidateAudit(job);
  const controls = DiagramReviewState.reviewControls({ status, deterministicAudit });
  const key = reviewDraftKey();
  const draft = DiagramReviewState.preserveReviewDraft(state.reviewDrafts, key, "");
  const accepted = status === "accepted" ? `<span class="review-accepted">已接受 Round ${review.base_round}</span>` : "";
  const message = review.message ? `<p class="review-error">${escapeHtml(review.message)}</p>` : "";
  const reason = controls.acceptReason ? `<p class="review-audit-reason">${escapeHtml(controls.acceptReason)}（当前：${escapeHtml(deterministicAudit)}）</p>` : "";
  return `<section class="human-review-panel" aria-live="polite">
    <div class="human-review-heading"><div><p class="pane-kicker">HUMAN IN THE LOOP</p><h3>人工复核</h3></div><span class="review-state review-${escapeAttr(status)}">${escapeHtml(REVIEW_LABELS[status] || REVIEW_LABELS.unreviewed)}</span></div>
    <p class="review-rule">接受后结束；提交修改建议只生成一个新 Round，Agent 不会自审，也不会自动重试。</p>
    <div class="review-candidate"><span>当前候选</span><strong>Round ${candidateRound}</strong><span>audit ${escapeHtml(deterministicAudit)}</span>${accepted}</div>
    <label class="review-feedback"><span>修改建议</span><textarea id="review-feedback" placeholder="例如：把点 E 的标签向左移，删除遮挡辅助线的说明文字。" ${controls.feedbackDisabled ? "disabled" : ""}>${escapeHtml(draft)}</textarea></label>
    ${reason}${message}
    <div class="human-review-actions">
      <button class="review-button review-accept" id="review-accept" type="button" ${controls.acceptDisabled || state.reviewSubmitting ? "disabled" : ""}>接受当前图</button>
      <button class="review-button review-submit" id="review-submit" type="button" ${controls.submitDisabled || state.reviewSubmitting ? "disabled" : ""}>提交给 Agent</button>
    </div>
    ${codexTaskBinding(review)}
  </section>`;
}

function codexTaskBinding(review) {
  const creating = state.reviewSubmitting && state.reviewSubmittingDecision === "changes_requested";
  const task = DiagramReviewState.codexTaskBinding(review, creating);
  if (!task) return "";
  const persistedThreadId = String(review.agent_thread_id || task.threadId || "");
  const thread = persistedThreadId
    ? `<span class="codex-task-thread"><span>Thread ID</span><code class="codex-task-id" title="${escapeAttr(persistedThreadId)}">${escapeHtml(persistedThreadId)}</code></span>`
    : `<span class="codex-task-thread"><span>Thread ID</span><code class="codex-task-id">—</code></span>`;
  return `<div class="codex-task-binding codex-task-${escapeAttr(task.status)}" role="status">
    <span class="codex-task-summary"><strong>Codex 任务</strong><span>${escapeHtml(CODEX_TASK_LABELS[task.status] || task.label)}</span></span>${thread}
  </div>`;
}

function bindHumanReviewActions(job, candidateRound) {
  const textarea = el("review-feedback");
  if (!textarea) return;
  textarea.addEventListener("input", () => {
    state.reviewDrafts[reviewDraftKey()] = textarea.value;
  });
  el("review-accept")?.addEventListener("click", () => submitHumanReview("accepted", candidateRound));
  el("review-submit")?.addEventListener("click", () => submitHumanReview("changes_requested", candidateRound));
}

async function submitHumanReview(decision, baseRound) {
  const feedback = el("review-feedback")?.value.trim() || "";
  if (decision === "changes_requested" && !feedback) {
    showAlert("请输入修改建议");
    el("review-feedback")?.focus();
    return;
  }
  const actionKey = `${reviewDraftKey()}:${decision}`;
  const actionId = state.reviewActions[actionKey] || newActionId();
  state.reviewActions[actionKey] = actionId;
  state.reviewSubmitting = true;
  state.reviewSubmittingDecision = decision;
  renderDetail();
  try {
    await api("/api/human-review", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        folder: state.folder.path,
        job_id: state.job.job_id,
        action_id: actionId,
        decision,
        feedback: decision === "accepted" ? "" : feedback,
        base_round: baseRound,
      }),
    });
    delete state.reviewActions[actionKey];
    if (decision === "changes_requested") state.reviewDrafts[reviewDraftKey()] = "";
    clearAlert();
    await loadJob(state.job.job_id, false);
  } catch (error) {
    showAlert(`人工复核提交失败：${error.message}`);
  } finally {
    state.reviewSubmitting = false;
    state.reviewSubmittingDecision = "";
    renderDetail();
  }
}

function selectedCandidateRound(job) {
  return DiagramReviewState.candidateRound(job);
}

function candidateAudit(job) {
  const selected = selectedCandidateRound(job);
  const round = (job.rounds || []).find((item) => item.round_index === selected);
  const status = String(round?.audit?.status || "").toLowerCase();
  return ["pass", "ok", "success"].includes(status) ? "pass" : (round?.audit && Object.keys(round.audit).length ? "block" : "missing");
}

function reviewDraftKey() { return `${state.folder?.path || ""}/${state.job?.job_id || ""}`; }
function preserveCurrentReviewDraft() {
  const textarea = el("review-feedback");
  if (textarea && state.folder && state.job) DiagramReviewState.preserveReviewDraft(state.reviewDrafts, reviewDraftKey(), textarea.value);
}
function newActionId() { return globalThis.crypto?.randomUUID?.() || `review-${Date.now()}-${Math.random().toString(16).slice(2)}`; }

function renderRounds(job) {
  if (!job.rounds?.length) { el("detail-body").innerHTML = emptyState("○", "还没有轮次产物", "Round 生成后会在这里逐轮出现"); return; }
  el("detail-body").innerHTML = `<div class="round-grid">${job.rounds.map((round) => `<article class="round-card">
    ${round.preview_path ? `<img src="${fileUrl(round.preview_path)}" alt="Round ${round.round_index} 预览">` : `<div class="preview-well"><div class="preview-placeholder"><strong>无预览</strong><span>检查该轮产物</span></div></div>`}
    <footer><strong>Round ${round.round_index}</strong>${statusBadge(round.status === "pass" ? "success" : round.status)}</footer>
  </article>`).join("")}</div>`;
}

function renderEvents(job) {
  if (!job.events?.length) { el("detail-body").innerHTML = emptyState("⋮", "还没有 workflow event", "workflow_events.jsonl 更新后会显示时间线"); return; }
  el("detail-body").innerHTML = `<ol class="event-list">${job.events.map((event) => `<li class="event-item"><span class="event-name">${escapeHtml(event.event || "event")}</span><time class="event-time">${escapeHtml(event.ts || "")}</time>${event.status ? ` ${statusBadge(normalizeEventStatus(event.status))}` : ""}<p class="event-message">${escapeHtml(event.message || event.error || summarizeEvent(event))}</p></li>`).join("")}</ol>`;
}

function renderArtifacts(job) {
  if (!job.artifact_groups?.length) { el("detail-body").innerHTML = emptyState("▤", "没有可显示的中间产物", "Job 文件出现后会自动分组"); return; }
  el("detail-body").innerHTML = job.artifact_groups.map((group, index) => `<details class="artifact-group" ${index < 3 ? "open" : ""}><summary>${escapeHtml(group.name)} · ${group.items.length}</summary><ul class="artifact-list">${group.items.map((item) => `<li><button class="artifact-button" type="button" data-artifact="${escapeAttr(item.path)}" data-kind="${escapeAttr(item.kind)}"><code>${escapeHtml(item.path.replace(`build/diagram/jobs/${job.job_id}/`, ""))}</code><span>${formatBytes(item.size)}</span></button></li>`).join("")}</ul></details>`).join("");
  el("detail-body").querySelectorAll("[data-artifact]").forEach((button) => button.addEventListener("click", () => openArtifact(button.dataset.artifact, button.dataset.kind)));
}

function renderPerformance(job) {
  const renderer = job.performance?.renderer || {};
  const stages = Array.isArray(renderer.stages) ? renderer.stages : [];
  if (!stages.length) { el("detail-body").innerHTML = emptyState("⌁", "暂无性能数据", "生成 performance_profile.json 后会显示分阶段耗时"); return; }
  const max = Math.max(...stages.map((item) => Number(item.elapsed_ms) || 0), 1);
  el("detail-body").innerHTML = `<section class="detail-section"><h3><span>Renderer stages</span><span>${formatNumber(renderer.total_ms)} ms</span></h3>${stages.map((item) => `<div class="performance-bar"><label>${escapeHtml(item.name)}</label><span class="bar-track"><i class="bar-fill" style="width:${Math.max(1.5, (Number(item.elapsed_ms) || 0) / max * 100)}%"></i></span><output>${formatNumber(item.elapsed_ms)} ms</output></div>`).join("")}</section>`;
}

async function openArtifact(path, kind) {
  const dialog = el("artifact-dialog");
  el("artifact-title").textContent = path.split("/").pop();
  el("artifact-kind").textContent = kind.toUpperCase();
  el("artifact-meta").textContent = path;
  const content = el("artifact-content");
  if (kind === "image") content.innerHTML = `<img src="${fileUrl(path)}" alt="${escapeAttr(path)}">`;
  else if (kind === "pdf") content.innerHTML = `<iframe src="${fileUrl(path)}" title="${escapeAttr(path)}"></iframe>`;
  else if (kind === "text") {
    content.innerHTML = `<div class="empty-state"><span class="empty-symbol">…</span><strong>正在读取</strong></div>`;
    try {
      const payload = await api(`/api/content?folder=${encodeURIComponent(state.folder.path)}&path=${encodeURIComponent(path)}`);
      el("artifact-meta").textContent = `${payload.path} · ${formatBytes(payload.size)} · ${payload.modified_at}${payload.truncated ? " · 已截断" : ""}`;
      content.innerHTML = `<pre>${escapeHtml(prettyText(payload.content, path))}</pre>`;
    } catch (error) { content.innerHTML = `<div class="empty-state error-state"><strong>读取失败</strong><span>${escapeHtml(error.message)}</span></div>`; }
  } else content.innerHTML = `<div class="empty-state"><strong>二进制产物</strong><a href="${fileUrl(path)}" target="_blank" rel="noreferrer">在新窗口打开</a></div>`;
  if (!dialog.open) dialog.showModal();
}

function renderEmptyWorkspace() {
  el("folder-summary").innerHTML = "";
  el("job-grid").innerHTML = emptyState("⌕", "输入关键词查找作业目录", "例如：比例辅助线");
  el("detail-body").innerHTML = emptyState("◇", "选择一张图查看完整链路", "中间产物、轮次和事件会显示在这里");
  el("copy-path").disabled = true;
}

function renderJobEmpty() {
  el("detail-title").textContent = "Job 详情";
  el("detail-body").innerHTML = emptyState("◇", "选择一张图查看完整链路", "中间产物、轮次和事件会显示在这里");
  el("copy-path").disabled = true;
}

function statusBadge(status) {
  const normalized = STATUS_LABELS[status] ? status : (status === "pass" || status === "ok" ? "success" : "incomplete");
  return `<span class="status-badge status-${normalized}">${STATUS_LABELS[normalized]}</span>`;
}

function warningBadge(label) { return `<span class="warning-badge">△ ${escapeHtml(label)}</span>`; }

function stageDetail(stages = {}) {
  return `<div class="key-grid">${STAGES.map(([key, label]) => keyItem(label, STATUS_LABELS[stages[key]] || (stages[key] === "not_applicable" ? "不适用" : stages[key] || "等待中"))).join("")}</div>`;
}

function keyItem(label, value) { return `<div class="key-item"><span>${escapeHtml(label)}</span><b>${escapeHtml(String(value))}</b></div>`; }
function emptyState(symbol, title, hint) { return `<div class="empty-state"><span class="empty-symbol">${symbol}</span><strong>${escapeHtml(title)}</strong><span>${escapeHtml(hint)}</span></div>`; }
function fileUrl(path) { return `/api/file?folder=${encodeURIComponent(state.folder.path)}&path=${encodeURIComponent(path)}`; }

async function api(url, options = {}) {
  const response = await fetch(url, { ...options, headers: { Accept: "application/json", ...(options.headers || {}) } });
  if (!response.ok) {
    let message = `${response.status} ${response.statusText}`;
    try { message = (await response.json()).detail || message; } catch (_) { /* keep HTTP message */ }
    throw new Error(message);
  }
  return response.json();
}

function copySelectedPath() {
  if (!state.folder) return;
  const path = state.job ? `${state.folder.absolute_path}/build/diagram/jobs/${state.job.job_id}` : state.folder.absolute_path;
  navigator.clipboard.writeText(path).then(() => { el("copy-path").textContent = "已复制"; setTimeout(() => { el("copy-path").textContent = "复制路径"; }, 1200); });
}

function showAlert(message) { el("global-alert").hidden = false; el("global-alert").textContent = message; }
function clearAlert() { el("global-alert").hidden = true; el("global-alert").textContent = ""; }
function normalizeEventStatus(status) { return ["ok", "pass", "success"].includes(String(status).toLowerCase()) ? "success" : ["failed", "error"].includes(String(status).toLowerCase()) ? "failed" : "running"; }
function summarizeEvent(event) { return Object.entries(event).filter(([key]) => !["ts", "event", "status"].includes(key)).slice(0, 3).map(([key, value]) => `${key}: ${typeof value === "object" ? JSON.stringify(value) : value}`).join(" · "); }
function formatClock(date) { return new Intl.DateTimeFormat("zh-CN", { hour: "2-digit", minute: "2-digit", second: "2-digit" }).format(date); }
function formatRelative(epoch) { if (!epoch) return "未知"; const seconds = Math.max(0, Date.now() / 1000 - epoch); if (seconds < 60) return `${Math.floor(seconds)} 秒前`; if (seconds < 3600) return `${Math.floor(seconds / 60)} 分钟前`; if (seconds < 86400) return `${Math.floor(seconds / 3600)} 小时前`; return `${Math.floor(seconds / 86400)} 天前`; }
function formatDuration(ms) { if (ms == null) return "—"; return ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(1)} s`; }
function formatNumber(value) { return Number(value || 0).toLocaleString("zh-CN", { maximumFractionDigits: 2 }); }
function formatBytes(bytes) { const value = Number(bytes || 0); if (value < 1024) return `${value} B`; if (value < 1024 ** 2) return `${(value / 1024).toFixed(1)} KB`; return `${(value / 1024 ** 2).toFixed(1)} MB`; }
function prettyText(content, path) { if (path.endsWith(".json")) { try { return JSON.stringify(JSON.parse(content), null, 2); } catch (_) { return content; } } return content; }
function debounce(fn, wait) { let timer; return (...args) => { clearTimeout(timer); timer = setTimeout(() => fn(...args), wait); }; }
function escapeHtml(value) { return String(value ?? "").replace(/[&<>'"]/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" }[char])); }
function escapeAttr(value) { return escapeHtml(value); }
