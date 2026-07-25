const state = {
  banks: [],
  detail: null,
  itemIndex: 0,
  requestToken: 0,
  submittingReview: false,
  selectedImageSlot: null,
  savingImage: false,
};
const byId = (id) => document.getElementById(id);
let mathRenderQueue = Promise.resolve();
let mathRenderEpoch = 0;
let audioContext = null;

function setText(id, value) { byId(id).textContent = value ?? ""; }

function formatReviewText(value) {
  const counters = [];
  const withFillinBlanks = String(value ?? "").replace(
    /\\fillin(?:\[[^\]]*\])?(?:\{[^}]*\})?/g,
    "＿＿＿＿＿＿",
  ).replace(/\\because/g, "∵").replace(/\\therefore/g, "∴");
  return withFillinBlanks.replace(
    /\\begin\{enumerate\}(?:\[[^\]]*\])?|\\end\{enumerate\}|\\item(?:\s*\[[^\]]*\])?/g,
    (token) => {
      if (token.startsWith("\\begin{enumerate}")) {
        counters.push(0);
        return "\n";
      }
      if (token.startsWith("\\end{enumerate}")) {
        counters.pop();
        return "\n";
      }
      if (!counters.length) return token;
      const depth = counters.length - 1;
      counters[depth] += 1;
      return `\n${"　".repeat(depth)}（${counters[depth]}）`;
    },
  );
}

function choiceLabel(key, index) {
  const normalized = String(key ?? "").trim().toUpperCase();
  return /^[A-Z]$/.test(normalized)
    ? normalized
    : String.fromCharCode("A".charCodeAt(0) + index);
}

function stripEmbeddedChoiceLabel(value) {
  return String(value ?? "").replace(
    /^\s*(?:(?:[A-Da-d]|[0-3])\s*[.、．]\s*|[（(]\s*(?:[A-Da-d]|[0-3])\s*[）)]\s*)/,
    "",
  );
}

function ensureAudioContext() {
  const AudioContextClass = window.AudioContext || window.webkitAudioContext;
  if (!AudioContextClass) return null;
  if (!audioContext) audioContext = new AudioContextClass();
  if (audioContext.state === "suspended") void audioContext.resume();
  return audioContext;
}

function playApprovalSound() {
  const context = ensureAudioContext();
  if (!context) return;
  const start = context.currentTime;
  [
    { frequency: 660, offset: 0, duration: 0.1 },
    { frequency: 880, offset: 0.105, duration: 0.16 },
  ].forEach(({ frequency, offset, duration }) => {
    const oscillator = context.createOscillator();
    const gain = context.createGain();
    oscillator.type = "sine";
    oscillator.frequency.setValueAtTime(frequency, start + offset);
    gain.gain.setValueAtTime(0.0001, start + offset);
    gain.gain.exponentialRampToValueAtTime(0.13, start + offset + 0.018);
    gain.gain.exponentialRampToValueAtTime(0.0001, start + offset + duration);
    oscillator.connect(gain).connect(context.destination);
    oscillator.start(start + offset);
    oscillator.stop(start + offset + duration);
  });
}

function playPageTurnSound() {
  const context = ensureAudioContext();
  if (!context) return;
  const duration = 0.16;
  const frameCount = Math.floor(context.sampleRate * duration);
  const buffer = context.createBuffer(1, frameCount, context.sampleRate);
  const samples = buffer.getChannelData(0);
  for (let index = 0; index < frameCount; index += 1) {
    const progress = index / frameCount;
    const envelope = Math.sin(Math.PI * progress) * (1 - 0.55 * progress);
    samples[index] = (Math.random() * 2 - 1) * envelope;
  }
  const source = context.createBufferSource();
  const filter = context.createBiquadFilter();
  const gain = context.createGain();
  source.buffer = buffer;
  filter.type = "bandpass";
  filter.frequency.setValueAtTime(1800, context.currentTime);
  filter.frequency.exponentialRampToValueAtTime(650, context.currentTime + duration);
  filter.Q.value = 0.75;
  gain.gain.setValueAtTime(0.075, context.currentTime);
  gain.gain.exponentialRampToValueAtTime(0.0001, context.currentTime + duration);
  source.connect(filter).connect(gain).connect(context.destination);
  source.start();
}

