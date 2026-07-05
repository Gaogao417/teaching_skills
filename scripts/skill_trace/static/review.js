(function () {
  const COGNITIVE_LAYERS = ["L3_strategy", "L0_structure", "L1_encoding", "L2_execution"];
  const REUSE_LEVELS = ["generic_action", "domain_action", "pattern_step", "instance_step"];
  const DEPRECATED_STEP_FIELDS = ["teacher_rationale", "input_state", "output_state", "source_evidence", "hint_intent"];
  const SUMMARY_LABELS = {
    target: "目标",
    core_strategy: "核心策略",
    target_relation_chain: "关系链",
    main_student_blocker: "主要卡点",
    preferred_path: "推荐路径",
  };

  let draft = null;
  let selectedIndex = 0;

  const fields = {
    stepName: document.getElementById("step-name"),
    domain: document.getElementById("domain"),
    cognitiveLayer: document.getElementById("cognitive-layer"),
    reuseLevel: document.getElementById("reuse-level"),
    studentAction: document.getElementById("student-action"),
    commonErrors: document.getElementById("common-errors"),
    isCoreStep: document.getElementById("is-core-step"),
    reviewerNote: document.getElementById("reviewer-note"),
    validationOutput: document.getElementById("validation-output"),
    statusDot: document.getElementById("review-status-dot"),
    statusText: document.getElementById("review-status-text"),
  };

  function optionList(select, values) {
    select.innerHTML = "";
    values.forEach((value) => {
      const option = document.createElement("option");
      option.value = value;
      option.textContent = value;
      select.appendChild(option);
    });
  }

  async function loadDraft() {
    optionList(fields.cognitiveLayer, COGNITIVE_LAYERS);
    optionList(fields.reuseLevel, REUSE_LEVELS);
    bindSourceTabs();

    const draftId = decodeURIComponent(window.location.pathname.split("/").pop());
    const response = await fetch(`/api/drafts/${draftId}`);
    const payload = await response.json();
    if (!response.ok) {
      showResult(payload);
      return;
    }
    draft = pruneDeprecatedStepFields(payload.draft_json);
    selectedIndex = 0;
    renderSource(payload);
    renderSteps();
    renderEditor();
    validateLocal();
  }

  function pruneDeprecatedStepFields(payload) {
    (payload.steps || []).forEach((step) => {
      DEPRECATED_STEP_FIELDS.forEach((field) => delete step[field]);
    });
    return payload;
  }

  function bindSourceTabs() {
    document.querySelectorAll("[data-source-target]").forEach((tab) => {
      tab.addEventListener("click", () => {
        document.querySelectorAll("[data-source-target]").forEach((node) => node.classList.remove("is-active"));
        document.querySelectorAll(".source-card").forEach((panel) => {
          panel.hidden = panel.id !== tab.dataset.sourceTarget;
        });
        tab.classList.add("is-active");
      });
    });
  }

  function renderSource(payload) {
    const problem = draft.problem_case;
    document.getElementById("problem-title").textContent = problem.title || draft.draft_id;
    document.getElementById("draft-id").textContent = `draft ${draft.draft_id}`;
    document.getElementById("case-id").textContent = `case ${payload.problem_case_id}`;
    document.getElementById("student-level").textContent = problem.target_student_level || "未标学生层级";

    const threadWarning = document.getElementById("thread-warning");
    if ((draft.codex_thread_id || "").startsWith("manual_")) {
      threadWarning.textContent = "非真实 Codex thread id：当前记录由本地工具生成，后续 SDK 续接 thread 时不能直接使用。";
      threadWarning.hidden = false;
    } else {
      threadWarning.textContent = "";
      threadWarning.hidden = true;
    }

    document.getElementById("raw-problem").textContent = problem.raw_problem || "";
    document.getElementById("provided-solution").textContent = problem.provided_solution || "";
    document.getElementById("expected-thinking").textContent = problem.expected_thinking || "";
    renderTopicTags(problem.topic_tags || []);
    renderTraceSummary(draft.trace_summary || {});
  }

  function renderTopicTags(tags) {
    const target = document.getElementById("topic-tags");
    target.innerHTML = "";
    tags.forEach((tag) => {
      const chip = document.createElement("span");
      chip.className = "tag";
      chip.textContent = tag;
      target.appendChild(chip);
    });
  }

  function renderTraceSummary(summary) {
    const list = document.getElementById("trace-summary");
    list.innerHTML = "";
    const knownKeys = Object.keys(SUMMARY_LABELS);
    const orderedKeys = [
      ...knownKeys.filter((key) => Object.prototype.hasOwnProperty.call(summary, key)),
      ...Object.keys(summary).filter((key) => !knownKeys.includes(key)),
    ];
    const entries = orderedKeys
      .map((key) => [key, summary[key]])
      .filter(([, value]) => value !== undefined && value !== null && String(value).trim());
    entries.forEach(([key, value]) => {
      const row = document.createElement("div");
      row.className = "summary-item";
      const term = document.createElement("dt");
      const description = document.createElement("dd");
      term.textContent = SUMMARY_LABELS[key] || key;
      description.textContent = Array.isArray(value) ? value.join("，") : String(value);
      row.append(term, description);
      list.appendChild(row);
    });
  }

  function renderSteps() {
    if (!draft) return;
    const list = document.getElementById("steps-list");
    list.innerHTML = "";
    draft.steps.forEach((step, index) => {
      const card = document.createElement("button");
      card.type = "button";
      card.className = "step-card";
      card.setAttribute("aria-label", `编辑 step ${step.order}: ${step.name || "未命名"}`);
      if (index === selectedIndex) card.classList.add("is-selected");
      card.addEventListener("click", () => {
        saveEditor();
        selectedIndex = index;
        renderSteps();
        renderEditor();
      });

      const indexNode = document.createElement("span");
      indexNode.className = "step-index";
      indexNode.textContent = String(step.order || index + 1);

      const main = document.createElement("span");
      main.className = "step-main";

      const titleRow = document.createElement("span");
      titleRow.className = "step-title-row";
      const title = document.createElement("span");
      title.className = "step-title";
      title.textContent = step.name || "未命名 step";
      const core = document.createElement("span");
      core.className = `chip ${step.is_core_step === false ? "chip-support" : ""}`;
      core.textContent = step.is_core_step === false ? "support" : "core";
      titleRow.append(title, core);

      const action = document.createElement("span");
      action.className = "step-action";
      action.textContent = step.student_action_norm || "student_action_norm 为空";

      const chips = document.createElement("span");
      chips.className = "chip-row";
      chips.append(
        chip(step.cognitive_layer || "missing layer", "chip-layer"),
        chip(step.reuse_level || "missing reuse", "chip-reuse"),
        chip(step.domain || "general", "")
      );
      if ((step.common_errors || []).length) chips.append(chip(`${step.common_errors.length} errors`, "chip-error"));

      main.append(titleRow, action, chips);
      card.append(indexNode, main);
      list.appendChild(card);
    });

    document.getElementById("step-count").textContent = `${draft.steps.length} steps`;
    document.getElementById("core-count").textContent = `${draft.steps.filter((step) => step.is_core_step !== false).length} core`;
  }

  function chip(text, className) {
    const node = document.createElement("span");
    node.className = `chip ${className}`.trim();
    node.textContent = text;
    return node;
  }

  function renderEditor() {
    const step = currentStep();
    if (!step) return;
    document.getElementById("editor-title").textContent = `${step.order || selectedIndex + 1}. ${step.name || "未命名 step"}`;
    fields.stepName.value = step.name || "";
    fields.domain.value = step.domain || "general";
    fields.cognitiveLayer.value = step.cognitive_layer || "L0_structure";
    fields.reuseLevel.value = step.reuse_level || "instance_step";
    fields.studentAction.value = step.student_action_norm || "";
    fields.commonErrors.value = (step.common_errors || []).join("\n");
    fields.isCoreStep.checked = step.is_core_step !== false;
  }

  function saveEditor() {
    const step = currentStep();
    if (!step) return;
    step.name = fields.stepName.value;
    step.domain = fields.domain.value || "general";
    step.cognitive_layer = fields.cognitiveLayer.value;
    step.reuse_level = fields.reuseLevel.value;
    step.student_action_norm = fields.studentAction.value;
    step.common_errors = fields.commonErrors.value.split("\n").map((item) => item.trim()).filter(Boolean);
    step.is_core_step = fields.isCoreStep.checked;
  }

  function currentStep() {
    if (!draft || !draft.steps.length) return null;
    selectedIndex = Math.max(0, Math.min(selectedIndex, draft.steps.length - 1));
    return draft.steps[selectedIndex];
  }

  function normalizeOrder() {
    draft.steps.forEach((step, index) => {
      step.order = index + 1;
      if (!step.step_id) step.step_id = `s${index + 1}`;
    });
  }

  function addStep() {
    saveEditor();
    draft.steps.splice(selectedIndex + 1, 0, {
      step_id: `s${Date.now()}`,
      order: selectedIndex + 2,
      name: "新步骤",
      cognitive_layer: "L0_structure",
      reuse_level: "instance_step",
      domain: "general",
      student_action_norm: "",
      common_errors: [],
      is_core_step: true,
    });
    selectedIndex += 1;
    normalizeOrder();
    renderSteps();
    renderEditor();
    validateLocal();
  }

  function deleteStep() {
    if (draft.steps.length <= 1) return;
    draft.steps.splice(selectedIndex, 1);
    selectedIndex = Math.max(0, selectedIndex - 1);
    normalizeOrder();
    renderSteps();
    renderEditor();
    validateLocal();
  }

  function moveSelected(offset) {
    saveEditor();
    const target = selectedIndex + offset;
    if (target < 0 || target >= draft.steps.length) return;
    const step = draft.steps.splice(selectedIndex, 1)[0];
    draft.steps.splice(target, 0, step);
    selectedIndex = target;
    normalizeOrder();
    renderSteps();
    renderEditor();
    validateLocal();
  }

  function validateLocal() {
    if (!draft) return false;
    saveEditor();
    const errors = [];
    const warnings = [];
    const orders = new Set();
    draft.steps.forEach((step) => {
      if (orders.has(step.order)) errors.push(`order 重复: ${step.order}`);
      orders.add(step.order);
      if (!step.cognitive_layer) errors.push(`${step.step_id}: cognitive_layer 不能为空`);
      if (!step.reuse_level) errors.push(`${step.step_id}: reuse_level 不能为空`);
      if (!step.student_action_norm || !step.student_action_norm.trim()) {
        errors.push(`${step.step_id}: student_action_norm 不能为空`);
      }
      if (/找.{0,12}(并|然后|再).{0,12}(算|计算|求|解)/.test(step.student_action_norm || "")) {
        warnings.push(`${step.step_id}: 可能包含复合动作`);
      }
    });
    if (!draft.codex_thread_id) errors.push("codex_thread_id 不能为空");
    if ((draft.codex_thread_id || "").startsWith("manual_")) {
      warnings.push("codex_thread_id 是本地生成的 manual id，不是真实 Codex thread id");
    }
    if (!draft.problem_case.raw_problem) errors.push("raw_problem 不能为空");
    if (!draft.steps.some((step) => step.cognitive_layer === "L3_strategy")) errors.push("至少需要一个 L3_strategy");
    if (!draft.steps.some((step) => step.cognitive_layer === "L0_structure" || step.cognitive_layer === "L1_encoding")) {
      errors.push("至少需要一个 L0_structure 或 L1_encoding");
    }
    const result = { ok: errors.length === 0, errors, warnings };
    showResult(result);
    renderSteps();
    return result.ok;
  }

  async function submitReview() {
    if (!validateLocal()) return;
    const response = await fetch("/api/reviews", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        draft_id: draft.draft_id,
        codex_thread_id: draft.codex_thread_id,
        reviewed_json: pruneDeprecatedStepFields(draft),
        reviewer_note: fields.reviewerNote.value,
      }),
    });
    const payload = await response.json();
    showResult(payload);
  }

  function showResult(payload) {
    fields.validationOutput.textContent = JSON.stringify(payload, null, 2);
    const ok = payload.ok === true || payload.status === "reviewed";
    const hasErrors = Array.isArray(payload.errors) && payload.errors.length > 0;
    fields.statusDot.classList.toggle("ok", ok);
    fields.statusDot.classList.toggle("error", hasErrors);
    fields.statusText.textContent = ok ? "可提交" : hasErrors ? "需修正" : "待校验";
  }

  document.getElementById("add-step").addEventListener("click", addStep);
  document.getElementById("delete-step").addEventListener("click", deleteStep);
  document.getElementById("move-up").addEventListener("click", () => moveSelected(-1));
  document.getElementById("move-down").addEventListener("click", () => moveSelected(1));
  document.getElementById("validate").addEventListener("click", validateLocal);
  document.getElementById("submit-review").addEventListener("click", submitReview);
  document.querySelectorAll("input, textarea, select").forEach((node) => {
    node.addEventListener("input", () => {
      saveEditor();
      renderSteps();
    });
    node.addEventListener("change", () => {
      saveEditor();
      renderSteps();
      renderEditor();
    });
  });

  loadDraft();
})();
