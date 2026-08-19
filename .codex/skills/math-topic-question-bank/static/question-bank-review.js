const state = {
  banks: [],
  // detail 是卷级目录（counts + items 的 id/title/review_status/stale），来自
  // ?directory=1（§8.3/§10.3 阶段 5）。完整单题（含 stem/answer/solution_steps/
  // prompt_previews）按需懒加载进 itemCache，navigateItem/applyItem 命中即用。
  detail: null,
  itemIndex: 0,
  itemCache: new Map(),
  requestToken: 0,
  // applyFilters 用独立 token，避免与 selectBank 的 requestToken 互相取消
  // （两者并发时旧实现会把对方的请求判为 stale，导致列表卡在 disabled）。
  filterToken: 0,
  // 单题懒加载 token：旧的单题请求完成后若 token 已变（用户切到别的题/卷），丢弃结果。
  itemLoadToken: 0,
  submittingReview: false,
  selectedImageSlot: null,
  savingImage: false,
};
// 原题来源 / 官方解答图廊：点击胶囊打开 dialog，可逐张翻看裁切截图 + 整页原图。
const sourceLightbox = { entries: [], index: 0 };
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

function badge(text, cls) {
  const node = document.createElement("span");
  node.className = cls ? `badge ${cls}` : "badge";
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

// 在「题目」 section 标题旁渲染单一「原卷来源页」胶囊：点击打开图廊，按页码顺序翻看所有来源图。
// word_evidence 的题干/解答分组不是业务需求（review ui 只做整卷溯源定位），故前端只渲染一个
// 合并视图：裁切截图（*_previews，{title,url}）+ 合并去重的整页来源（source_pages，
// {page,url}）。ingestion 对不同卷可能产出其中一种或两种都有，这里都收纳，谁有显示谁。
// 无任何数据（formal 卷或缺证据）则不渲染胶囊。
function renderSourceCapsules(item) {
  const root = byId("source-capsules");
  root.replaceChildren();
  const groups = [
    {
      label: "原卷来源页",
      crops: [
        ...((item.source_question_previews || [])),
        ...((item.official_solution_previews || [])),
      ],
      pages: item.source_pages,
    },
  ];
  groups.forEach(({ label, crops, pages }) => {
    const entries = [
      ...((crops || []).map((entry) => ({ url: entry.url, title: entry.title || label }))),
      ...((pages || []).map((entry) => ({ url: entry.url, title: `原卷第 ${entry.page} 页` }))),
    ];
    if (!entries.length) return;
    const capsule = document.createElement("span");
    capsule.className = "source-capsule";
    capsule.tabIndex = 0;
    capsule.setAttribute("role", "button");
    capsule.setAttribute("aria-label", `${label}，点击打开 ${entries.length} 张截图`);
    capsule.textContent = `${label} (${entries.length})`;
    const open = () => openSourceLightbox(label, entries);
    capsule.addEventListener("click", open);
    capsule.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        open();
      }
    });
    root.append(capsule);
  });
}

// 图廊渲染：把当前 index 的图填进 dialog。
function renderSourceLightbox() {
  const { entries, index } = sourceLightbox;
  const entry = entries[index];
  if (!entry) return;
  const image = byId("source-lightbox-image");
  image.src = entry.url;
  image.alt = entry.title;
  const openLink = byId("source-lightbox-open");
  openLink.href = entry.url;
  setText("source-lightbox-caption", entry.title);
  setText("source-lightbox-counter", `${index + 1} / ${entries.length}`);
  byId("source-lightbox-prev").disabled = index <= 0;
  byId("source-lightbox-next").disabled = index >= entries.length - 1;
}

function openSourceLightbox(label, entries) {
  if (!entries?.length) return;
  sourceLightbox.entries = entries;
  sourceLightbox.index = 0;
  setText("source-lightbox-title", label);
  renderSourceLightbox();
  byId("source-lightbox").showModal();
  window.setTimeout(() => byId("source-lightbox-close").focus(), 0);
}

function navigateSourceLightbox(delta) {
  const next = sourceLightbox.index + delta;
  if (next < 0 || next >= sourceLightbox.entries.length) return;
  sourceLightbox.index = next;
  renderSourceLightbox();
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

// 图片 section 配置：target → 显示名 + 是否单图（prompt 仅一张）。
// 解答图按题目管理，不再要求绑定到某一步；原题来源 / 官方解答整页仍走胶囊图廊，
// 不作为可编辑 image-section。
const IMAGE_SECTION_CONFIG = {
  prompt: { label: "题图", single: true },
  official_solution: { label: "解答图", single: false },
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
    // pending attribution: highlight the card and add a confidence-scaled badge.
    if (entry.attribution_state === "needs_review") {
      figure.classList.add("attribution-pending");
      if (entry.attribution_confidence === "low") {
        figure.classList.add("attribution-low");
      }
    }
    const image = document.createElement("img");
    image.src = entry.url;
    image.alt = `${altPrefix} ${index + 1}`;
    image.addEventListener("error", () => {
      figure.replaceChildren(document.createTextNode("预览文件暂不可用"));
    });
    const caption = document.createElement("figcaption");
    caption.textContent = entry.title || `第 ${index + 1} 步`;
    if (entry.attribution_state === "needs_review") {
      const badge = document.createElement("span");
      badge.className = "attribution-badge";
      badge.textContent = entry.attribution_confidence === "low"
        ? "低置信度，请核对归属"
        : "归因待确认";
      caption.append(badge);
    }
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

// 把目录项（{id,title,review_status,stale}）或完整 item（含 review{}）归一成评审标签。
// 目录项是轻量结构（§8.3），不带 review{} 子对象，用顶层 review_status/stale；完整 item
// 走 review.stale/review.status。两种来源都支持，renderList/findNextReviewIndex 通用。
function reviewLabelOf(item) {
  if (!item) return "";
  const staging = state.detail?.kind === "staging_exam";
  if (!staging) return "";
  const review = item.review || {};
  const stale = review.stale ?? item.stale ?? false;
  const status = review.status ?? item.review_status ?? "pending";
  if (stale) return "已过期";
  return { approved: "已通过", rejected: "待修改", invalid: "记录异常" }[status] || "待审核";
}

function reviewNeedsAttentionOf(item) {
  if (!item) return true;
  const review = item.review || {};
  const stale = review.stale ?? item.stale ?? false;
  const status = review.status ?? item.review_status ?? "pending";
  if (stale) return true;
  return !["approved", "rejected"].includes(status);
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
    // 目录项没有 skill_tags，只有完整题才有；已缓存的题显示标签，未缓存只显示评审标签。
    const cached = state.itemCache.get(item.id);
    const tags = cached?.skill_tags || [];
    // 小题讲解/解答状态：缺讲解或缺解答时在列表直接可见，便于定位待补题。
    // 目录项暂无该摘要，仅完整题（detail 或已缓存）显示，避免误标。
    const explanations = item.explanations_summary || cached?.explanations_summary;
    const explanationMarks = [];
    if (explanations?.missing_explanation) explanationMarks.push("缺讲解");
    if (explanations?.missing_solution_count) explanationMarks.push(`缺解答×${explanations.missing_solution_count}`);
    meta.textContent = [reviewLabelOf(item), ...tags.slice(0, 3), ...explanationMarks].filter(Boolean).join(" · ");
    if (explanationMarks.length) button.classList.add("needs-explanations");
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
  setText("clue", formatReviewText(item.clue || "暂无思路提示"));
  renderSubquestionPreview(item);
  // P2-03：staging 题目开放文本编辑（修订后重算 hash、旧审核置 stale）。
  const editToggle = byId("edit-text-toggle");
  editToggle.hidden = !(state.detail.kind === "staging_exam");
  editToggle.textContent = item.text_edited ? "编辑题干/答案文本（已修订）" : "编辑题干/答案文本";
  hideTextEditPanel();
  const locationIssues = byId("text-edit-location-issues");
  locationIssues.hidden = !(Array.isArray(item.source_location_issues) && item.source_location_issues.length);
  locationIssues.textContent = item.source_location_issues
    ? `来源页归属校验：${item.source_location_issues.join("；")}`
    : "";
  setText("position-summary", `${itemIndex + 1} / ${state.detail.items.length}`);
  const error = byId("load-error");
  error.hidden = !item.load_error;
  error.textContent = item.load_error ? `本题读取失败：${item.load_error}` : "";
  const badges = byId("item-badges");
  const badgeNodes = [
    item.difficulty ? badge(item.difficulty) : null,
    item.points !== undefined ? badge(`${item.points} 分`) : null,
    ...(item.skill_tags || []).slice(0, 4).map(badge),
    // pending image attributions: item-level hint that some figures await confirmation.
    item.pending_image_count ? badge(`归因待确认 ${item.pending_image_count}`, "attribution-pending-badge") : null,
  ].filter(Boolean);
  badges.replaceChildren(...badgeNodes);
  const staging = state.detail.kind === "staging_exam";
  renderTranscriptionIssues(item);
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
  renderSourceCapsules(item);
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
        // 解题步骤里的旧图只读显示，图片编辑统一走题目级“解答图”图库。
        figure.append(image, caption);
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
  // 题目级“解答图”图库：仅在 staging 显示。来源凭证（整页官方解答）仍由顶部胶囊提供。
  const solutionGallery = byId("official-solution-preview");
  if (solutionGallery?.closest(".image-section")) {
    solutionGallery.closest(".image-section").hidden = !staging;
  }
  if (staging) {
    previewGallery(
      "official-solution-preview",
      item.official_solution_previews || [],
      "暂无解答图",
      `${item.id} 解答图`,
      { editTarget: "official_solution", editLabel: "解答图" },
    );
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
    const quarantined = Boolean(state.detail.review_mode_active);
    byId("approve-item").disabled = quarantined;
    byId("approve-paper").disabled = quarantined;
    if (quarantined) {
      setText(
        "bulk-message",
        "当前为转写疑点隔离审核卷：请先裁决疑点并重建正常 staging。",
      );
    }
  }
  byId("previous-item").disabled = itemIndex === 0;
  byId("next-item").disabled = itemIndex === state.detail.items.length - 1;
  [...document.querySelectorAll(".question-row")].forEach((row, index) => {
    row.setAttribute("aria-current", String(index === itemIndex));
  });
  wireImageSections();
  updateSlotSelection();
  void loadExplanations(item.id);
  void loadApproaches(item.id);
}

function issueValue(value) {
  if (typeof value !== "string") return String(value ?? "");
  try {
    const decoded = JSON.parse(value);
    return typeof decoded === "string" ? decoded : JSON.stringify(decoded, null, 2);
  } catch {
    return value;
  }
}

async function resolveTranscriptionIssue(itemId, issue, body, messageNode) {
  messageNode.textContent = "正在保存裁决…";
  try {
    const response = await fetch(
      `/api/banks/${encodeURIComponent(state.detail.id)}/items/${encodeURIComponent(itemId)}/issues/${encodeURIComponent(issue.issue_id)}/resolution`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...body, note: "" }),
      },
    );
    if (!response.ok) throw new Error(await response.text());
    state.itemCache.delete(itemId);
    const directoryItem = state.detail.items.find((entry) => entry.id === itemId);
    if (directoryItem) {
      directoryItem.unresolved_review_issue_count = Math.max(
        0, (directoryItem.unresolved_review_issue_count || 1) - 1,
      );
    }
    await ensureItemLoaded(itemId);
    renderList();
    renderItem();
  } catch (error) {
    messageNode.textContent = `保存失败：${error.message}`;
  }
}