function badge(text) {
  const node = document.createElement("span");
  node.className = "badge";
  node.textContent = text;
  return node;
}

function preview(rootId, url, emptyText, alt) {
  const root = byId(rootId);
  root.replaceChildren();
  if (!url) {
    root.textContent = emptyText;
    return;
  }
  const image = document.createElement("img");
  image.src = url;
  image.alt = alt;
  image.addEventListener("error", () => { root.replaceChildren(document.createTextNode("预览文件暂不可用")); });
  root.append(image);
}

function appendWordEvidence(rootId, entries) {
  const root = byId(rootId);
  (entries || []).forEach((entry) => {
    const article = document.createElement("article");
    article.className = "source-text";
    const title = document.createElement("strong");
    title.textContent = entry.title || "Word 来源";
    const body = document.createElement("pre");
    body.className = "source-text";
    body.textContent = formatReviewText(entry.text || "");
    article.append(title, body);
    root.append(article);
  });
}

function imageSlotKey(itemId, target, index) {
  return `${itemId}:${target}:${index}`;
}

function updateSlotSelection() {
  document.querySelectorAll("[data-image-slot]").forEach((slot) => {
    const selected = slot.dataset.imageSlot === state.selectedImageSlot?.key;
    slot.classList.toggle("is-selected", selected);
    slot.setAttribute("aria-selected", String(selected));
    const hint = slot.querySelector(".slot-paste-hint");
    if (hint) {
      hint.textContent = selected
        ? "已选中 · ⌘V 粘贴替换"
        : "点击选中 · ⌘V 替换";
    }
  });
}

function selectImageSlot(target, index, label) {
  const item = state.detail?.items?.[state.itemIndex];
  if (!item || state.detail.kind !== "staging_exam" || state.savingImage) return;
  state.selectedImageSlot = {
    target,
    index,
    itemId: item.id,
    label,
    key: imageSlotKey(item.id, target, index),
  };
  updateSlotSelection();
  setText("review-message", `${label} 已选中，直接按 ⌘V / Ctrl+V 粘贴图片。`);
}

function wireImageSlot(slot, target, index, label) {
  slot.dataset.imageSlot = imageSlotKey(
    state.detail.items[state.itemIndex].id,
    target,
    index,
  );
  slot.tabIndex = 0;
  slot.setAttribute("role", "option");
  slot.setAttribute("aria-label", `${label}，点击选中后粘贴`);
  slot.addEventListener("click", () => selectImageSlot(target, index, label));
  slot.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      selectImageSlot(target, index, label);
    }
  });
}

function imageDeleteButton(target, index, label) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "image-delete-button";
  button.setAttribute("aria-label", `删除${label}`);
  button.title = `删除${label}`;
  button.textContent = "×";
  button.addEventListener("click", (event) => {
    event.stopPropagation();
    void deleteImageSlot(target, index, label);
  });
  return button;
}

function imageAddSlot(target, index, label) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "image-add-slot";
  button.dataset.imageSlot = imageSlotKey(
    state.detail.items[state.itemIndex].id,
    target,
    index,
  );
  button.setAttribute("aria-selected", "false");
  button.setAttribute("aria-label", `${label}，点击选中后粘贴`);
  const plus = document.createElement("span");
  plus.className = "image-add-icon";
  plus.textContent = "+";
  const text = document.createElement("span");
  text.textContent = label;
  const hint = document.createElement("small");
  hint.textContent = "选中后按 ⌘V";
  button.append(plus, text, hint);
  button.addEventListener("click", () => selectImageSlot(target, index, label));
  return button;
}

