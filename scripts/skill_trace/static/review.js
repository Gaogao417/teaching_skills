(function () {
  const COGNITIVE_LAYERS = ["L3_strategy", "L0_structure", "L1_encoding", "L2_execution"];
  const REUSE_LEVELS = ["generic_action", "domain_action", "pattern_step", "instance_step"];

  let draft = null;
  let selectedIndex = 0;

  const fields = {
    stepName: document.getElementById("step-name"),
    cognitiveLayer: document.getElementById("cognitive-layer"),
    reuseLevel: document.getElementById("reuse-level"),
    studentAction: document.getElementById("student-action"),
    teacherRationale: document.getElementById("teacher-rationale"),
    inputState: document.getElementById("input-state"),
    outputState: document.getElementById("output-state"),
    commonErrors: document.getElementById("common-errors"),
    isCoreStep: document.getElementById("is-core-step"),
    reviewerNote: document.getElementById("reviewer-note"),
    validationOutput: document.getElementById("validation-output"),
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
    const draftId = decodeURIComponent(window.location.pathname.split("/").pop());
    const response = await fetch(`/api/drafts/${draftId}`);
    const payload = await response.json();
    if (!response.ok) {
      showResult(payload);
      return;
    }
    draft = payload.draft_json;
    selectedIndex = 0;
    renderSource(payload);
    renderSteps();
    renderEditor();
    validateLocal();
  }

  function renderSource(payload) {
    const problem = draft.problem_case;
    document.getElementById("problem-title").textContent = problem.title || draft.draft_id;
    document.getElementById("draft-meta").textContent =
      `draft: ${draft.draft_id} · thread: ${draft.codex_thread_id} · case: ${payload.problem_case_id}`;
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
  }

  function renderSteps() {
    const body = document.getElementById("steps-body");
    body.innerHTML = "";
    draft.steps.forEach((step, index) => {
      const row = document.createElement("tr");
      if (index === selectedIndex) row.classList.add("selected");
      row.addEventListener("click", () => {
        saveEditor();
        selectedIndex = index;
        renderSteps();
        renderEditor();
      });
      [step.order, step.name, step.cognitive_layer, step.reuse_level].forEach((value) => {
        const cell = document.createElement("td");
        cell.textContent = value;
        row.appendChild(cell);
      });
      body.appendChild(row);
    });
  }

  function renderEditor() {
    const step = currentStep();
    if (!step) return;
    fields.stepName.value = step.name || "";
    fields.cognitiveLayer.value = step.cognitive_layer || "L0_structure";
    fields.reuseLevel.value = step.reuse_level || "instance_step";
    fields.studentAction.value = step.student_action_norm || "";
    fields.teacherRationale.value = step.teacher_rationale || "";
    fields.inputState.value = step.input_state || "";
    fields.outputState.value = step.output_state || "";
    fields.commonErrors.value = (step.common_errors || []).join("\n");
    fields.isCoreStep.checked = step.is_core_step !== false;
  }

  function saveEditor() {
    const step = currentStep();
    if (!step) return;
    step.name = fields.stepName.value;
    step.cognitive_layer = fields.cognitiveLayer.value;
    step.reuse_level = fields.reuseLevel.value;
    step.student_action_norm = fields.studentAction.value;
    step.teacher_rationale = fields.teacherRationale.value;
    step.input_state = fields.inputState.value;
    step.output_state = fields.outputState.value;
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
      teacher_rationale: "",
      input_state: "",
      output_state: "",
      source_evidence: "",
      common_errors: [],
      hint_intent: "",
      is_core_step: true,
    });
    selectedIndex += 1;
    normalizeOrder();
    renderSteps();
    renderEditor();
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
  }

  function validateLocal() {
    saveEditor();
    const errors = [];
    const warnings = [];
    const orders = new Set();
    draft.steps.forEach((step) => {
      if (orders.has(step.order)) errors.push(`order 重复: ${step.order}`);
      orders.add(step.order);
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
        reviewed_json: draft,
        reviewer_note: fields.reviewerNote.value,
      }),
    });
    const payload = await response.json();
    showResult(payload);
  }

  function showResult(payload) {
    fields.validationOutput.textContent = JSON.stringify(payload, null, 2);
  }

  document.getElementById("add-step").addEventListener("click", addStep);
  document.getElementById("delete-step").addEventListener("click", deleteStep);
  document.getElementById("move-up").addEventListener("click", () => moveSelected(-1));
  document.getElementById("move-down").addEventListener("click", () => moveSelected(1));
  document.getElementById("validate").addEventListener("click", validateLocal);
  document.getElementById("submit-review").addEventListener("click", submitReview);
  document.querySelectorAll("input, textarea, select").forEach((node) => {
    node.addEventListener("change", saveEditor);
  });

  loadDraft();
})();