function renderTranscriptionIssues(item) {
  const section = byId("transcription-issues");
  const list = byId("transcription-issue-list");
  const issues = item.review_issues || [];
  section.hidden = !issues.length;
  list.replaceChildren();
  if (!issues.length) return;
  const unresolved = issues.filter((issue) => !issue.resolved).length;
  setText("transcription-issue-summary", `${issues.length} 项 · ${unresolved} 项未裁决`);
  issues.forEach((issue) => {
    const card = document.createElement("article");
    card.className = `transcription-issue-card severity-${issue.severity}`;
    const head = document.createElement("header");
    const title = document.createElement("strong");
    title.textContent = `${issue.field_path || issue.asset_id} · ${issue.code}`;
    const stateBadge = document.createElement("span");
    stateBadge.textContent = issue.resolved ? "已裁决" : issue.severity;
    stateBadge.className = "transcription-issue-state";
    head.append(title, stateBadge);
    card.append(head);
    if (issue.detail) {
      const detail = document.createElement("p");
      detail.textContent = issue.detail;
      card.append(detail);
    }
    const candidates = document.createElement("div");
    candidates.className = "transcription-candidates";
    (issue.candidates || []).forEach((candidate) => {
      const row = document.createElement("div");
      row.className = "transcription-candidate";
      const value = document.createElement("pre");
      value.textContent = issueValue(candidate.raw_value);
      const meta = document.createElement("small");
      const evidence = (candidate.evidence || []).map((entry) => {
        const bbox = entry.box_px ? ` bbox=${entry.box_px.join(",")}` : "";
        return `${entry.source} · 第${entry.page_number}页${bbox}`;
      }).join("\n");
      meta.textContent = `${candidate.window_id} · 置信度 ${candidate.confidence}${candidate.selected ? " · 当前暂选" : ""}\n${evidence}`;
      const choose = document.createElement("button");
      choose.type = "button";
      choose.textContent = candidate.window_id.startsWith("baseline:") ? "采用已有基线" : "采用此候选";
      choose.disabled = Boolean(issue.resolved);
      choose.addEventListener("click", () => {
        const body = candidate.window_id.startsWith("baseline:")
          ? { decision: "accept_baseline" }
          : { decision: "accept_candidate", accepted_window_id: candidate.window_id };
        void resolveTranscriptionIssue(item.id, issue, body, message);
      });
      row.append(value, meta, choose);
      candidates.append(row);
    });
    if (issue.allowed_classes) {
      issue.allowed_classes.forEach((value) => {
        const choose = document.createElement("button");
        choose.type = "button";
        choose.textContent = `分类为 ${value}`;
        choose.disabled = Boolean(issue.resolved);
        choose.addEventListener("click", () => {
          void resolveTranscriptionIssue(item.id, issue, { decision: value }, message);
        });
        candidates.append(choose);
      });
    }
    const manual = document.createElement("button");
    manual.type = "button";
    manual.textContent = "手工输入正确值";
    manual.disabled = Boolean(issue.resolved) || !issue.candidates;
    manual.addEventListener("click", () => {
      const value = window.prompt("输入该字段的正确值：");
      if (value !== null && value.trim()) {
        void resolveTranscriptionIssue(
          item.id, issue, { decision: "manual", manual_value: value }, message,
        );
      }
    });
    candidates.append(manual);
    const message = document.createElement("p");
    message.className = "review-message";
    card.append(candidates, message);
    list.append(card);
  });
}

function setReviewControlsDisabled(disabled) {
  [byId("approve-item"), byId("reject-item"), byId("confirm-revision"), byId("approve-paper")].forEach((button) => {
    button.disabled = disabled;
  });
}

// reviewNeedsAttentionOf（上方）是同时支持目录项/完整题的通用版；
// reviewNeedsAttention 保留旧名作为完整题别名，给已有调用点用。
function reviewNeedsAttention(item) {
  return reviewNeedsAttentionOf(item);
}

function findNextReviewIndex(currentIndex) {
  const items = state.detail?.items || [];
  for (let offset = 1; offset < items.length; offset += 1) {
    const candidateIndex = (currentIndex + offset) % items.length;
    if (reviewNeedsAttentionOf(items[candidateIndex])) return candidateIndex;
  }
  return -1;
}

function updateStagingProgress() {
  if (state.detail?.kind !== "staging_exam") return;
  const counts = { approved: 0, rejected: 0, stale: 0 };
  // 目录项自带 review_status/stale（§8.3），完整题带 review{}，两种结构都能数。
  state.detail.items.forEach((item) => {
    const review = item.review || {};
    const stale = review.stale ?? item.stale ?? false;
    const status = review.status ?? item.review_status ?? "pending";
    if (stale) counts.stale += 1;
    else if (status === "approved") counts.approved += 1;
    else if (status === "rejected") counts.rejected += 1;
  });
  state.detail.approved_count = counts.approved;
  state.detail.rejected_count = counts.rejected;
  state.detail.stale_count = counts.stale;
  // 目录的 counts 子对象（§8.3 规范字段）也同步，保持单一真相源。
  state.detail.counts = { ...counts };
  const progress = `${counts.approved} 通过 · ${counts.rejected} 待修改 · ${counts.stale} 过期`;
  setText("bank-meta", [state.detail.grade, progress].filter(Boolean).join(" · "));
}

// 审核接口返回的是 review 对象 {status, stale, note, ...}（不含 stem/answer 等）。
// 既更新目录项的 review_status/stale（让 renderList/updateStagingProgress 用目录就能数），
// 也更新 itemCache 里完整题的 review{}（若该题已懒加载过）。两种来源都同步。
function applyReviewResult(itemId, review) {
  const directoryItem = (state.detail?.items || []).find((entry) => entry.id === itemId);
  if (directoryItem) {
    directoryItem.review_status = review.status;
    directoryItem.stale = Boolean(review.stale);
  }
  const cached = state.itemCache.get(itemId);
  if (cached) {
    cached.review = review;
  }
}

// 换图/删图/单题接口返回的是完整 item（含 stem/answer/solution_steps/previews）。
// 写入 itemCache，并同步目录项的 review_status/stale（review 状态来自 item.review）。
function applyFullItem(fullItem) {
  state.itemCache.set(fullItem.id, fullItem);
  const directoryItem = (state.detail?.items || []).find((entry) => entry.id === fullItem.id);
  if (directoryItem) {
    const review = fullItem.review || {};
    directoryItem.review_status = review.status || directoryItem.review_status;
    directoryItem.stale = Boolean(review.stale ?? directoryItem.stale);
  }
}

function hideTextEditPanel() {
  byId("text-edit-panel").hidden = true;
}

// 小问拆分：与讲解面板（explanations）同源的显示级派生——从题干/答案文本
// 里的（1）（2）标记切段。仅用于编辑 UI 的分段展示，保存时拼回整题字段，
// 不改变底层存储（P2-03 小问文本编辑的 UI 层实现）。
// 切片保留原文（不 trim、保留原标记符全/半角形态），保证"未改动即逐字节
// 往返"——否则组装结果与原文出现假差异，保存时会把没改过的题误判为已编辑。
function splitSubquestions(text) {
  const value = String(text || "");
  const markers = [...value.matchAll(/[（(]([1-9])[）)]/g)];
  if (markers.length < 2) return null;
  const head = value.slice(0, markers[0].index);
  const parts = markers.map((match, index) => {
    const end = index + 1 < markers.length ? markers[index + 1].index : value.length;
    return {
      id: match[1],
      marker: match[0],
      text: value.slice(match.index + match[0].length, end),
    };
  });
  const ids = parts.map((part) => part.id);
  if (new Set(ids).size !== ids.length) return null;
  return { head, parts };
}

function assembleSubquestionText(head, parts) {
  return head + parts.map((part) => `${part.marker}${part.text}`).join("");
}

// 二级小问：第(N)问内部的 ①② 分支（上海卷常见："…两次平移…① 求…；② 求…"）。
// 同样只是显示级拆分，拼回时保持原文顺序与标记。
const CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩";

function splitCircledParts(text) {
  const value = String(text || "");
  const indices = [...CIRCLED]
    .map((glyph) => value.indexOf(glyph))
    .filter((position) => position >= 0);
  if (indices.length < 2) return null;
  indices.sort((a, b) => a - b);
  const prefix = value.slice(0, indices[0]);
  const parts = indices.map((start, index) => {
    const end = index + 1 < indices.length ? indices[index + 1] : value.length;
    return {
      glyph: value[start],
      text: value.slice(start + 1, end),
    };
  });
  return { prefix, parts };
}

function assembleCircledParts(prefix, partTexts, glyphs) {
  return (
    prefix + partTexts.map((text, index) => `${glyphs[index]}${text}`).join("")
  );
}

function renderSegmentedEdit(item) {
  const stemParts = splitSubquestions(item.stem_latex || "");
  const answerParts = splitSubquestions(item.answer || "");
  const container = byId("edit-parts");
  container.replaceChildren();
  const promptInputs = [];
  const answerInputs = [];
  // 无小问标记 → 整题文本框（此前的形态）。
  if (!stemParts) {
    byId("edit-stem-field").hidden = false;
    byId("edit-answer-field").hidden = false;
    byId("edit-stem").value = item.stem_latex || "";
    byId("edit-answer").value = item.answer || "";
    return;
  }
  byId("edit-stem-field").hidden = true;
  byId("edit-answer-field").hidden = !answerParts;
  if (!answerParts) {
    byId("edit-answer").value = item.answer || "";
  }

  const headLabel = document.createElement("label");
  const headSpan = document.createElement("span");
  headSpan.textContent = "共享题干（各小问之前的部分）";
  headLabel.append(headSpan);
  const headInput = document.createElement("textarea");
  headInput.rows = 3;
  headInput.value = stemParts.head;
  container.append(headLabel, headInput);

  container.dataset.partInputs = "";
  stemParts.parts.forEach((part, index) => {
    const promptLabel = document.createElement("label");
    const promptSpan = document.createElement("span");
    promptSpan.textContent = `第（${index + 1}）问 题干`;
    promptLabel.append(promptSpan);
    container.append(promptLabel);

    // 第(N)问内部含 ①② → 二级分栏(如黄浦24第(2)问的两个分支)。
    const circled = splitCircledParts(part.text);
    const partPromptInputs = [];
    if (circled) {
      const prefixLabel = document.createElement("label");
      const prefixSpan = document.createElement("span");
      prefixSpan.textContent = `第（${index + 1}）问 公共部分`;
      prefixLabel.append(prefixSpan);
      const prefixInput = document.createElement("textarea");
      prefixInput.rows = 2;
      prefixInput.value = circled.prefix;
      container.append(prefixLabel, prefixInput);
      partPromptInputs.push({ kind: "circled-prefix", input: prefixInput });
      circled.parts.forEach((sub) => {
        const subLabel = document.createElement("label");
        const subSpan = document.createElement("span");
        subSpan.textContent = `第（${index + 1}）问 ${sub.glyph}`;
        subLabel.append(subSpan);
        const subInput = document.createElement("textarea");
        subInput.rows = 2;
        subInput.value = sub.text;
        container.append(subLabel, subInput);
        partPromptInputs.push({ kind: "circled", glyph: sub.glyph, input: subInput });
      });
    } else {
      const promptInput = document.createElement("textarea");
      promptInput.rows = 2;
      promptInput.value = part.text;
      container.append(promptInput);
      partPromptInputs.push({ kind: "plain", input: promptInput });
    }
    container.dataset.partInputs += `${index}:${partPromptInputs.length};`;

    if (answerParts && answerParts.parts[index]) {
      const answerLabel = document.createElement("label");
      const answerSpan = document.createElement("span");
      answerSpan.textContent = `第（${index + 1}）问 答案`;
      answerLabel.append(answerSpan);
      const answerInput = document.createElement("textarea");
      answerInput.rows = 2;
      answerInput.value = answerParts.parts[index].text;
      answerInputs.push(answerInput);
      container.append(answerLabel, answerInput);
    }
  });
}

function readSegmentedEdit(item) {
  const container = byId("edit-parts");
  if (!container.childElementCount) {
    return { stem: byId("edit-stem").value, answer: byId("edit-answer").value };
  }
  const stemParts = splitSubquestions(item.stem_latex || "");
  const answerParts = splitSubquestions(item.answer || "");
  const labels = [...container.querySelectorAll(":scope > label")];
  const textareas = [...container.querySelectorAll(":scope > textarea")];
  const head = textareas[0].value.trim();
  const hasPartAnswers = Boolean(answerParts);
  const promptParts = [];
  const answerPartTexts = [];
  let cursor = 1; // 0 号是共享题干
  stemParts.parts.forEach((part, index) => {
    const circled = splitCircledParts(part.text);
    if (circled) {
      const prefix = textareas[cursor].value.trim();
      cursor += 1;
      const subTexts = [];
      circled.parts.forEach(() => {
        subTexts.push(textareas[cursor].value.trim());
        cursor += 1;
      });
      promptParts.push(
        assembleCircledParts(
          prefix,
          subTexts,
          circled.parts.map((sub) => sub.glyph),
        ),
      );
    } else {
      promptParts.push(textareas[cursor].value.trim());
      cursor += 1;
    }
    if (hasPartAnswers) {
      answerPartTexts.push(textareas[cursor].value.trim());
      cursor += 1;
    }
  });
  const stem = assembleSubquestionText(
    head,
    promptParts.map((part, index) => ({
      marker: stemParts.parts[index].marker,
      text: part,
    })),
  );
  const answer = hasPartAnswers
    ? stemParts.parts
        .map((part, index) => `${part.marker}${answerPartTexts[index]}`)
        .join("；")
    : byId("edit-answer").value;
  void labels;
  return { stem, answer };
}