function previewGallery(rootId, entries, emptyText, altPrefix, options = {}) {
  const root = byId(rootId);
  root.replaceChildren();
  root.classList.toggle(
    "preview-gallery",
    Boolean((entries || []).length || options.emptyTarget),
  );
  if (!(entries || []).length) {
    if (options.emptyTarget) {
      root.append(imageAddSlot(
        options.emptyTarget,
        options.emptyIndex || 0,
        options.emptyLabel || "添加图片",
      ));
    } else {
      root.textContent = emptyText;
    }
    updateSlotSelection();
    return;
  }
  entries.forEach((entry, index) => {
    const figure = document.createElement("figure");
    figure.className = "preview-card";
    const image = document.createElement("img");
    image.src = entry.url;
    image.alt = `${altPrefix} ${index + 1}`;
    image.addEventListener("error", () => {
      figure.replaceChildren(document.createTextNode("预览文件暂不可用"));
    });
    const caption = document.createElement("figcaption");
    caption.textContent = entry.title || `第 ${index + 1} 步`;
    if (entry.edit_target) {
      const label = entry.title || `${altPrefix} ${index + 1}`;
      wireImageSlot(figure, entry.edit_target, entry.edit_index, label);
      figure.append(imageDeleteButton(entry.edit_target, entry.edit_index, label));
      const hint = document.createElement("span");
      hint.className = "slot-paste-hint";
      hint.textContent = "点击选中 · ⌘V 替换";
      figure.append(image, caption, hint);
    } else {
      figure.append(image, caption);
    }
    root.append(figure);
  });
  if (options.appendTarget) {
    root.append(imageAddSlot(
      options.appendTarget,
      entries.length,
      options.appendLabel || "添加图片",
    ));
  }
  updateSlotSelection();
}

function renderList() {
  const list = byId("question-list");
  list.replaceChildren();
  state.detail.items.forEach((item, index) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "question-row";
    button.setAttribute("aria-current", String(index === state.itemIndex));
    const heading = document.createElement("span");
    heading.className = "row-heading";
    const id = document.createElement("span");
    id.className = "row-id";
    id.textContent = item.id;
    heading.append(id);
    const title = document.createElement("span");
    title.className = "row-title";
    title.textContent = item.title || item.id;
    const meta = document.createElement("span");
    meta.className = "row-meta";
    const review = item.review || {};
    const reviewLabel = state.detail.kind === "staging_exam"
      ? (review.stale ? "已过期" : ({ approved: "已通过", rejected: "待修改", invalid: "记录异常" }[review.status] || "待审核"))
      : "";
    meta.textContent = [reviewLabel, ...(item.skill_tags || []).slice(0, 3)].filter(Boolean).join(" · ");
    button.append(heading, title, meta);
    button.addEventListener("mouseenter", () => selectItem(index));
    button.addEventListener("focus", () => selectItem(index));
    button.addEventListener("click", () => selectItem(index));
    list.append(button);
  });
}

