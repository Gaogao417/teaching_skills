const state = {
  banks: [],
  detail: null,
  itemIndex: 0,
  requestToken: 0,
  // applyFilters 用独立 token，避免与 selectBank 的 requestToken 互相取消
  // （两者并发时旧实现会把对方的请求判为 stale，导致列表卡在 disabled）。
  filterToken: 0,
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

function appendPageBadges(rootId, pages) {
  const root = byId(rootId);
  root.replaceChildren();
  (pages || []).forEach((page) => {
    const link = document.createElement("a");
    link.className = "badge page-badge";
    link.href = page.url;
    link.target = "_blank";
    link.rel = "noopener";
    link.textContent = `P${page.page}`;
    link.title = `原卷第 ${page.page} 页（点击新页打开整页图）`;
    root.append(link);
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
  slot.addEventListener("click", (event) => {
    event.stopPropagation();
    selectImageSlot(target, index, label);
  });
  slot.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      event.stopPropagation();
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

// 图片 section 配置：target → 显示名 + 是否单图（prompt 仅一张，其余可追加）。
const IMAGE_SECTION_CONFIG = {
  prompt: { label: "题图", single: true },
  official_solution: { label: "官方解答原图", single: false },
};

function emptyAddHint(label) {
  const wrap = document.createElement("div");
  wrap.className = "empty-add-hint";
  const icon = document.createElement("span");
  icon.className = "empty-add-icon";
  icon.textContent = "＋";
  const text = document.createElement("span");
  text.textContent = `点击此处添加${label}`;
  const small = document.createElement("small");
  small.textContent = "选中后按 ⌘V 粘贴";
  wrap.append(icon, text, small);
  return wrap;
}

// 给静态的 .image-section 挂一次点击监听：点击 section 空白处 → 追加图片
// （prompt 单图已有图时退化为替换 index 0）。来自图卡/删除按钮的点击由它们
// 自己 stopPropagation，不会冒泡到这里。
function wireImageSections() {
  document.querySelectorAll(".image-section[data-image-target]").forEach((section) => {
    const target = section.dataset.imageTarget;
    const config = IMAGE_SECTION_CONFIG[target] || { label: target, single: false };
    section.classList.toggle("is-single", config.single);
    section.tabIndex = 0;
    section.setAttribute("role", "option");
    section.setAttribute("aria-label", `${config.label}，点击选中后粘贴`);
    // 同步当前 item 的追加位 key，让 updateSlotSelection 能高亮 section 空白区。
    const item = state.detail?.items?.[state.itemIndex];
    if (item) {
      const count = section.querySelectorAll(".preview-card[data-image-slot]").length;
      const index = config.single && count > 0 ? 0 : count;
      section.dataset.imageSlot = imageSlotKey(item.id, target, index);
    } else {
      delete section.dataset.imageSlot;
    }
    if (section.dataset.imageWired) return;
    section.dataset.imageWired = "1";
    const trigger = () => {
      if (state.detail?.kind !== "staging_exam" || state.savingImage) return;
      const count = section.querySelectorAll(".preview-card[data-image-slot]").length;
      const index = config.single && count > 0 ? 0 : count;
      selectImageSlot(target, index, config.label);
      if (config.single && count > 0) {
        setText("review-message", `${config.label}只支持一张，将替换现有图片。直接按 ⌘V / Ctrl+V 粘贴。`);
      }
    };
    // 图卡/删除按钮各自 stopPropagation，所以这里只会收到空白区点击。
    section.addEventListener("click", trigger);
    section.addEventListener("keydown", (event) => {
      if (event.key !== "Enter" && event.key !== " ") return;
      event.preventDefault();
      trigger();
    });
  });
}

function previewGallery(rootId, entries, emptyText, altPrefix, options = {}) {
  const root = byId(rootId);
  root.replaceChildren();
  const list = entries || [];
  const section = root.closest(".image-section[data-image-target]");
  const editable = Boolean(options.editTarget);
  root.classList.toggle("preview-gallery", Boolean(list.length || editable));
  if (section) {
    section.classList.toggle("has-images", list.length > 0);
    section.classList.toggle("is-empty", editable && list.length === 0);
    section.classList.toggle("is-editable", editable);
  }
  if (!list.length) {
    if (editable) {
      root.append(emptyAddHint(options.editLabel || "图片"));
    } else {
      root.textContent = emptyText;
    }
    updateSlotSelection();
    return;
  }
  list.forEach((entry, index) => {
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
    appendPageBadges("source-question-page-badges", item.source_question_pages || []);
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
        const slotLabel = step.preview_title || "解析图";
        const figure = document.createElement("figure");
        figure.className = "step-preview is-empty";
        figure.append(emptyAddHint("解析图"));
        wireImageSlot(figure, step.edit_target, step.edit_index, slotLabel);
        row.append(figure);
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
      { editTarget: "prompt", editLabel: "题图" },
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
    staging ? { editTarget: "official_solution", editLabel: "官方解答原图" } : {},
  );
  if (staging) {
    appendPageBadges("solution-page-badges", item.official_solution_pages || []);
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
  wireImageSections();
  updateSlotSelection();
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

async function loadFacets() {
  try {
    const response = await fetch("/api/banks/facets");
    if (!response.ok) throw new Error(await response.text());
    const facets = await response.json();
    const gradeSelect = byId("filter-grade");
    const yearSelect = byId("filter-year");
    fillFacetOptions(gradeSelect, facets.grades || []);
    fillFacetOptions(yearSelect, facets.years || []);
    // 试卷类型下拉的枚举写死在 HTML 里；facets 仅用来启用/禁用它。
    byId("filter-grade").disabled = false;
    byId("filter-year").disabled = false;
    byId("filter-exam-type").disabled = false;
  } catch (error) {
    // facets 失败不阻断主流程，搜索 + 来源筛选仍可用。
    console.warn("facets 加载失败：", error.message);
  }
}

function fillFacetOptions(select, values) {
  const keepValue = select.value;
  const keep = Array.from(select.querySelectorAll("option")).find(
    (option) => option.value === keepValue,
  );
  select.replaceChildren();
  const placeholder = document.createElement("option");
  placeholder.value = "";
  placeholder.textContent = "全部";
  select.append(placeholder);
  values.forEach((value) => {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = value;
    select.append(option);
  });
  if (keep) select.value = keepValue;
}

function buildFilterParams() {
  const params = new URLSearchParams();
  const kind = byId("filter-kind").value;
  const grade = byId("filter-grade").value;
  const year = byId("filter-year").value;
  const examType = byId("filter-exam-type").value;
  const query = byId("search-input").value.trim();
  if (kind) params.set("kind", kind);
  if (grade) params.set("grade", grade);
  if (year) params.set("year", year);
  if (examType) params.set("exam_type", examType);
  if (query) params.set("q", query);
  return params;
}

function renderBankList(select) {
  select.replaceChildren();
  if (!state.banks.length) {
    const option = document.createElement("option");
    option.value = "";
    option.textContent = "没有匹配的题库";
    select.append(option);
    select.disabled = false;
    setText("page-status", "没有匹配的题库，可调整筛选项或检索词。");
    byId("page-status").hidden = false;
    byId("review-layout").hidden = true;
    return;
  }
  state.banks.forEach((bank) => {
    const option = document.createElement("option");
    option.value = bank.id;
    const prefix = bank.kind === "staging_exam" ? "试卷" : "专题";
    const meta = [bank.year, bank.exam_type, bank.grade].filter(Boolean).join("·");
    const tail = meta ? `｜${meta}` : "";
    option.textContent = `${prefix}｜${bank.topic}（${bank.item_count} 题）${tail}`;
    select.append(option);
  });
  select.disabled = false;
}

async function applyFilters() {
  const token = ++state.filterToken;
  const params = buildFilterParams();
  const select = byId("bank-select");
  // 过滤期间禁用列表 + 显示加载态，避免用户/测试在旧数据上误读。
  select.disabled = true;
  setText("page-status", "正在筛选题库…");
  byId("page-status").hidden = false;
  byId("review-layout").hidden = true;
  try {
    const response = await fetch(`/api/banks?${params.toString()}`);
    if (!response.ok) throw new Error(await response.text());
    const payload = await response.json();
    // 即便是过期请求也解锁列表，避免并发竞态时 select 卡在 disabled。
    if (token !== state.filterToken) {
      select.disabled = false;
      return;
    }
    state.banks = payload.banks || [];
    renderBankList(select);
    if (!state.banks.length) return;
    // 同步 URL：保留 ?bank= 用于深链分享，追加过滤参数。
    const url = new URL(window.location.href);
    const requestedBankId = url.searchParams.get("bank");
    const stillPresent = requestedBankId
      && state.banks.some((bank) => bank.id === requestedBankId);
    const initialBank = stillPresent
      ? state.banks.find((bank) => bank.id === requestedBankId)
      : state.banks[0];
    select.value = initialBank.id;
    // 把当前过滤态写回 URL（便于刷新/分享）。
    ["kind", "grade", "year", "exam_type"].forEach((key) => {
      const id = `filter-${key === "exam_type" ? "exam-type" : key}`;
      const value = byId(id).value;
      if (value) url.searchParams.set(key, value);
      else url.searchParams.delete(key);
    });
    const query = byId("search-input").value.trim();
    if (query) url.searchParams.set("q", query);
    else url.searchParams.delete("q");
    window.history.replaceState({}, "", url);
    byId("page-status").hidden = true;
    byId("review-layout").hidden = false;
    await selectBank(initialBank.id);
  } catch (error) {
    select.disabled = false;
    if (token !== state.filterToken) return;
    setText("page-status", `题库列表加载失败：${error.message}。请刷新页面重试。`);
  }
}

function debounce(fn, wait) {
  let timer = null;
  return (...args) => {
    clearTimeout(timer);
    timer = window.setTimeout(() => fn(...args), wait);
  };
}

async function loadBanks() {
  // 从 URL 恢复过滤态（支持深链 / 刷新）。
  const url = new URL(window.location.href);
  const restore = (id, key) => {
    const value = url.searchParams.get(key);
    if (value) byId(id).value = value;
  };
  restore("filter-kind", "kind");
  restore("filter-grade", "grade");
  restore("filter-year", "year");
  restore("filter-exam-type", "exam_type");
  const restoreQuery = url.searchParams.get("q");
  if (restoreQuery) byId("search-input").value = restoreQuery;
  await loadFacets();
  await applyFilters();
}

byId("bank-select").addEventListener("change", (event) => selectBank(event.target.value));
byId("filter-kind").addEventListener("change", () => { void applyFilters(); });
byId("filter-grade").addEventListener("change", () => { void applyFilters(); });
byId("filter-year").addEventListener("change", () => { void applyFilters(); });
byId("filter-exam-type").addEventListener("change", () => { void applyFilters(); });
byId("search-input").addEventListener("input", debounce(() => { void applyFilters(); }, 200));
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