function showTextEditPanel(item) {
  renderSegmentedEdit(item);
  byId("edit-clue").value = item.clue || "";
  byId("edit-steps").value = (item.solution_steps || [])
    .map((step) => (typeof step === "string" ? step : step.content || step.title || ""))
    .join("\n");
  const message = byId("text-edit-message");
  message.textContent = "";
  message.hidden = true;
  byId("text-edit-panel").hidden = false;
  const firstInput = byId("edit-parts").querySelector("textarea") || byId("edit-stem");
  firstInput.focus();
}

async function saveTextEdits() {
  const item = state.detail.items[state.itemIndex];
  if (!item) return;
  const message = byId("text-edit-message");
  const payload = {};
  const { stem, answer } = readSegmentedEdit(item);
  const clue = byId("edit-clue").value;
  const steps = byId("edit-steps").value.split("\n").map((line) => line.trim()).filter(Boolean);
  if (stem !== (item.stem_latex || "")) payload.stem_latex = stem;
  if (answer !== (item.answer || "")) payload.answer = answer;
  if (clue !== (item.clue || "")) payload.clue = clue;
  if (steps.join("\n") !== (item.solution_steps || []).map((s) => (typeof s === "string" ? s : s.content || s.title || "")).join("\n")) {
    payload.solution_steps = steps;
  }
  if (!Object.keys(payload).length) {
    message.textContent = "没有改动可保存。";
    message.hidden = false;
    return;
  }
  try {
    const response = await fetch(
      `/api/banks/${encodeURIComponent(state.detail.bank_id)}/items/${encodeURIComponent(item.id)}/text`,
      {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      }
    );
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new Error(body.detail || `保存失败（${response.status}）`);
    }
    const updated = await response.json();
    state.itemCache.set(item.id, updated);
    applyFullItem(updated, state.itemIndex);
    message.textContent = "已保存：content hash 已重算，请重新审核本题。";
    message.hidden = false;
  } catch (error) {
    message.textContent = `保存失败：${error.message}`;
    message.hidden = false;
  }
}

byId("edit-text-toggle").addEventListener("click", () => {
  const item = state.detail.items[state.itemIndex];
  if (!item) return;
  showTextEditPanel(item);
});
byId("edit-text-cancel").addEventListener("click", hideTextEditPanel);
byId("edit-text-save").addEventListener("click", saveTextEdits);

async function submitReview(decision, note = "") {
  const item = state.detail?.items?.[state.itemIndex];
  if (!item || state.detail.kind !== "staging_exam" || state.submittingReview) return false;
  if (state.detail.review_mode_active) {
    setText(
      "review-message",
      "隔离审核卷不能直接通过或要求修改；请先完成字段裁决并重建正常 staging。",
    );
    return false;
  }
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
    applyReviewResult(reviewedItemId, await response.json());
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

// 在当前筛选列表（state.banks）里找下一份未全通过（approved_count < item_count）的
// staging 试卷。从当前卷之后环形扫描，找不到返回 null。
function findNextUnreviewedBank(currentBankId) {
  const banks = state.banks || [];
  const current = banks.findIndex((bank) => bank.id === currentBankId);
  if (current < 0) return null;
  const isUnreviewed = (bank) => (
    bank.kind === "staging_exam"
    && (bank.approved_count || 0) < (bank.item_count || 0)
  );
  for (let offset = 1; offset <= banks.length; offset += 1) {
    const candidate = banks[(current + offset) % banks.length];
    if (candidate.id !== currentBankId && isUnreviewed(candidate)) return candidate;
  }
  return null;
}

// 全卷一键通过：POST review-all → 刷新当前卷 items/counts → 回写 state.banks 计数 →
// 跳到下一份未全通过卷（找不到则停在本卷第 1 题）。单题失败收集在 errors[] 里，
// 在 bulk-message 列出，不跳卷，让用户处理。
async function approveWholePaper() {
  if (!state.detail || state.detail.kind !== "staging_exam" || state.submittingReview) return;
  if (state.detail.review_mode_active) {
    setText("bulk-message", "隔离审核卷不能直接通过；请先裁决并重建正常 staging。");
    return;
  }
  const currentBankId = state.detail.id;
  state.submittingReview = true;
  setReviewControlsDisabled(true);
  ensureAudioContext();
  setText("bulk-message", "正在一键通过整卷…");
  setText("review-message", "");
  try {
    const response = await fetch(
      `/api/banks/${encodeURIComponent(currentBankId)}/review-all`,
      { method: "POST" },
    );
    if (!response.ok) throw new Error(await response.text());
    const payload = await response.json();
    const errors = payload.errors || [];
    // bulk approve 返回 {counts, updated_reviews, errors}（§9.2 推荐方案）：
    // 就地用 applyReviewResult 同步目录项 review_status/stale 与 itemCache 完整题 review，
    // counts 直接回写。不重拉整卷。
    const updatedReviews = payload.updated_reviews || {};
    state.detail.items.forEach((item) => {
      const review = updatedReviews[item.id];
      if (review) applyReviewResult(item.id, review);
    });
    const counts = payload.counts;
    if (counts) {
      state.detail.approved_count = counts.approved || 0;
      state.detail.rejected_count = counts.rejected || 0;
      state.detail.stale_count = counts.stale || 0;
      state.detail.counts = { ...counts };
    } else {
      updateStagingProgress();
    }
    // 回写当前 bank 的计数到 state.banks，让"下一份未通过卷"判断准确。
    const bankEntry = state.banks.find((bank) => bank.id === currentBankId);
    if (bankEntry) {
      bankEntry.approved_count = state.detail.approved_count;
      bankEntry.rejected_count = state.detail.rejected_count;
      bankEntry.stale_count = state.detail.stale_count;
    }
    renderList();
    if (errors.length) {
      setText("bulk-message", `${errors.length} 题审核失败：${errors.map((e) => e.item_id).join("、")}。请逐题处理后重试，未跳转。`);
      renderItem();
      return;
    }
    const nextBank = findNextUnreviewedBank(currentBankId);
    playApprovalSound();
    if (nextBank) {
      setText("bulk-message", `本卷已全部通过，正在跳转 ${nextBank.topic}…`);
      await selectBank(nextBank.id);
      setText("bulk-message", `已跳转 ${nextBank.topic}。`);
    } else {
      state.itemIndex = 0;
      renderItem();
      setText("bulk-message", "本卷已全部通过，筛选范围内已无待审试卷。");
    }
  } catch (error) {
    setText("bulk-message", `一键通过失败：${error.message}`);
  } finally {
    state.submittingReview = false;
    setReviewControlsDisabled(false);
  }
}

// 单题懒加载（§10.3 阶段 5）：目录项只有 id/title/review_status/stale，
// 完整题（stem/answer/solution_steps/previews）按需请求 /items/{item_id}。
// renderItem 先查 itemCache，命中直接渲染；未命中渲染骨架并触发请求，到货后重渲。
// itemLoadToken 防竞态：用户切到别的题/卷后旧请求的结果被丢弃。
async function ensureItemLoaded(itemId) {
  if (state.itemCache.has(itemId)) return state.itemCache.get(itemId);
  const token = ++state.itemLoadToken;
  const response = await fetch(
    `/api/banks/${encodeURIComponent(state.detail.id)}/items/${encodeURIComponent(itemId)}`,
  );
  if (!response.ok) throw new Error(await response.text());
  const fullItem = await response.json();
  // 切到别的题/卷了，或 selectBank 重建了 detail → 丢弃。
  if (token !== state.itemLoadToken) return null;
  applyFullItem(fullItem);
  return fullItem;
}

function renderItem() {
  const directoryItem = state.detail.items[state.itemIndex];
  const itemIndex = state.itemIndex;
  const cached = directoryItem ? state.itemCache.get(directoryItem.id) : null;
  const epoch = ++mathRenderEpoch;
  const reader = byId("reader");

  // 数据已经在 itemCache 中时先同步更新 DOM。MathJax 排版可以随后执行，不能让
  // 旧的 typeset 队列挡住刚保存的题图/解答图回显。
  if (cached) {
    if (window.MathJax?.typesetClear) window.MathJax.typesetClear([reader]);
    applyItem(cached, itemIndex);
    mathRenderQueue = mathRenderQueue.then(async () => {
      if (epoch !== mathRenderEpoch || !window.MathJax?.typesetPromise) return;
      await window.MathJax.typesetPromise([reader]);
    }).catch((error) => {
      console.warn("MathJax typesetting failed", error);
    });
    prefetchNeighborItems(itemIndex);
    return;
  }

  // 骨架也立即显示；完整单题到货后同步更新 DOM，再把公式排版排进队列。
  renderSkeleton(directoryItem, itemIndex);
  void ensureItemLoaded(directoryItem.id).then((fullItem) => {
    if (!fullItem || epoch !== mathRenderEpoch) return;
    if (window.MathJax?.typesetClear) window.MathJax.typesetClear([reader]);
    applyItem(fullItem, itemIndex);
    mathRenderQueue = mathRenderQueue.then(async () => {
      if (epoch !== mathRenderEpoch || !window.MathJax?.typesetPromise) return;
      await window.MathJax.typesetPromise([reader]);
    }).catch((error) => {
      console.warn("MathJax typesetting failed", error);
    });
  }).catch((error) => {
    if (epoch !== mathRenderEpoch) return;
    const node = byId("load-error");
    if (node) {
      node.hidden = false;
      node.textContent = `本题读取失败：${error.message}`;
    }
  });
  // 空闲预取前后各一题（§10.3），不阻塞当前渲染。
  prefetchNeighborItems(itemIndex);
}

// 预取当前题的前后各一题（§10.3）：单题接口命中后只解析该题 3 份 YAML（A5），
// 用户翻题时直接命中 itemCache，无感知延迟。已缓存的跳过。
function prefetchNeighborItems(itemIndex) {
  const items = state.detail?.items || [];
  const neighbors = [itemIndex - 1, itemIndex + 1];
  for (const neighborIndex of neighbors) {
    if (neighborIndex < 0 || neighborIndex >= items.length) continue;
    const directoryItem = items[neighborIndex];
    if (!directoryItem || state.itemCache.has(directoryItem.id)) continue;
    // 故意不 await、不持有 token：预取的结果只写 cache，不重渲。
    fetch(
      `/api/banks/${encodeURIComponent(state.detail.id)}/items/${encodeURIComponent(directoryItem.id)}`,
    )
      .then((response) => (response.ok ? response.json() : null))
      .then((fullItem) => {
        if (fullItem && state.detail && state.detail.id) {
          applyFullItem(fullItem);
        }
      })
      .catch(() => { /* 预取失败静默 */ });
  }
}

// 骨架渲染：当前题尚未懒加载完成时，先把 id/位置/空内容铺上，避免界面空白。
function renderSkeleton(directoryItem, itemIndex) {
  if (!directoryItem) return;
  setText("item-id", directoryItem.id);
  setText("item-title", directoryItem.title || directoryItem.id);
  setText("stem", "正在读取题目…");
  setText("answer", "正在读取答案…");
  setText("clue", "正在读取思路提示…");
  setText("position-summary", `${itemIndex + 1} / ${state.detail.items.length}`);
  const error = byId("load-error");
  if (error) {
    error.hidden = true;
    error.textContent = "";
  }
  const badges = byId("item-badges");
  if (badges) badges.replaceChildren();
  ["choices", "solution-steps", "solution-notes"].forEach((id) => {
    const node = byId(id);
    if (node) node.replaceChildren();
  });
  // 讲解/解答面板重置为骨架态；切题时若还在录音则先停止。
  stopExplanationRecording();
  stopApproachRecording();
  const explanationsBody = byId("explanations-body");
  if (explanationsBody) {
    const loading = document.createElement("p");
    loading.className = "explanations-loading";
    loading.textContent = "正在读取讲解/解答…";
    explanationsBody.replaceChildren(loading);
  }
  explanationMessageNode(byId("explanations-card"), "");
  if (state.detail.kind === "staging_exam") {
    ["prompt-preview", "official-solution-preview", "source-capsules"].forEach((id) => {
      const node = byId(id);
      if (node) node.replaceChildren();
    });
  }
  byId("previous-item").disabled = itemIndex === 0;
  byId("next-item").disabled = itemIndex === state.detail.items.length - 1;
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
    applyFullItem(await response.json());
    updateStagingProgress();
    renderList();
    renderItem();
    await mathRenderQueue;
    const expired = target.target === "official_solution"
      ? "；该题此前的人工审核已自动过期。"
      : "";
    setText("review-message", `${target.label} 已保存${expired}槽位仍保持选中，可继续粘贴替换。`);
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
    applyFullItem(await response.json());
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
  // 加载新卷前清空单题缓存（§8.3 item cache 随卷失效），避免跨卷串题。
  state.itemCache = new Map();
  // 切换卷期间不隐藏整个 layout（F3）：仅在首次加载（detail 仍为 null）时显示 page-status，
  // 已有内容时保持显示旧卷直到新目录到达，避免搜索/切卷时界面闪烁消失。
  const isFirstLoad = state.detail === null;
  setText("page-status", "正在读取题库…");
  byId("page-status").hidden = false;
  if (isFirstLoad) byId("review-layout").hidden = true;
  try {
    // 卷级轻量目录（§8.3）：counts + items 的 id/title/review_status/stale。
    // 完整题按需懒加载（§10.3），避免一次拉整卷 3×N 份 YAML。
    const response = await fetch(
      `/api/banks/${encodeURIComponent(bankId)}?directory=1`,
      { signal: selectBankAbortController().signal },
    );
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
    const counts = detail.counts || {};
    const progress = staging
      ? `${counts.approved || 0} 通过 · ${counts.rejected || 0} 待修改 · ${counts.stale || 0} 过期`
      : `${counts.approved || 0}/${detail.item_count} 题可用`;
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
    if (error.name === "AbortError") return;
    setText("page-status", `题库加载失败：${error.message}。可重新选择题库重试。`);
  }
}

// selectBank 的 AbortController（F4）：新的 selectBank 调用会取消上一个未完成的目录请求。
// 用一个模块级单例，每次 selectBank 新建并替换，旧请求在浏览器侧被取消。
let selectBankAbort = null;
function selectBankAbortController() {
  if (selectBankAbort) selectBankAbort.abort();
  selectBankAbort = new AbortController();
  return selectBankAbort;
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
  // 过滤期间禁用列表，避免在旧数据上误读。但不再隐藏整个 review-layout（F3）：
  // 已加载的卷内容保持显示直到新结果到达，搜索/过滤时界面不闪烁消失。
  select.disabled = true;
  const hadLayout = !byId("review-layout").hidden;
  if (!hadLayout) {
    // 仅在首次（layout 还没出现过）时显示「正在筛选」；已有内容则不打扰。
    setText("page-status", "正在筛选题库…");
    byId("page-status").hidden = false;
  }
  // F4 AbortController：新的 applyFilters 取消上一个未完成的 /api/banks 请求。
  if (filtersAbort) filtersAbort.abort();
  filtersAbort = new AbortController();
  try {
    const response = await fetch(`/api/banks?${params.toString()}`, {
      signal: filtersAbort.signal,
    });
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
    // F2：仅当选中的 bank_id 真正变化才重载整卷详情。过滤后当前卷仍在结果集里时，
    // 不触发 selectBank，用户在搜索时不会被打断到第 1 题。
    const currentBankId = state.detail?.id;
    const targetBankId = initialBank.id;
    select.value = targetBankId;
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
    if (!hadLayout) {
      byId("page-status").hidden = true;
    }
    if (currentBankId !== targetBankId) {
      await selectBank(targetBankId);
    } else {
      // 当前卷仍在结果集：保持内容，只把 page-status 收掉。
      byId("page-status").hidden = true;
      byId("review-layout").hidden = false;
    }
  } catch (error) {
    select.disabled = false;
    if (error.name === "AbortError") return;
    if (token !== state.filterToken) return;
    setText("page-status", `题库列表加载失败：${error.message}。请刷新页面重试。`);
  }
}

// applyFilters 的 AbortController（F4），与 selectBank 的独立。
let filtersAbort = null;

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

  // 首屏改用 bootstrap（§8.1/§10.1，F1）：一次拿到 summaries + facets + errors，
  // 消灭 loadFacets() → applyFilters() 串行瀑布。本地填 facets 后再触发首次 selectBank。
  try {
    const response = await fetch("/api/bootstrap");
    if (!response.ok) throw new Error(await response.text());
    const payload = await response.json();
    const facets = payload.facets || {};
    fillFacetOptions(byId("filter-grade"), facets.grades || []);
    fillFacetOptions(byId("filter-year"), facets.years || []);
    byId("filter-grade").disabled = false;
    byId("filter-year").disabled = false;
    byId("filter-exam-type").disabled = false;
  } catch (error) {
    // bootstrap 失败（冷启动 / 服务端构建中）→ 显示「正在建立题库索引」（§10.4），
    // 不阻断：applyFilters 仍会单独请求 /api/banks，facets 缺失时下拉为空但搜索可用。
    setText("page-status", "正在建立题库索引，请稍候…");
    byId("page-status").hidden = false;
    console.warn("bootstrap 加载失败：", error.message);
  }
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
byId("approve-paper").addEventListener("click", () => { void approveWholePaper(); });
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
byId("source-lightbox-close").addEventListener("click", () => byId("source-lightbox").close());
byId("source-lightbox-prev").addEventListener("click", () => navigateSourceLightbox(-1));
byId("source-lightbox-next").addEventListener("click", () => navigateSourceLightbox(1));
// 点 backdrop（dialog 自身，而非其子元素）关闭图廊。
byId("source-lightbox").addEventListener("click", (event) => {
  if (event.target === event.currentTarget) event.currentTarget.close();
});
byId("source-lightbox").addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    event.preventDefault();
    event.currentTarget.close();
  } else if (event.key === "ArrowLeft") {
    event.preventDefault();
    navigateSourceLightbox(-1);
  } else if (event.key === "ArrowRight") {
    event.preventDefault();
    navigateSourceLightbox(1);
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
    || byId("source-lightbox").open
    || isEditableTarget(event.target)
  ) return;
  const key = event.key.toLowerCase();
  // Shift+A 单独路由到全卷通过，避免和单题 A 撞车。
  if (event.shiftKey && key === "a" && state.detail?.kind === "staging_exam") {
    event.preventDefault();
    void approveWholePaper();
    return;
  }
  if (event.shiftKey) return;
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
// ---------------------------------------------------------------------------
// 小题讲解 / 解答：录音 → 转写润色 → 编辑 → 批准 → 导出 teaching-tools blueprint
// ---------------------------------------------------------------------------