function applyItem(item, itemIndex) {
  if (!item) return;
  setText("item-id", item.id);
  setText("item-title", item.title || item.id);
  setText("stem", formatReviewText(item.stem_latex || "题干不可用"));
  setText("answer", formatReviewText(item.answer || "暂无答案"));
  setText("explanation", formatReviewText(item.explanation || "暂无解析"));
  setText("position-summary", `${itemIndex + 1} / ${state.detail.items.length}`);
  const error = byId("load-error");
  error.hidden = !item.load_error;
  error.textContent = item.load_error ? `本题读取失败：${item.load_error}` : "";
  const badges = byId("item-badges");
  const badgeNodes = [
    item.difficulty ? badge(item.difficulty) : null,
    item.points !== undefined ? badge(`${item.points} 分`) : null,
    ...(item.skill_tags || []).slice(0, 4).map(badge),
  ].filter(Boolean);
  badges.replaceChildren(...badgeNodes);
  const staging = state.detail.kind === "staging_exam";
  const promptAlert = byId("prompt-review-alert");
  const promptNotes = byId("prompt-review-notes");
  const needsHumanCrop = staging && item.prompt_status === "needs_human_crop";
  promptAlert.hidden = !needsHumanCrop;
  promptNotes.replaceChildren();
  if (needsHumanCrop) {
    (item.prompt_review_notes || ["请对照原题截图人工补裁题图。"]).forEach((note) => {
      const row = document.createElement("li");
      row.textContent = note;
      promptNotes.append(row);
    });
  }
  byId("source-question-section").hidden = !staging;
  if (staging) {
    previewGallery(
      "source-question-preview",
      item.source_question_previews || [],
      "原题截图不可用",
      `${item.id} 原题截图`,
    );
    appendWordEvidence("source-question-preview", item.source_question_texts || []);
  }
  const choices = byId("choices");
  choices.replaceChildren();
  const choiceEntries = Object.entries(item.choices || {});
  byId("choices-section").hidden = !choiceEntries.length;
  choiceEntries.forEach(([key, value], index) => {
    const row = document.createElement("li");
    row.textContent = `${choiceLabel(key, index)}. ${formatReviewText(stripEmbeddedChoiceLabel(value))}`;
    choices.append(row);
  });
  const steps = byId("solution-steps");
  steps.replaceChildren();
  if (!(item.solution_steps || []).length) {
    const empty = document.createElement("li");
    empty.textContent = "暂无分步解答";
    steps.append(empty);
  } else {
    item.solution_steps.forEach((step) => {
      const row = document.createElement("li");
      const title = document.createElement("span");
      title.className = "step-title";
      title.textContent = step.title;
      const content = document.createElement("span");
      content.className = "source-text";
      content.textContent = formatReviewText(step.content);
      row.append(title, content);
      if (step.preview_url) {
        const figure = document.createElement("figure");
        figure.className = "step-preview";
        const slotLabel = step.preview_title || "解析图";
        const image = document.createElement("img");
        image.src = step.preview_url;
        image.alt = `${item.id} ${slotLabel}`;
        image.addEventListener("error", () => {
          figure.replaceChildren(document.createTextNode("解析图暂不可用"));
        });
        const caption = document.createElement("figcaption");
        caption.textContent = slotLabel;
        if (staging) {
          wireImageSlot(figure, step.edit_target, step.edit_index, slotLabel);
          figure.append(imageDeleteButton(step.edit_target, step.edit_index, slotLabel));
          const hint = document.createElement("span");
          hint.className = "slot-paste-hint";
          hint.textContent = "点击选中 · ⌘V 替换";
          figure.append(image, caption, hint);
        } else {
          figure.append(image, caption);
        }
        row.append(figure);
      } else if (staging) {
        row.append(imageAddSlot(
          step.edit_target,
          step.edit_index,
          step.preview_title || "添加解析图",
        ));
      }
      steps.append(row);
    });
  }
  const notes = byId("solution-notes");
  notes.replaceChildren();
  const noteEntries = item.solution_notes || [];
  byId("solution-notes-section").hidden = !noteEntries.length;
  noteEntries.forEach((note) => {
    const row = document.createElement("li");
    if (typeof note === "string") {
      row.textContent = formatReviewText(note);
    } else {
      const title = note?.title ? `${note.title}：` : "";
      row.textContent = formatReviewText(
        `${title}${note?.content_latex || note?.content || note?.latex || ""}`,
      );
    }
    notes.append(row);
  });
  if (staging) {
    previewGallery(
      "prompt-preview",
      item.prompt_previews || [],
      "本题无题图",
      `${item.id} 题图`,
      { emptyTarget: "prompt", emptyLabel: "添加题图" },
    );
  } else {
    preview("prompt-preview", item.prompt_preview_url, "本题无题图", `${item.id} 题图`);
  }
  const solutionPreviews = (item.solution_previews || []).length
    ? item.solution_previews
    : (item.solution_preview_url ? [{ title: "解答图", url: item.solution_preview_url }] : []);
  setText("solution-preview-title", staging ? "官方解答原图" : "解答图");
  previewGallery(
    "solution-preview",
    solutionPreviews,
    staging ? "官方解答原图不可用" : "本题无解答图",
    staging ? `${item.id} 官方解答原图` : `${item.id} 解答图`,
  );
  if (staging) {
    appendWordEvidence("solution-preview", item.official_solution_texts || []);
  }
  const reviewCard = byId("review-card");
  reviewCard.hidden = !staging;
  if (staging) {
    const review = item.review || {};
    const statusText = review.stale
      ? "已过期，请重新审核"
      : ({ approved: "已通过", rejected: "已要求修改", invalid: "审核记录异常" }[review.status] || "待审核");
    setText("review-status", statusText);
    byId("review-status").dataset.status = review.stale ? "stale" : (review.status || "pending");
    setText("review-message", review.error || "");
  }
  byId("previous-item").disabled = itemIndex === 0;
  byId("next-item").disabled = itemIndex === state.detail.items.length - 1;
  [...document.querySelectorAll(".question-row")].forEach((row, index) => {
    row.setAttribute("aria-current", String(index === itemIndex));
  });
}