const explanationsState = {
  payload: null,
  token: 0,
  itemId: null,
};

const explanationRecording = {
  recorder: null,
  chunks: [],
  approachId: null,
  bankId: null,
  itemId: null,
  mimeType: "",
  timer: null,
  startedAt: 0,
};

const EXPLANATION_SOURCE_LABELS = {
  recorded: "录音",
  transcript: "录音转写",
  polished: "录音润色",
  generated: "自动生成",
  manual: "手工",
};

function explanationsEndpoint(bankId, itemId) {
  return `/api/banks/${encodeURIComponent(bankId)}/items/${encodeURIComponent(itemId)}/explanations`;
}

function currentExplanationItemId() {
  return state.detail?.items?.[state.itemIndex]?.id || null;
}

async function explanationsFetch(url, options = {}) {
  const response = await fetch(url, options);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.detail || `请求失败（${response.status}）`);
  }
  return payload;
}

function applyExplanationsPayload(payload) {
  explanationsState.payload = payload?.subquestions ? payload : payload?.explanations;
  renderExplanations();
}

function findExplanationApproach(approachId) {
  for (const subquestion of explanationsState.payload?.subquestions || []) {
    for (const approach of subquestion.approaches || []) {
      if (approach.id === approachId) return { subquestion, approach };
    }
  }
  return null;
}

function explanationMessageNode(scope, text, tone = "info") {
  if (!scope) return;
  const node = scope.classList?.contains("explanation-approach")
    ? scope.querySelector(".explanation-message")
    : byId("explanations-message");
  if (!node) return;
  node.textContent = text || "";
  node.dataset.tone = tone;
}

async function loadExplanations(itemId) {
  const bankId = state.detail?.id;
  if (!bankId || !itemId) return;
  const token = ++explanationsState.token;
  explanationsState.itemId = itemId;
  explanationsState.payload = null;
  explanationMessageNode(byId("explanations-card"), "");
  const body = byId("explanations-body");
  if (body) {
    const loading = document.createElement("p");
    loading.className = "explanations-loading";
    loading.textContent = "正在读取讲解/解答…";
    body.replaceChildren(loading);
  }
  try {
    const payload = await explanationsFetch(explanationsEndpoint(bankId, itemId));
    if (token !== explanationsState.token) return;
    explanationsState.payload = payload;
    renderExplanations();
  } catch (error) {
    if (token !== explanationsState.token) return;
    const target = byId("explanations-body");
    if (target) {
      const node = document.createElement("p");
      node.className = "explanations-error";
      node.textContent = `讲解/解答读取失败：${error.message}`;
      target.replaceChildren(node);
    }
  }
}

function subquestionStatusLabel(subquestion) {
  const approaches = subquestion.approaches || [];
  if (!approaches.length) return "缺讲解";
  const approved = approaches.filter(
    (approach) => approach.explanation?.status === "approved" && approach.solution?.status === "approved",
  ).length;
  return approved === approaches.length && approved > 0
    ? `${approaches.length} 对 · 全部已批准`
    : `${approaches.length} 对 · ${approved} 已批准`;
}

function approachStatusLabel(approach) {
  const explanation = approach.explanation || {};
  const solution = approach.solution || {};
  if (explanation.status === "approved" && solution.status === "approved") return "已批准";
  const parts = [];
  parts.push(explanation.text?.trim() ? "有讲解" : "缺讲解");
  parts.push(solution.text?.trim() ? "有解答" : "缺解答");
  return parts.join(" · ");
}

function renderExplanations() {
  const payload = explanationsState.payload;
  const body = byId("explanations-body");
  if (!body || !payload) return;
  body.replaceChildren();
  (payload.subquestions || []).forEach((subquestion) => {
    body.append(renderExplanationSubquestion(subquestion));
  });
  const hint = byId("explanations-hint");
  if (hint) {
    hint.textContent = payload.recording_supported
      ? "讲解与解答按小题配对管理：点“录讲解”口述后自动转写并润色，可编辑、重新润色或补齐；批准后导出 teaching-tools blueprint。"
      : "录音转写未启用（服务器缺 DASHSCOPE_API_KEY 或 ffmpeg）：仍可手动编辑讲解，或用“补齐缺失讲解/解答”自动生成。";
  }
  updateRecordingButtons();
  scheduleExplanationsTypeset();
}

function scheduleExplanationsTypeset() {
  const body = byId("explanations-body");
  if (!body || !window.MathJax?.typesetPromise) return;
  mathRenderQueue = mathRenderQueue.then(async () => {
    await window.MathJax.typesetPromise([body]);
  }).catch((error) => {
    console.warn("MathJax typesetting failed", error);
  });
}

function ghostButton(text, className = "ghost-button") {
  const button = document.createElement("button");
  button.type = "button";
  button.className = className;
  button.textContent = text;
  return button;
}

function renderExplanationSubquestion(subquestion) {
  const wrap = document.createElement("article");
  wrap.className = "explanation-subquestion";
  wrap.dataset.subquestionId = subquestion.id;

  const head = document.createElement("div");
  head.className = "explanation-subquestion-head";
  const label = document.createElement("strong");
  label.className = "explanation-subquestion-label";
  label.textContent = subquestion.label || "整题";
  const stem = document.createElement("span");
  stem.className = "explanation-subquestion-stem source-text";
  stem.textContent = formatReviewText(subquestion.stem_latex || "");
  const status = badge(subquestionStatusLabel(subquestion), "chip-explanation-status");
  const addButton = ghostButton("＋ 新建讲解-解答");
  addButton.addEventListener("click", () => {
    void createApproachAction(subquestion.id, addButton);
  });
  head.append(label, stem, status, addButton);
  wrap.append(head);

  (subquestion.approaches || []).forEach((approach) => {
    wrap.append(renderExplanationApproach(approach));
  });
  if (!(subquestion.approaches || []).length) {
    const empty = document.createElement("p");
    empty.className = "explanation-empty";
    empty.textContent = "该小问还没有讲解-解答：点“新建讲解-解答”添加，或用顶部“补齐缺失讲解”自动生成。";
    wrap.append(empty);
  }
  return wrap;
}

function renderExplanationApproach(approach) {
  const card = document.createElement("article");
  card.className = "explanation-approach";
  card.dataset.approachId = approach.id;

  const head = document.createElement("div");
  head.className = "explanation-approach-head";
  const title = document.createElement("strong");
  title.className = "explanation-approach-title";
  title.textContent = approach.title || `思路 ${approach.id}`;
  const status = badge(approachStatusLabel(approach), "chip-explanation-status");
  const headActions = document.createElement("span");
  headActions.className = "explanation-approach-actions";

  const recordButton = document.createElement("button");
  recordButton.type = "button";
  recordButton.className = "explanation-record-button";
  recordButton.dataset.approachId = approach.id;
  recordButton.textContent = "● 录讲解";
  recordButton.addEventListener("click", () => {
    void toggleExplanationRecording(approach.id);
  });

  const polishButton = ghostButton("润色讲解");
  polishButton.addEventListener("click", () => {
    void polishApproachAction(approach.id, polishButton);
  });

  const generateExplanationButton = ghostButton("生成讲解");
  generateExplanationButton.addEventListener("click", () => {
    void generateApproachTextAction("explanation", approach.id, generateExplanationButton);
  });

  const generateSolutionButton = ghostButton("生成解答");
  generateSolutionButton.addEventListener("click", () => {
    void generateApproachTextAction("solution", approach.id, generateSolutionButton);
  });

  const approveButton = ghostButton("批准并导出 blueprint", "approve-button");
  approveButton.addEventListener("click", () => {
    void approveApproachAction(approach.id, approveButton);
  });

  const deleteButton = ghostButton("删除", "reject-button");
  deleteButton.addEventListener("click", () => {
    void deleteApproachAction(approach.id);
  });

  headActions.append(recordButton);
  if (approach.explanation?.transcript || approach.explanation?.audio_path) headActions.append(polishButton);
  if (!approach.explanation?.text?.trim()) headActions.append(generateExplanationButton);
  if (approach.explanation?.text?.trim() && !approach.solution?.text?.trim()) {
    headActions.append(generateSolutionButton);
  }
  if (approach.explanation?.text?.trim() && approach.solution?.text?.trim()) {
    headActions.append(approveButton);
  }
  headActions.append(deleteButton);

  const headParts = [title, status];
  if (approach.blueprint) {
    headParts.push(badge(approach.blueprint.stale ? "blueprint 已过期" : "blueprint 已导出", "chip-blueprint"));
  }
  head.append(...headParts, headActions);
  card.append(head);

  card.append(renderExplanationField("讲解", approach, "explanation"));
  if (approach.explanation?.transcript) {
    const details = document.createElement("details");
    details.className = "explanation-transcript";
    const summary = document.createElement("summary");
    summary.textContent = "录音转写稿";
    const transcript = document.createElement("pre");
    transcript.textContent = approach.explanation.transcript;
    details.append(summary, transcript);
    card.append(details);
  }
  card.append(renderExplanationField("解答", approach, "solution"));

  const message = document.createElement("p");
  message.className = "explanation-message";
  message.setAttribute("role", "status");
  card.append(message);
  return card;
}

function renderExplanationField(labelText, approach, field) {
  const block = document.createElement("div");
  block.className = "explanation-field";
  const head = document.createElement("div");
  head.className = "explanation-field-head";
  const label = document.createElement("span");
  label.className = "explanation-field-label";
  label.textContent = labelText;
  const source = approach[field]?.source;
  if (source && approach[field]?.text?.trim()) {
    const sourceChip = badge(EXPLANATION_SOURCE_LABELS[source] || source, "chip-source");
    head.append(label, sourceChip);
  } else {
    head.append(label);
  }
  const textarea = document.createElement("textarea");
  textarea.rows = field === "explanation" ? 5 : 4;
  textarea.className = "explanation-textarea";
  textarea.value = approach[field]?.text || "";
  textarea.setAttribute("aria-label", `${labelText}（编辑后失焦自动保存）`);
  const preview = document.createElement("div");
  preview.className = "explanation-preview source-text";
  preview.textContent = formatReviewText(textarea.value);
  bindExplanationEditor(textarea, preview, approach.id, field);
  block.append(head, textarea, preview);
  return block;
}

function bindExplanationEditor(textarea, preview, approachId, field) {
  textarea.addEventListener("input", () => {
    preview.textContent = formatReviewText(textarea.value);
  });
  textarea.addEventListener("blur", () => {
    const found = findExplanationApproach(approachId);
    if (!found) return;
    const before = found.approach[field]?.text || "";
    if (textarea.value.trim() === before.trim()) return;
    void saveApproachText(approachId, field, textarea.value);
  });
}

async function saveApproachText(approachId, field, value) {
  const bankId = state.detail?.id;
  const itemId = currentExplanationItemId();
  if (!bankId || !itemId) return;
  const body = field === "explanation" ? { explanation_text: value } : { solution_text: value };
  const scope = document.querySelector(`.explanation-approach[data-approach-id="${approachId}"]`);
  explanationMessageNode(scope, "保存中…");
  try {
    const payload = await explanationsFetch(
      `${explanationsEndpoint(bankId, itemId)}/approaches/${encodeURIComponent(approachId)}`,
      {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      },
    );
    if (explanationsState.itemId === itemId) applyExplanationsPayload(payload);
    const fresh = document.querySelector(`.explanation-approach[data-approach-id="${approachId}"]`);
    explanationMessageNode(fresh, "已保存。", "ok");
  } catch (error) {
    const fresh = document.querySelector(`.explanation-approach[data-approach-id="${approachId}"]`);
    explanationMessageNode(fresh, `保存失败：${error.message}`, "error");
  }
}

async function createApproachAction(subquestionId, button) {
  const bankId = state.detail?.id;
  const itemId = currentExplanationItemId();
  if (!bankId || !itemId) return;
  button.disabled = true;
  try {
    const payload = await explanationsFetch(`${explanationsEndpoint(bankId, itemId)}/approaches`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ subquestion_id: subquestionId }),
    });
    if (explanationsState.itemId === itemId) applyExplanationsPayload(payload);
  } catch (error) {
    explanationMessageNode(byId("explanations-card"), `新建失败：${error.message}`, "error");
  } finally {
    button.disabled = false;
  }
}

async function deleteApproachAction(approachId) {
  if (!window.confirm("删除这组讲解-解答？录音文件会保留在题库目录中。")) return;
  const bankId = state.detail?.id;
  const itemId = currentExplanationItemId();
  if (!bankId || !itemId) return;
  try {
    const payload = await explanationsFetch(
      `${explanationsEndpoint(bankId, itemId)}/approaches/${encodeURIComponent(approachId)}`,
      { method: "DELETE" },
    );
    if (explanationsState.itemId === itemId) applyExplanationsPayload(payload);
  } catch (error) {
    explanationMessageNode(byId("explanations-card"), `删除失败：${error.message}`, "error");
  }
}

async function polishApproachAction(approachId, button) {
  const bankId = state.detail?.id;
  const itemId = currentExplanationItemId();
  if (!bankId || !itemId) return;
  const scope = document.querySelector(`.explanation-approach[data-approach-id="${approachId}"]`);
  explanationMessageNode(scope, "正在润色讲解…");
  if (button) button.disabled = true;
  try {
    const payload = await explanationsFetch(
      `${explanationsEndpoint(bankId, itemId)}/approaches/${encodeURIComponent(approachId)}/polish`,
      { method: "POST" },
    );
    if (explanationsState.itemId === itemId) applyExplanationsPayload(payload);
    const fresh = document.querySelector(`.explanation-approach[data-approach-id="${approachId}"]`);
    explanationMessageNode(fresh, "润色完成，可直接编辑或重新润色。", "ok");
  } catch (error) {
    const fresh = document.querySelector(`.explanation-approach[data-approach-id="${approachId}"]`);
    explanationMessageNode(fresh, `润色失败：${error.message}`, "error");
  } finally {
    if (button) button.disabled = false;
  }
}

async function generateApproachTextAction(kind, approachId, button) {
  // 单对补齐：kind=explanation 只填本对缺的讲解；kind=solution 只补本对解答。
  const found = findExplanationApproach(approachId);
  if (!found) return;
  const bankId = state.detail?.id;
  const itemId = currentExplanationItemId();
  if (!bankId || !itemId) return;
  const scope = document.querySelector(`.explanation-approach[data-approach-id="${approachId}"]`);
  explanationMessageNode(scope, kind === "explanation" ? "正在生成讲解…" : "正在生成解答…");
  if (button) button.disabled = true;
  try {
    const payload = await explanationsFetch(`${explanationsEndpoint(bankId, itemId)}/generate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ kind }),
    });
    if (explanationsState.itemId === itemId) applyExplanationsPayload(payload);
    const fresh = document.querySelector(`.explanation-approach[data-approach-id="${approachId}"]`);
    explanationMessageNode(fresh, "已生成，可继续编辑或重新润色。", "ok");
  } catch (error) {
    const fresh = document.querySelector(`.explanation-approach[data-approach-id="${approachId}"]`);
    explanationMessageNode(fresh, `生成失败：${error.message}`, "error");
  } finally {
    if (button) button.disabled = false;
  }
}

async function generateMissingAction(kind) {
  const bankId = state.detail?.id;
  const itemId = currentExplanationItemId();
  if (!bankId || !itemId) return;
  const card = byId("explanations-card");
  explanationMessageNode(card, kind === "explanation" ? "正在为缺讲解的小问生成讲解…" : "正在为缺解答的讲解生成解答…");
  try {
    const payload = await explanationsFetch(`${explanationsEndpoint(bankId, itemId)}/generate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ kind }),
    });
    if (explanationsState.itemId === itemId) applyExplanationsPayload(payload.explanations || payload);
    const errors = payload.errors || [];
    if (!payload.generated && !errors.length) {
      explanationMessageNode(card, "没有需要补齐的内容。");
    } else if (errors.length) {
      explanationMessageNode(card, `已生成 ${payload.generated} 项，失败 ${errors.length} 项：${errors.map((entry) => entry.error).join("；")}`, "error");
    } else {
      explanationMessageNode(card, `已生成 ${payload.generated} 项，请逐条核对后批准。`, "ok");
    }
  } catch (error) {
    explanationMessageNode(card, `补齐失败：${error.message}`, "error");
  }
}

async function exportBlueprintAction() {
  const bankId = state.detail?.id;
  if (!bankId) return;
  const card = byId("explanations-card");
  explanationMessageNode(card, "正在重导出 blueprint…");
  try {
    const payload = await explanationsFetch(
      `/api/banks/${encodeURIComponent(bankId)}/explanations/blueprint`,
      { method: "POST" },
    );
    explanationMessageNode(
      card,
      payload.candidate_count
        ? `已导出 ${payload.candidate_count} 个 candidate（${payload.item_count} 题）→ ${payload.batch_path}`
        : "当前题库还没有已批准的讲解-解答对，未生成 blueprint。",
      payload.candidate_count ? "ok" : "info",
    );
  } catch (error) {
    explanationMessageNode(card, `导出失败：${error.message}`, "error");
  }
}