function setReviewControlsDisabled(disabled) {
  [byId("approve-item"), byId("reject-item"), byId("confirm-revision")].forEach((button) => {
    button.disabled = disabled;
  });
}

function reviewNeedsAttention(item) {
  const review = item?.review || {};
  return Boolean(review.stale) || !["approved", "rejected"].includes(review.status);
}

function findNextReviewIndex(currentIndex) {
  const items = state.detail?.items || [];
  for (let offset = 1; offset < items.length; offset += 1) {
    const candidateIndex = (currentIndex + offset) % items.length;
    if (reviewNeedsAttention(items[candidateIndex])) return candidateIndex;
  }
  return -1;
}

function updateStagingProgress() {
  if (state.detail?.kind !== "staging_exam") return;
  const counts = { approved: 0, rejected: 0, stale: 0 };
  state.detail.items.forEach((item) => {
    const review = item.review || {};
    if (review.stale) counts.stale += 1;
    else if (review.status === "approved") counts.approved += 1;
    else if (review.status === "rejected") counts.rejected += 1;
  });
  state.detail.approved_count = counts.approved;
  state.detail.rejected_count = counts.rejected;
  state.detail.stale_count = counts.stale;
  const progress = `${counts.approved} 通过 · ${counts.rejected} 待修改 · ${counts.stale} 过期`;
  setText("bank-meta", [state.detail.grade, progress].filter(Boolean).join(" · "));
}

async function submitReview(decision, note = "") {
  const item = state.detail?.items?.[state.itemIndex];
  if (!item || state.detail.kind !== "staging_exam" || state.submittingReview) return false;
  const reviewedIndex = state.itemIndex;
  const reviewedItemId = item.id;
  state.submittingReview = true;
  setReviewControlsDisabled(true);
  if (decision === "approved") ensureAudioContext();
  setText("review-message", "正在保存审核记录…");
  setText("revision-error", "");
  try {
    const response = await fetch(
      `/api/banks/${encodeURIComponent(state.detail.id)}/items/${encodeURIComponent(item.id)}/review`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ decision, note }),
      },
    );
    if (!response.ok) throw new Error(await response.text());
    item.review = await response.json();
    updateStagingProgress();
    const nextReviewIndex = findNextReviewIndex(reviewedIndex);
    if (decision === "rejected") byId("revision-dialog").close();
    if (nextReviewIndex >= 0) state.itemIndex = nextReviewIndex;
    renderList();
    renderItem();
    if (decision === "approved") {
      playApprovalSound();
    }
    if (nextReviewIndex >= 0) {
      window.setTimeout(playPageTurnSound, decision === "approved" ? 280 : 0);
    }
    await mathRenderQueue;
    const decisionLabel = decision === "approved" ? "通过" : "要求修改";
    const destination = nextReviewIndex >= 0
      ? `已跳到 ${state.detail.items[nextReviewIndex].id}。`
      : "本卷已经没有待审核题目。";
    setText("review-message", `${reviewedItemId} 已保存：${decisionLabel}。${destination}`);
    return true;
  } catch (error) {
    setText("review-message", `保存失败：${error.message}`);
    if (decision === "rejected") setText("revision-error", `保存失败：${error.message}`);
    return false;
  } finally {
    state.submittingReview = false;
    setReviewControlsDisabled(false);
  }
}

function renderItem() {
  const item = state.detail.items[state.itemIndex];
  const itemIndex = state.itemIndex;
  const epoch = ++mathRenderEpoch;
  mathRenderQueue = mathRenderQueue.then(async () => {
    if (epoch !== mathRenderEpoch) return;
    const reader = byId("reader");
    if (window.MathJax?.typesetClear) window.MathJax.typesetClear([reader]);
    applyItem(item, itemIndex);
    if (!window.MathJax?.typesetPromise) return;
    await window.MathJax.typesetPromise([reader]);
  }).catch((error) => {
    console.warn("MathJax typesetting failed", error);
  });
}

function selectItem(index) {
  if (!state.detail || index < 0 || index >= state.detail.items.length) return;
  if (index !== state.itemIndex) state.selectedImageSlot = null;
  state.itemIndex = index;
  renderItem();
}