async function approveApproachAction(approachId, button) {
  const bankId = state.detail?.id;
  const itemId = currentExplanationItemId();
  if (!bankId || !itemId) return;
  const scope = document.querySelector(`.explanation-approach[data-approach-id="${approachId}"]`);
  explanationMessageNode(scope, "正在批准并导出 blueprint…");
  if (button) button.disabled = true;
  try {
    const payload = await explanationsFetch(
      `${explanationsEndpoint(bankId, itemId)}/approaches/${encodeURIComponent(approachId)}/approve`,
      { method: "POST" },
    );
    if (explanationsState.itemId === itemId && payload.explanations) {
      applyExplanationsPayload(payload.explanations);
    }
    const fresh = document.querySelector(`.explanation-approach[data-approach-id="${approachId}"]`);
    explanationMessageNode(
      fresh,
      `已批准并导出 blueprint：${payload.export.candidate_count} 个 candidate → ${payload.export.batch_path}`,
      "ok",
    );
    playApprovalSound();
  } catch (error) {
    const fresh = document.querySelector(`.explanation-approach[data-approach-id="${approachId}"]`);
    explanationMessageNode(fresh, `批准失败：${error.message}`, "error");
  } finally {
    if (button) button.disabled = false;
  }
}

function pickRecordingMimeType() {
  if (!window.MediaRecorder) return "";
  for (const type of ["audio/webm;codecs=opus", "audio/webm", "audio/mp4"]) {
    if (MediaRecorder.isTypeSupported(type)) return type;
  }
  return "";
}

function formatRecordingDuration(seconds) {
  const minutes = Math.floor(seconds / 60);
  const rest = seconds % 60;
  return `${String(minutes).padStart(2, "0")}:${String(rest).padStart(2, "0")}`;
}

function updateRecordingButtons() {
  document.querySelectorAll(".explanation-record-button").forEach((button) => {
    const approachId = button.dataset.approachId;
    if (explanationRecording.approachId === approachId) {
      button.classList.add("is-recording");
      const seconds = Math.floor((Date.now() - explanationRecording.startedAt) / 1000);
      button.textContent = `■ 停止 ${formatRecordingDuration(seconds)}`;
      button.setAttribute("aria-pressed", "true");
    } else {
      button.classList.remove("is-recording");
      button.textContent = "● 录讲解";
      button.setAttribute("aria-pressed", "false");
      button.disabled = Boolean(explanationRecording.approachId);
    }
  });
}

async function toggleExplanationRecording(approachId) {
  if (explanationRecording.approachId) {
    stopExplanationRecording();
    return;
  }
  const bankId = state.detail?.id;
  const itemId = currentExplanationItemId();
  const scope = document.querySelector(`.explanation-approach[data-approach-id="${approachId}"]`);
  if (!bankId || !itemId) return;
  if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
    explanationMessageNode(scope, "当前浏览器不支持录音（需要 MediaRecorder 与麦克风权限）。", "error");
    return;
  }
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const mimeType = pickRecordingMimeType();
    const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
    explanationRecording.recorder = recorder;
    explanationRecording.chunks = [];
    explanationRecording.approachId = approachId;
    explanationRecording.bankId = bankId;
    explanationRecording.itemId = itemId;
    explanationRecording.mimeType = recorder.mimeType || mimeType || "audio/webm";
    explanationRecording.startedAt = Date.now();
    recorder.ondataavailable = (event) => {
      if (event.data?.size) explanationRecording.chunks.push(event.data);
    };
    recorder.onstop = () => {
      stream.getTracks().forEach((track) => track.stop());
      const chunks = explanationRecording.chunks;
      const meta = {
        bankId: explanationRecording.bankId,
        itemId: explanationRecording.itemId,
        approachId: explanationRecording.approachId,
        mimeType: explanationRecording.mimeType,
      };
      explanationRecording.recorder = null;
      explanationRecording.approachId = null;
      if (explanationRecording.timer) {
        clearInterval(explanationRecording.timer);
        explanationRecording.timer = null;
      }
      updateRecordingButtons();
      if (chunks.length) {
        void uploadExplanationRecording(meta, new Blob(chunks, { type: meta.mimeType }));
      }
    };
    recorder.start();
    explanationRecording.timer = setInterval(updateRecordingButtons, 500);
    updateRecordingButtons();
    explanationMessageNode(scope, "录音中…再次点击停止并转写。");
  } catch (error) {
    explanationRecording.approachId = null;
    updateRecordingButtons();
    explanationMessageNode(scope, `无法开始录音：${error.message}`, "error");
  }
}

function stopExplanationRecording() {
  if (explanationRecording.recorder?.state === "recording") {
    explanationRecording.recorder.stop();
  }
}

async function uploadExplanationRecording(meta, blob) {
  const base = explanationsEndpoint(meta.bankId, meta.itemId);
  const stillOnItem = explanationsState.itemId === meta.itemId;
  const scope = document.querySelector(`.explanation-approach[data-approach-id="${meta.approachId}"]`);
  if (stillOnItem) explanationMessageNode(scope, "录音结束，正在上传并转写…");
  try {
    const payload = await explanationsFetch(
      `${base}/approaches/${encodeURIComponent(meta.approachId)}/audio`,
      { method: "POST", headers: { "Content-Type": meta.mimeType }, body: blob },
    );
    if (explanationsState.itemId === meta.itemId) applyExplanationsPayload(payload);
    let fresh = document.querySelector(`.explanation-approach[data-approach-id="${meta.approachId}"]`);
    if (fresh) explanationMessageNode(fresh, "转写完成，正在润色讲解…");
    try {
      const polished = await explanationsFetch(
        `${base}/approaches/${encodeURIComponent(meta.approachId)}/polish`,
        { method: "POST" },
      );
      if (explanationsState.itemId === meta.itemId) applyExplanationsPayload(polished);
      fresh = document.querySelector(`.explanation-approach[data-approach-id="${meta.approachId}"]`);
      explanationMessageNode(fresh, "已根据录音润色讲解，可直接编辑、重新润色或批准。", "ok");
    } catch (error) {
      fresh = document.querySelector(`.explanation-approach[data-approach-id="${meta.approachId}"]`);
      explanationMessageNode(fresh, `录音已保存、转写成功，但润色失败：${error.message}。可点“润色讲解”重试。`, "error");
    }
  } catch (error) {
    const fresh = document.querySelector(`.explanation-approach[data-approach-id="${meta.approachId}"]`);
    explanationMessageNode(fresh, `录音上传或转写失败：${error.message}`, "error");
  }
}

byId("explanations-generate-missing").addEventListener("click", () => void generateMissingAction("explanation"));
byId("explanations-generate-solutions").addEventListener("click", () => void generateMissingAction("solution"));
byId("explanations-export-blueprint").addEventListener("click", () => void exportBlueprintAction());

// ---------------------------------------------------------------------------
// 教学策略 TeachingApproach（Phase 3）：录音(append-only) → 回放 → 润色 →
// 从解答初始化教学步骤 → 编辑 goal/entry/常见错误/skill → 批准冻结 canonical
// ---------------------------------------------------------------------------

const approachState = {
  payload: null,
  token: 0,
  itemId: null,
};

const approachRecording = {
  recorder: null,
  chunks: [],
  approachId: null,
  bankId: null,
  itemId: null,
  mimeType: "",
  timer: null,
  startedAt: 0,
};

const APPROACH_ORIGIN_LABELS = {
  ai_draft: "AI 建议",
  assignment: "解答脚手架",
  manual: "教师编辑",
  none: "未初始化",
};

const APPROACH_EDITOR_KEY = "question-bank-review:approach-identity";

function approachIdentity() {
  try {
    const stored = JSON.parse(window.localStorage.getItem(APPROACH_EDITOR_KEY) || "{}");
    return { author: stored.author || "", reviewer: stored.reviewer || "" };
  } catch {
    return { author: "", reviewer: "" };
  }
}

function saveApproachIdentity(author, reviewer) {
  try {
    window.localStorage.setItem(APPROACH_EDITOR_KEY, JSON.stringify({ author, reviewer }));
  } catch {
    /* localStorage 不可用时静默降级为会话内输入 */
  }
}

function approachEndpoint(bankId, itemId) {
  return `/api/banks/${encodeURIComponent(bankId)}/items/${encodeURIComponent(itemId)}/teaching-approach`;
}

function currentApproachItemId() {
  return approachState.itemId || currentExplanationItemId();
}

function findTeachingApproach(approachId) {
  for (const approach of approachState.payload?.approaches || []) {
    if (approach.id === approachId) return approach;
  }
  return null;
}

function approachMessageNode(scope, text, tone = "info") {
  if (!scope) return;
  const node = scope.classList?.contains("approach-item")
    ? scope.querySelector(".approach-item-message")
    : byId("approach-message");
  if (!node) return;
  node.textContent = text || "";
  node.dataset.tone = tone;
}

function applyApproachPayload(payload) {
  approachState.payload = payload?.approaches ? payload : payload?.teaching_approach;
  renderApproaches();
}

async function loadApproaches(itemId) {
  const bankId = state.detail?.id;
  if (!bankId || !itemId) return;
  const token = ++approachState.token;
  approachState.itemId = itemId;
  approachState.payload = null;
  approachMessageNode(byId("approach-card"), "");
  const body = byId("approach-body");
  if (body) {
    const loading = document.createElement("p");
    loading.className = "explanations-loading";
    loading.textContent = "正在读取教学策略…";
    body.replaceChildren(loading);
  }
  const bindingNode = byId("approach-binding");
  if (bindingNode) bindingNode.textContent = "";
  try {
    const payload = await explanationsFetch(approachEndpoint(bankId, itemId));
    if (token !== approachState.token) return;
    approachState.payload = payload;
    renderApproaches();
  } catch (error) {
    if (token !== approachState.token) return;
    const target = byId("approach-body");
    if (target) {
      const node = document.createElement("p");
      node.className = "explanations-error";
      node.textContent = `教学策略读取失败：${error.message}`;
      target.replaceChildren(node);
    }
  }
}

function approachStatusLabel(approach) {
  if (approach.approval) return "已批准（canonical 冻结）";
  const steps = approach.steps || [];
  const complete = steps.filter(
    (step) => step.intent?.trim() && step.narration?.trim()
      && step.expected_student_reasoning?.trim() && (step.skill_ids || []).length,
  ).length;
  return steps.length
    ? `草稿 · ${steps.length} 步（${complete} 步齐全，批准需 ≥3 步且全部齐全）`
    : "草稿 · 未初始化步骤";
}

function renderSubquestionPreview(item) {
  const section = byId("subquestion-preview-section");
  if (!section) return;
  const preview = item.subquestion_split_preview;
  section.hidden = !preview || !(preview.parts || []).length;
  if (section.hidden) return;
  setText("subquestion-preview-note", preview.note || "");
  const body = byId("subquestion-preview-body");
  body.replaceChildren();
  (preview.warnings || []).forEach((warning) => {
    const alert = document.createElement("p");
    alert.className = "subquestion-preview-warning";
    alert.textContent = `⚠ ${warning}`;
    body.append(alert);
  });
  (preview.parts || []).forEach((part) => {
    const row = document.createElement("div");
    row.className = "subquestion-preview-part";
    const head = document.createElement("p");
    head.className = "subquestion-preview-part-head";
    head.textContent = `（${part.part_id}）${part.prompt}`;
    const answer = document.createElement("p");
    answer.textContent = `答案：${part.answer || "（未提取）"}${part.range_constraint ? `（范围 ${part.range_constraint}）` : ""}`;
    const solution = document.createElement("p");
    solution.className = "source-text";
    solution.textContent = `解答：${part.solution || "（未提取）"}`;
    row.append(head, answer, solution);
    body.append(row);
  });
}

function renderApproaches() {
  const payload = approachState.payload;
  const body = byId("approach-body");
  if (!body || !payload) return;
  const identity = approachIdentity();
  const reviewerInput = byId("approach-reviewer-input");
  const authorInput = byId("approach-author-input");
  if (reviewerInput && !reviewerInput.value) reviewerInput.value = identity.reviewer;
  if (authorInput && !authorInput.value) authorInput.value = identity.author;

  body.replaceChildren();
  const question = payload.question;
  const bindingNode = byId("approach-binding");
  const questionParts = payload.question_parts || [];
  if (bindingNode) {
    bindingNode.textContent = question
      ? `绑定 canonical 题目：${question.artifact_id}${questionParts.length ? `（${questionParts.length} 个小问，Approach 须绑定具体小问）` : "（无小问，整题粒度）"}（批准时校验当前版本，question 漂移自动 stale）`
      : "该题没有 canonical QuestionTruth 绑定：不能创建教学策略（仅迁移题库支持）。";
    bindingNode.dataset.bound = question ? "true" : "false";
  }
  const partSelect = byId("approach-part-select");
  if (partSelect) {
    partSelect.hidden = !questionParts.length;
    partSelect.replaceChildren();
    if (questionParts.length) {
      const placeholder = document.createElement("option");
      placeholder.value = "";
      placeholder.textContent = "选择小问（新建时）";
      partSelect.append(placeholder);
      questionParts.forEach((part) => {
        const option = document.createElement("option");
        option.value = part.part_id;
        option.textContent = `（${part.part_id}）${(part.prompt || "").slice(0, 18)}`;
        partSelect.append(option);
      });
    }
  }
  const approaches = payload.approaches || [];
  if (!approaches.length) {
    const empty = document.createElement("p");
    empty.className = "explanation-empty";
    empty.textContent = "还没有整题教学策略：点右上「＋ 新建教学策略」，或先在小题讲解区试讲。";
    body.append(empty);
  }
  approaches.forEach((approach) => body.append(renderApproachItem(approach)));
  updateApproachRecordingButtons();
  scheduleExplanationsTypeset();
}

function renderApproachItem(approach) {
  const card = document.createElement("article");
  card.className = "approach-item";
  card.dataset.approachId = approach.id;

  const head = document.createElement("div");
  head.className = "explanation-approach-head";
  const title = document.createElement("input");
  title.type = "text";
  title.className = "approach-title-input";
  title.value = approach.title || "";
  title.setAttribute("aria-label", "教学策略标题（失焦保存）");
  title.addEventListener("blur", () => {
    if (title.value.trim() && title.value.trim() !== approach.title) {
      void saveApproachField(approach.id, { title: title.value.trim() });
    }
  });
  const status = badge(approachStatusLabel(approach), "chip-explanation-status");
  const authorChip = badge(`作者 ${approach.author || "?"}`, "chip-source");
  head.append(title, status, authorChip);
  const questionParts = approachState.payload?.question_parts || [];
  if (questionParts.length) {
    const partSelect = document.createElement("select");
    partSelect.className = "approach-part-select";
    partSelect.setAttribute("aria-label", "绑定小问");
    const emptyOption = document.createElement("option");
    emptyOption.value = "";
    emptyOption.textContent = "未选小问";
    partSelect.append(emptyOption);
    questionParts.forEach((part) => {
      const option = document.createElement("option");
      option.value = part.part_id;
      option.textContent = `第（${part.part_id}）问`;
      if (String(approach.part_id || "") === part.part_id) option.selected = true;
      partSelect.append(option);
    });
    if (!approach.part_id) emptyOption.selected = true;
    partSelect.addEventListener("change", () => {
      void saveApproachField(approach.id, { part_id: partSelect.value });
    });
    head.append(partSelect);
  } else if (approach.part_id) {
    head.append(badge(`第（${approach.part_id}）问`, "chip-source"));
  }

  const canonical = approach.canonical;
  if (canonical) {
    head.append(badge(
      `canonical ${canonical.artifact_id}@${canonical.version} · ${String(canonical.content_hash).slice(0, 14)}…`,
      "chip-blueprint",
    ));
  }
  card.append(head);

  // 录音按钮 + 证据链（音频回放 + 转写稿 + 润色稿，全部 append-only）
  const actions = document.createElement("div");
  actions.className = "explanation-approach-actions";
  const recordButton = document.createElement("button");
  recordButton.type = "button";
  recordButton.className = "explanation-record-button approach-record-button";
  recordButton.dataset.approachId = approach.id;
  recordButton.textContent = "● 录讲解";
  recordButton.addEventListener("click", () => {
    void toggleApproachRecording(approach.id);
  });
  actions.append(recordButton);

  const initStepsButton = ghostButton("从解答初始化步骤");
  initStepsButton.addEventListener("click", () => {
    void initApproachStepsAction(approach.id, initStepsButton);
  });
  actions.append(initStepsButton);

  const approveButton = ghostButton("批准冻结 canonical", "approve-button");
  approveButton.addEventListener("click", () => {
    void approveApproachFreezeAction(approach.id, approveButton);
  });
  actions.append(approveButton);

  const deleteButton = ghostButton("删除", "reject-button");
  deleteButton.addEventListener("click", () => {
    void deleteTeachingApproachAction(approach.id);
  });
  actions.append(deleteButton);
  card.append(actions);

  const evidence = approach.evidence || {};
  const recordings = evidence.recordings || [];
  if (recordings.length) {
    const evidenceBlock = document.createElement("div");
    evidenceBlock.className = "approach-evidence";
    const evidenceHead = document.createElement("p");
    evidenceHead.className = "approach-evidence-head";
    evidenceHead.textContent = `证据链（append-only）：录音 ${recordings.length} 个修订 · 润色 ${(evidence.polishes || []).length} 个修订 · 人工编辑痕迹 ${(evidence.manual_edit_notes || []).length} 条`;
    evidenceBlock.append(evidenceHead);
    for (const entry of recordings) {
      const row = document.createElement("div");
      row.className = "approach-recording";
      const audio = document.createElement("audio");
      audio.controls = true;
      audio.preload = "none";
      const bankId = state.detail?.id;
      const itemId = currentApproachItemId();
      audio.src = `${approachEndpoint(bankId, itemId)}/approaches/${encodeURIComponent(approach.id)}/audio/${entry.revision}`;
      const label = document.createElement("span");
      label.className = "approach-recording-label";
      label.textContent = `r${entry.revision} · ${entry.recorded_at || ""} · ${Math.max(1, Math.round((entry.audio_bytes || 0) / 1024))}KB`;
      row.append(label, audio);
      if (entry.transcript) {
        const details = document.createElement("details");
        details.className = "explanation-transcript";
        const summary = document.createElement("summary");
        summary.textContent = `转写稿 r${entry.revision}（ASR ${entry.asr?.model_id || "?"}）`;
        const transcript = document.createElement("pre");
        transcript.textContent = entry.transcript;
        details.append(summary, transcript);
        row.append(details);
      }
      evidenceBlock.append(row);
    }
    card.append(evidenceBlock);
  }
  if (approach.polished_text) {
    const details = document.createElement("details");
    details.className = "explanation-transcript";
    const summary = document.createElement("summary");
    summary.textContent = "润色稿（最新，供对照编辑）";
    const polished = document.createElement("pre");
    polished.textContent = approach.polished_text;
    details.append(summary, polished);
    card.append(details);
  }

  // goal / entry signal（P3-06）
  card.append(renderApproachTextField(approach, "goal", "教学目标（goal）", "这一题想让学生学会什么思路？"));
  card.append(renderApproachTextField(approach, "entry_signal", "入口信号（entry signal）", "学生从哪个条件切入？", true));

  // TeachingStep 编辑器（P3-05/P3-06）
  const stepsBlock = document.createElement("div");
  stepsBlock.className = "approach-steps";
  const stepsHead = document.createElement("div");
  stepsHead.className = "approach-steps-head";
  const stepsTitle = document.createElement("strong");
  stepsTitle.textContent = "教学步骤（TeachingStep）";
  const originChip = badge(APPROACH_ORIGIN_LABELS[approach.steps_origin] || approach.steps_origin, "chip-source");
  const addStepButton = ghostButton("＋ 加一步");
  addStepButton.addEventListener("click", () => {
    void addApproachStepAction(approach.id);
  });
  const saveStepsButton = ghostButton("保存全部步骤", "approve-button");
  saveStepsButton.addEventListener("click", () => {
    void saveApproachStepsAction(approach.id, stepsBlock, saveStepsButton);
  });
  stepsHead.append(stepsTitle, originChip, addStepButton, saveStepsButton);
  stepsBlock.append(stepsHead);
  (approach.steps || []).forEach((step, index) => {
    stepsBlock.append(renderApproachStepEditor(approach, step, index));
  });
  if (!(approach.steps || []).length) {
    const empty = document.createElement("p");
    empty.className = "explanation-empty";
    empty.textContent = "还没有教学步骤：点「从解答初始化步骤」生成草稿（AI 只建议），再逐字段编辑。";
    stepsBlock.append(empty);
  }
  card.append(stepsBlock);

  const message = document.createElement("p");
  message.className = "approach-item-message";
  message.setAttribute("role", "status");
  card.append(message);
  return card;
}

function renderApproachTextField(approach, field, labelText, placeholder, singleLine = false) {
  const block = document.createElement("div");
  block.className = "explanation-field";
  const head = document.createElement("div");
  head.className = "explanation-field-head";
  const label = document.createElement("span");
  label.className = "explanation-field-label";
  label.textContent = labelText;
  head.append(label);
  let input;
  if (singleLine) {
    input = document.createElement("input");
    input.type = "text";
  } else {
    input = document.createElement("textarea");
    input.rows = 2;
  }
  input.className = "explanation-textarea approach-field-input";
  input.value = approach[field] || "";
  input.placeholder = placeholder || "";
  input.setAttribute("aria-label", `${labelText}（失焦保存）`);
  input.addEventListener("blur", () => {
    const before = approach[field] || "";
    if (input.value.trim() === before.trim()) return;
    void saveApproachField(approach.id, { [field]: input.value });
  });
  block.append(head, input);
  return block;
}

function renderApproachStepEditor(approach, step, index) {
  const wrap = document.createElement("div");
  wrap.className = "approach-step";
  wrap.dataset.stepIndex = String(index);
  const head = document.createElement("div");
  head.className = "approach-step-head";
  const idLabel = document.createElement("strong");
  idLabel.textContent = step.step_id || `S${index + 1}`;
  const origin = badge(APPROACH_ORIGIN_LABELS[step.origin] || step.origin || "manual", "chip-source");
  const removeButton = ghostButton("移除本步", "reject-button");
  removeButton.addEventListener("click", () => {
    void removeApproachStepAction(approach.id, index);
  });
  head.append(idLabel, origin, removeButton);
  wrap.append(head);

  const fields = [
    ["intent", "教学意图（intent）", true],
    ["narration", "讲解词（narration）", false],
    ["expected_student_reasoning", "期望学生推理", false],
    ["accepted_alternatives", "可接受等价路径（每行一条）", false],
    ["common_errors", "常见错误（每行一条）", false],
  ];
  for (const [field, labelText, singleLine] of fields) {
    const fieldBlock = document.createElement("div");
    fieldBlock.className = "approach-step-field";
    const label = document.createElement("label");
    label.textContent = labelText;
    let input;
    if (singleLine) {
      input = document.createElement("input");
      input.type = "text";
    } else {
      input = document.createElement("textarea");
      input.rows = 2;
    }
    input.className = `approach-step-${field}`;
    const value = step[field];
    input.value = Array.isArray(value) ? value.join("\n") : value || "";
    fieldBlock.append(label, input);
    wrap.append(fieldBlock);
  }
  const skillBlock = document.createElement("div");
  skillBlock.className = "approach-step-field";
  const skillLabel = document.createElement("label");
  skillLabel.textContent = "skill refs";
  skillBlock.append(skillLabel);
  const skillIds = approachState.payload?.topic_skill_ids || [];
  const selected = new Set(step.skill_ids || []);
  for (const skillId of skillIds) {
    const checkboxLabel = document.createElement("label");
    checkboxLabel.className = "approach-skill-option";
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.value = skillId;
    checkbox.checked = selected.has(skillId);
    checkbox.className = "approach-step-skill";
    checkboxLabel.append(checkbox, document.createTextNode(` ${skillId}`));
    skillBlock.append(checkboxLabel);
  }
  wrap.append(skillBlock);
  return wrap;
}

function collectStepsFromDom(approachId) {
  const card = document.querySelector(`.approach-item[data-approach-id="${approachId}"]`);
  if (!card) return null;
  const steps = [];
  card.querySelectorAll(".approach-step").forEach((stepNode) => {
    const read = (selector) => stepNode.querySelector(selector)?.value || "";
    steps.push({
      intent: read(".approach-step-intent"),
      narration: read(".approach-step-narration"),
      expected_student_reasoning: read(".approach-step-expected_student_reasoning"),
      accepted_alternatives: read(".approach-step-accepted_alternatives").split("\n").map((line) => line.trim()).filter(Boolean),
      common_errors: read(".approach-step-common_errors").split("\n").map((line) => line.trim()).filter(Boolean),
      skill_ids: [...stepNode.querySelectorAll(".approach-step-skill:checked")].map((node) => node.value),
    });
  });
  return steps;
}