function navigateItem(delta) {
  if (!state.detail) return false;
  const nextIndex = state.itemIndex + delta;
  if (nextIndex < 0 || nextIndex >= state.detail.items.length) return false;
  selectItem(nextIndex);
  playPageTurnSound();
  return true;
}

function openRevisionDialog() {
  const item = state.detail?.items?.[state.itemIndex];
  const dialog = byId("revision-dialog");
  if (!item || state.detail.kind !== "staging_exam" || state.submittingReview || dialog.open) return;
  const review = item.review || {};
  const existingNote = review.status === "rejected" && !review.stale ? (review.note || "") : "";
  setText("revision-item-label", `${item.id} · ${item.title || item.id}`);
  byId("revision-note").value = existingNote;
  setText("revision-error", "");
  dialog.showModal();
  window.setTimeout(() => byId("revision-note").focus(), 0);
}

async function uploadPastedImage(blob) {
  const target = state.selectedImageSlot;
  if (
    !target
    || !(blob instanceof Blob)
    || !blob.type.startsWith("image/")
    || state.savingImage
  ) return;
  state.savingImage = true;
  setText("review-message", `${target.label} 正在保存…`);
  try {
    const response = await fetch(
      `/api/banks/${encodeURIComponent(state.detail.id)}/items/${encodeURIComponent(target.itemId)}/images/${encodeURIComponent(target.target)}/${target.index}`,
      {
        method: "POST",
        headers: { "Content-Type": blob.type || "image/png" },
        body: blob,
      },
    );
    if (!response.ok) throw new Error(await response.text());
    const updatedItem = await response.json();
    const updatedIndex = state.detail.items.findIndex((item) => item.id === target.itemId);
    if (updatedIndex >= 0) state.detail.items[updatedIndex] = updatedItem;
    updateStagingProgress();
    renderList();
    renderItem();
    await mathRenderQueue;
    setText("review-message", `${target.label} 已保存；槽位仍保持选中，可继续粘贴替换。`);
  } catch (error) {
    setText("review-message", `图片保存失败：${error.message}`);
  } finally {
    state.savingImage = false;
  }
}

async function deleteImageSlot(targetName, index, label) {
  const item = state.detail?.items?.[state.itemIndex];
  if (!item || state.detail.kind !== "staging_exam" || state.savingImage) return;
  state.savingImage = true;
  setText("review-message", `正在移除${label}…`);
  try {
    const response = await fetch(
      `/api/banks/${encodeURIComponent(state.detail.id)}/items/${encodeURIComponent(item.id)}/images/${encodeURIComponent(targetName)}/${index}`,
      { method: "DELETE" },
    );
    if (!response.ok) throw new Error(await response.text());
    const updatedItem = await response.json();
    const updatedIndex = state.detail.items.findIndex((candidate) => candidate.id === item.id);
    if (updatedIndex >= 0) state.detail.items[updatedIndex] = updatedItem;
    state.selectedImageSlot = null;
    updateStagingProgress();
    renderList();
    renderItem();
    await mathRenderQueue;
    setText("review-message", `${label}已移出槽位；原图片文件仍保留，可点击加号粘贴新图。`);
  } catch (error) {
    setText("review-message", `删除失败：${error.message}`);
  } finally {
    state.savingImage = false;
  }
}

function isEditableTarget(target) {
  if (!(target instanceof Element)) return false;
  return Boolean(target.closest("input, textarea, select, [contenteditable='true']"));
}

async function selectBank(bankId) {
  const token = ++state.requestToken;
  setText("page-status", "正在读取题库…");
  byId("page-status").hidden = false;
  byId("review-layout").hidden = true;
  try {
    const response = await fetch(`/api/banks/${encodeURIComponent(bankId)}`);
    if (!response.ok) throw new Error(await response.text());
    const detail = await response.json();
    if (token !== state.requestToken) return;
    state.detail = detail;
    state.itemIndex = 0;
    state.selectedImageSlot = null;
    const selectedUrl = new URL(window.location.href);
    selectedUrl.searchParams.set("bank", bankId);
    window.history.replaceState({}, "", selectedUrl);
    setText("topic-summary", detail.topic);
    const staging = detail.kind === "staging_exam";
    const progress = staging
      ? `${detail.approved_count || 0} 通过 · ${detail.rejected_count || 0} 待修改 · ${detail.stale_count || 0} 过期`
      : `${detail.enabled_count}/${detail.item_count} 题可用`;
    setText("bank-meta", [detail.grade, progress].filter(Boolean).join(" · "));
    setText("item-count", `${detail.item_count} 题`);
    if (!detail.items.length) {
      setText("page-status", "这个题库目前没有题目。");
      return;
    }
    byId("page-status").hidden = true;
    byId("review-layout").hidden = false;
    renderList();
    renderItem();
  } catch (error) {
    if (token !== state.requestToken) return;
    setText("page-status", `题库加载失败：${error.message}。可重新选择题库重试。`);
  }
}

async function loadBanks() {
  try {
    const response = await fetch("/api/banks");
    if (!response.ok) throw new Error(await response.text());
    const payload = await response.json();
    state.banks = payload.banks;
    const select = byId("bank-select");
    select.replaceChildren();
    if (!state.banks.length) {
      const option = document.createElement("option");
      option.textContent = "没有发现正式题库";
      select.append(option);
      setText("page-status", "artifacts/题库 下没有可预览的 question-bank.yaml。 ");
      return;
    }
    state.banks.forEach((bank) => {
      const option = document.createElement("option");
      option.value = bank.id;
      const prefix = bank.kind === "staging_exam" ? "试卷审核" : "专题题库";
      option.textContent = `${prefix}｜${bank.topic}（${bank.item_count} 题）`;
      select.append(option);
    });
    select.disabled = false;
    const requestedBankId = new URL(window.location.href).searchParams.get("bank");
    const initialBank = state.banks.find((bank) => bank.id === requestedBankId) || state.banks[0];
    select.value = initialBank.id;
    await selectBank(initialBank.id);
  } catch (error) {
    setText("page-status", `题库列表加载失败：${error.message}。请刷新页面重试。`);
  }
}

byId("bank-select").addEventListener("change", (event) => selectBank(event.target.value));
byId("previous-item").addEventListener("click", () => navigateItem(-1));
byId("next-item").addEventListener("click", () => navigateItem(1));
byId("approve-item").addEventListener("click", () => submitReview("approved", ""));
byId("reject-item").addEventListener("click", openRevisionDialog);
byId("cancel-revision").addEventListener("click", () => byId("revision-dialog").close());
byId("revision-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const note = byId("revision-note").value.trim();
  if (!note) {
    setText("revision-error", "请填写具体修改意见后再提交。");
    byId("revision-note").focus();
    return;
  }
  void submitReview("rejected", note);
});
byId("revision-note").addEventListener("input", () => setText("revision-error", ""));
byId("revision-note").addEventListener("keydown", (event) => {
  if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
    event.preventDefault();
    byId("revision-form").requestSubmit();
  }
});
byId("revision-dialog").addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !state.submittingReview) {
    event.preventDefault();
    byId("revision-dialog").close();
  }
});
document.addEventListener("paste", (event) => {
  if (
    event.defaultPrevented
    || isEditableTarget(event.target)
    || !state.selectedImageSlot
    || state.detail?.kind !== "staging_exam"
  ) return;
  const imageItem = [...(event.clipboardData?.items || [])].find(
    (item) => item.kind === "file" && item.type.startsWith("image/"),
  );
  if (!imageItem) {
    setText("review-message", "剪贴板中没有图片，请先复制截图再粘贴。");
    return;
  }
  event.preventDefault();
  void uploadPastedImage(imageItem.getAsFile());
});
document.addEventListener("keydown", (event) => {
  if (
    event.defaultPrevented
    || event.repeat
    || event.ctrlKey
    || event.metaKey
    || event.altKey
    || byId("revision-dialog").open
    || isEditableTarget(event.target)
  ) return;
  const key = event.key.toLowerCase();
  if (key === "a" && state.detail?.kind === "staging_exam") {
    event.preventDefault();
    void submitReview("approved", "");
  } else if (key === "r" && state.detail?.kind === "staging_exam") {
    event.preventDefault();
    openRevisionDialog();
  } else if (event.key === "ArrowLeft" && navigateItem(-1)) {
    event.preventDefault();
  } else if (event.key === "ArrowRight" && navigateItem(1)) {
    event.preventDefault();
  }
});
loadBanks();