async function saveApproachField(approachId, body) {
  const bankId = state.detail?.id;
  const itemId = currentApproachItemId();
  if (!bankId || !itemId) return;
  const scope = document.querySelector(`.approach-item[data-approach-id="${approachId}"]`);
  approachMessageNode(scope, "保存中…");
  try {
    const payload = await explanationsFetch(
      `${approachEndpoint(bankId, itemId)}/approaches/${encodeURIComponent(approachId)}`,
      {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...body, editor: reviewerInputValue() }),
      },
    );
    if (approachState.itemId === itemId) applyApproachPayload(payload);
    const fresh = document.querySelector(`.approach-item[data-approach-id="${approachId}"]`);
    approachMessageNode(fresh, "已保存（留痕到 manual_edit_notes）。", "ok");
  } catch (error) {
    const fresh = document.querySelector(`.approach-item[data-approach-id="${approachId}"]`);
    approachMessageNode(fresh, `保存失败：${error.message}`, "error");
  }
}

async function saveApproachStepsAction(approachId, stepsBlock, button) {
  const steps = collectStepsFromDom(approachId);
  if (!steps) return;
  if (button) button.disabled = true;
  try {
    await saveApproachFieldRaw(approachId, { steps });
    const fresh = document.querySelector(`.approach-item[data-approach-id="${approachId}"]`);
    approachMessageNode(fresh, `已保存 ${steps.length} 个教学步骤。`, "ok");
  } finally {
    if (button) button.disabled = false;
  }
}

async function saveApproachFieldRaw(approachId, body) {
  const bankId = state.detail?.id;
  const itemId = currentApproachItemId();
  const payload = await explanationsFetch(
    `${approachEndpoint(bankId, itemId)}/approaches/${encodeURIComponent(approachId)}`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...body, editor: reviewerInputValue() }),
    },
  );
  if (approachState.itemId === itemId) applyApproachPayload(payload);
  return payload;
}

async function addApproachStepAction(approachId) {
  const found = findTeachingApproach(approachId);
  if (!found) return;
  const steps = collectStepsFromDom(approachId) || [];
  steps.push({
    intent: "",
    narration: "",
    expected_student_reasoning: "",
    accepted_alternatives: [],
    common_errors: [],
    skill_ids: [],
  });
  await saveApproachFieldRaw(approachId, { steps });
}

async function removeApproachStepAction(approachId, index) {
  const steps = collectStepsFromDom(approachId);
  if (!steps) return;
  steps.splice(index, 1);
  await saveApproachFieldRaw(approachId, { steps });
}

async function createApproachTeachingAction() {
  const bankId = state.detail?.id;
  const itemId = currentApproachItemId();
  if (!bankId || !itemId) return;
  const title = window.prompt("教学策略标题（如：从公共角正推）");
  if (!title || !title.trim()) return;
  const author = authorInputValue();
  const partId = (byId("approach-part-select")?.value || "").trim();
  if ((approachState.payload?.question_parts || []).length && !partId) {
    approachMessageNode(byId("approach-card"), "该题含小问：新建教学策略前请先在「选择小问」下拉中选定小问（ADR-005 part 绑定）。", "error");
    return;
  }
  saveApproachIdentity(author, reviewerInputValue());
  try {
    const payload = await explanationsFetch(`${approachEndpoint(bankId, itemId)}/approaches`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title: title.trim(), author, part_id: partId }),
    });
    if (approachState.itemId === itemId) applyApproachPayload(payload);
  } catch (error) {
    approachMessageNode(byId("approach-card"), `新建失败：${error.message}`, "error");
  }
}

async function deleteTeachingApproachAction(approachId) {
  const found = findTeachingApproach(approachId);
  if (!found) return;
  if (found.canonical) {
    approachMessageNode(byId("approach-card"), "已有 canonical 冻结版本的教学策略不能删除：请编辑后重新批准。", "error");
    return;
  }
  if (!window.confirm("删除该教学策略工作副本？（尚未冻结 canonical）")) return;
  const bankId = state.detail?.id;
  const itemId = currentApproachItemId();
  try {
    const payload = await explanationsFetch(
      `${approachEndpoint(bankId, itemId)}/approaches/${encodeURIComponent(approachId)}`,
      { method: "DELETE" },
    );
    if (approachState.itemId === itemId) applyApproachPayload(payload);
  } catch (error) {
    approachMessageNode(byId("approach-card"), `删除失败：${error.message}`, "error");
  }
}

async function initApproachStepsAction(approachId, button) {
  const found = findTeachingApproach(approachId);
  if (!found) return;
  const hasSteps = (found.steps || []).length > 0;
  if (hasSteps && !window.confirm("已有教学步骤，重新初始化会覆盖当前草稿。继续？")) return;
  const bankId = state.detail?.id;
  const itemId = currentApproachItemId();
  const scope = document.querySelector(`.approach-item[data-approach-id="${approachId}"]`);
  approachMessageNode(scope, "正在初始化教学步骤草稿…");
  if (button) button.disabled = true;
  try {
    const payload = await explanationsFetch(
      `${approachEndpoint(bankId, itemId)}/approaches/${encodeURIComponent(approachId)}/steps/init`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ use_ai: true, replace: hasSteps }),
      },
    );
    if (approachState.itemId === itemId) applyApproachPayload(payload);
    const fresh = document.querySelector(`.approach-item[data-approach-id="${approachId}"]`);
    approachMessageNode(fresh, "步骤草稿已生成（AI 只建议）：请逐字段核对编辑后保存。", "ok");
  } catch (error) {
    const fresh = document.querySelector(`.approach-item[data-approach-id="${approachId}"]`);
    approachMessageNode(fresh, `初始化失败：${error.message}`, "error");
  } finally {
    if (button) button.disabled = false;
  }
}

async function approveApproachFreezeAction(approachId, button) {
  const bankId = state.detail?.id;
  const itemId = currentApproachItemId();
  if (!bankId || !itemId) return;
  const reviewer = reviewerInputValue();
  if (!reviewer) {
    approachMessageNode(byId("approach-card"), "请先在右上填写审核人 ID。", "error");
    return;
  }
  const reviewNote = window.prompt("审核备注（review note，将写入 canonical approval）", "") ?? "";
  saveApproachIdentity(authorInputValue(), reviewer);
  const scope = document.querySelector(`.approach-item[data-approach-id="${approachId}"]`);
  approachMessageNode(scope, "正在批准并冻结 canonical…");
  if (button) button.disabled = true;
  try {
    const payload = await explanationsFetch(
      `${approachEndpoint(bankId, itemId)}/approaches/${encodeURIComponent(approachId)}/approve`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ reviewer_id: reviewer, review_note: reviewNote.trim() }),
      },
    );
    if (approachState.itemId === itemId && payload.teaching_approach) {
      applyApproachPayload(payload.teaching_approach);
    }
    const fresh = document.querySelector(`.approach-item[data-approach-id="${approachId}"]`);
    approachMessageNode(
      fresh,
      `已冻结 ${payload.canonical.artifact_id}@${payload.canonical.version}（${payload.canonical.content_hash.slice(0, 14)}…）。`,
      "ok",
    );
    playApprovalSound();
  } catch (error) {
    const fresh = document.querySelector(`.approach-item[data-approach-id="${approachId}"]`);
    approachMessageNode(fresh, `批准失败：${error.message}`, "error");
  } finally {
    if (button) button.disabled = false;
  }
}

function reviewerInputValue() {
  return byId("approach-reviewer-input")?.value.trim() || "";
}

function authorInputValue() {
  return byId("approach-author-input")?.value.trim() || "question-bank-review-ui";
}

function updateApproachRecordingButtons() {
  document.querySelectorAll(".approach-record-button").forEach((button) => {
    const approachId = button.dataset.approachId;
    if (approachRecording.approachId === approachId) {
      button.classList.add("is-recording");
      const seconds = Math.floor((Date.now() - approachRecording.startedAt) / 1000);
      button.textContent = `■ 停止 ${formatRecordingDuration(seconds)}`;
      button.setAttribute("aria-pressed", "true");
    } else {
      button.classList.remove("is-recording");
      button.textContent = "● 录讲解";
      button.setAttribute("aria-pressed", "false");
      button.disabled = Boolean(approachRecording.approachId);
    }
  });
}

async function toggleApproachRecording(approachId) {
  if (approachRecording.approachId) {
    stopApproachRecording();
    return;
  }
  const bankId = state.detail?.id;
  const itemId = currentApproachItemId();
  const scope = document.querySelector(`.approach-item[data-approach-id="${approachId}"]`);
  if (!bankId || !itemId) return;
  if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
    approachMessageNode(scope, "当前浏览器不支持录音（需要 MediaRecorder 与麦克风权限）。", "error");
    return;
  }
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const mimeType = pickRecordingMimeType();
    const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
    approachRecording.recorder = recorder;
    approachRecording.chunks = [];
    approachRecording.approachId = approachId;
    approachRecording.bankId = bankId;
    approachRecording.itemId = itemId;
    approachRecording.mimeType = recorder.mimeType || mimeType || "audio/webm";
    approachRecording.startedAt = Date.now();
    recorder.ondataavailable = (event) => {
      if (event.data?.size) approachRecording.chunks.push(event.data);
    };
    recorder.onstop = () => {
      stream.getTracks().forEach((track) => track.stop());
      const chunks = approachRecording.chunks;
      const meta = {
        bankId: approachRecording.bankId,
        itemId: approachRecording.itemId,
        approachId: approachRecording.approachId,
        mimeType: approachRecording.mimeType,
      };
      approachRecording.recorder = null;
      approachRecording.approachId = null;
      if (approachRecording.timer) {
        clearInterval(approachRecording.timer);
        approachRecording.timer = null;
      }
      updateApproachRecordingButtons();
      if (chunks.length) {
        void uploadApproachRecording(meta, new Blob(chunks, { type: meta.mimeType }));
      }
    };
    recorder.start();
    approachRecording.timer = setInterval(updateApproachRecordingButtons, 500);
    updateApproachRecordingButtons();
    approachMessageNode(scope, "录音中…再次点击停止并转写（append-only 新修订）。");
  } catch (error) {
    approachRecording.approachId = null;
    updateApproachRecordingButtons();
    approachMessageNode(scope, `无法开始录音：${error.message}`, "error");
  }
}

function stopApproachRecording() {
  if (approachRecording.recorder?.state === "recording") {
    approachRecording.recorder.stop();
  }
}

async function uploadApproachRecording(meta, blob) {
  const base = approachEndpoint(meta.bankId, meta.itemId);
  const stillOnItem = approachState.itemId === meta.itemId;
  const scope = document.querySelector(`.approach-item[data-approach-id="${meta.approachId}"]`);
  if (stillOnItem) approachMessageNode(scope, "录音结束，正在上传并转写…");
  try {
    const payload = await explanationsFetch(
      `${base}/approaches/${encodeURIComponent(meta.approachId)}/audio`,
      { method: "POST", headers: { "Content-Type": meta.mimeType }, body: blob },
    );
    if (approachState.itemId === meta.itemId) applyApproachPayload(payload);
    let fresh = document.querySelector(`.approach-item[data-approach-id="${meta.approachId}"]`);
    if (fresh) approachMessageNode(fresh, "转写完成，正在润色（新修订，不覆盖转写稿）…");
    try {
      const polished = await explanationsFetch(
        `${base}/approaches/${encodeURIComponent(meta.approachId)}/polish`,
        { method: "POST" },
      );
      if (approachState.itemId === meta.itemId) applyApproachPayload(polished);
      fresh = document.querySelector(`.approach-item[data-approach-id="${meta.approachId}"]`);
      approachMessageNode(fresh, "润色完成：对照录音与转写稿编辑步骤后批准。", "ok");
    } catch (error) {
      fresh = document.querySelector(`.approach-item[data-approach-id="${meta.approachId}"]`);
      approachMessageNode(fresh, `录音已保存、转写成功，但润色失败：${error.message}。可稍后重试润色。`, "error");
    }
  } catch (error) {
    const fresh = document.querySelector(`.approach-item[data-approach-id="${meta.approachId}"]`);
    approachMessageNode(fresh, `录音上传或转写失败：${error.message}`, "error");
  }
}

byId("approach-create").addEventListener("click", () => void createApproachTeachingAction());

loadBanks();
