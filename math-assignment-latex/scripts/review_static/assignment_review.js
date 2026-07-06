(function () {
  const QUESTION_TYPES = new Set(["choice", "fillin", "problem", "short_answer", "variation_training"]);
  let state = null;
  let student = null;
  let teacher = null;
  let sectionIndex = 0;
  let blockIndex = 0;
  let lastTexPath = "";

  const $ = (id) => document.getElementById(id);

  async function init() {
    const response = await fetch("/api/state");
    state = await response.json();
    student = state.student;
    teacher = state.teacher;
    $("doc-title").textContent = student.meta?.title || "练习审核";
    $("doc-path").textContent = [state.student_path, state.teacher_path].filter(Boolean).join(" / ");
    bindButtons();
    renderAll();
  }

  function bindButtons() {
    $("save-reviewed").addEventListener("click", saveReviewed);
    $("sync-teacher").addEventListener("click", syncTeacherStem);
    $("rebuild-answer-key").addEventListener("click", rebuildAnswerKey);
    $("validate-yaml").addEventListener("click", validateYaml);
    $("render-latex").addEventListener("click", renderLatex);
    $("compile-pdf").addEventListener("click", compilePdf);
    $("save-agent-request").addEventListener("click", saveAgentRequest);
  }

  function renderAll() {
    renderSections();
    renderQuestions();
    renderEditor();
  }

  function sections(doc) {
    return doc?.sections || [];
  }

  function currentSection(doc = student) {
    return sections(doc)[sectionIndex] || { blocks: [] };
  }

  function questionBlocks(section) {
    return (section.blocks || []).map((block, index) => ({ block, index })).filter(({ block }) => QUESTION_TYPES.has(block.type));
  }

  function currentStudentBlock() {
    return (currentSection(student).blocks || [])[blockIndex] || null;
  }

  function currentTeacherBlock() {
    if (!teacher) return null;
    const studentBlock = currentStudentBlock();
    const teacherSection = currentSection(teacher);
    return (teacherSection.blocks || []).find((block) => block.id && block.id === studentBlock?.id) || (teacherSection.blocks || [])[blockIndex] || null;
  }

  function renderSections() {
    const target = $("section-list");
    target.innerHTML = "";
    sections(student).forEach((section, index) => {
      const questions = questionBlocks(section);
      const points = questions.reduce((sum, item) => sum + Number(item.block.points || 0), 0);
      const counts = countTypes(questions.map((item) => item.block));
      const button = document.createElement("button");
      button.type = "button";
      button.className = `section-card ${index === sectionIndex ? "is-selected" : ""}`;
      button.innerHTML = `
        <span class="card-title">${escapeHtml(section.title || section.id || `题组 ${index + 1}`)}</span>
        <span class="muted">${questions.length} 题 · ${points} 分</span>
        <span class="chip-row">${Object.entries(counts).map(([k, v]) => `<span class="chip">${escapeHtml(k)} ${v}</span>`).join("")}</span>`;
      button.addEventListener("click", () => {
        saveEditor();
        sectionIndex = index;
        blockIndex = questions[0]?.index || 0;
        renderAll();
      });
      target.appendChild(button);
    });
  }

  function renderQuestions() {
    const section = currentSection(student);
    $("section-title").textContent = section.title || section.id || "题目";
    $("section-meta").textContent = `${section.type || ""} · ${section.visibility || ""}`;
    const target = $("question-table");
    target.innerHTML = "";
    questionBlocks(section).forEach(({ block, index }, displayIndex) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = `question-row ${index === blockIndex ? "is-selected" : ""}`;
      button.innerHTML = `
        <strong>${displayIndex + 1}</strong>
        <span>${escapeHtml(block.type || "")}</span>
        <span class="question-stem">${escapeHtml(stemSummary(block))}</span>
        <span>${Number(block.points || 0)} 分</span>`;
      button.addEventListener("click", () => {
        saveEditor();
        blockIndex = index;
        renderQuestions();
        renderEditor();
      });
      target.appendChild(button);
    });
  }

  function renderEditor() {
    const sBlock = currentStudentBlock();
    const tBlock = currentTeacherBlock();
    $("editor-title").textContent = sBlock ? `${sBlock.id || ""} ${sBlock.type || ""}` : "题目编辑";
    $("editor-meta").textContent = sBlock ? `${sectionIndex + 1}.${blockIndex + 1}` : "";
    const target = $("editor");
    target.innerHTML = `
      <div class="editor-column">
        <h3>学生版</h3>
        ${sBlock ? questionEditor("student", sBlock, false) : "<p class='muted'>未选择题目</p>"}
      </div>
      <div class="editor-column">
        <h3>教师版</h3>
        ${tBlock ? questionEditor("teacher", tBlock, true) : "<p class='muted'>没有教师版或未找到对应题目。</p>"}
      </div>`;
  }

  function questionEditor(prefix, block, isTeacher) {
    const parts = [
      field(prefix, "id", "ID", block.id || ""),
      field(prefix, "points", "分值", block.points || ""),
      area(prefix, "stem_latex", "题干 LaTeX", block.stem_latex || block.stem || "", 10),
      area(prefix, "choices", "选项 JSON", JSON.stringify(block.choices || {}, null, 2), 6, true),
      area(prefix, "hints", "提示 JSON", JSON.stringify(block.hints || [], null, 2), 6, true),
      area(prefix, "answer_space", "答题区 JSON", JSON.stringify(block.answer_space || {}, null, 2), 6, true),
    ];
    if (isTeacher) {
      parts.push(
        area(prefix, "answer", "答案", block.answer || "", 3),
        area(prefix, "explanation", "解析", block.explanation || "", 5),
        area(prefix, "solution_steps", "解题步骤 JSON", JSON.stringify(block.solution_steps || [], null, 2), 10, true),
        area(prefix, "teaching", "教师备注 JSON", JSON.stringify(block.teaching || {}, null, 2), 8, true)
      );
    }
    return parts.join("");
  }

  function saveEditor() {
    saveQuestion("student", currentStudentBlock());
    saveQuestion("teacher", currentTeacherBlock());
  }

  function saveQuestion(prefix, block) {
    if (!block) return;
    const node = (name) => document.querySelector(`[data-prefix="${prefix}"][data-field="${name}"]`);
    ["id", "stem_latex", "answer", "explanation"].forEach((key) => {
      const el = node(key);
      if (el) block[key] = el.value;
    });
    const points = node("points");
    if (points) block.points = Number(points.value || 0);
    ["choices", "hints", "answer_space", "solution_steps", "teaching"].forEach((key) => {
      const el = node(key);
      if (el) block[key] = parseJson(el.value, block[key] || (key === "choices" || key === "answer_space" || key === "teaching" ? {} : []));
    });
  }

  function syncTeacherStem() {
    saveEditor();
    const sBlock = currentStudentBlock();
    const tBlock = currentTeacherBlock();
    if (!sBlock || !tBlock) return;
    ["id", "type", "points", "stem", "stem_latex", "choices", "hints", "answer_space", "diagram_col", "prompt_diagram"].forEach((key) => {
      if (sBlock[key] !== undefined) tBlock[key] = structuredClone(sBlock[key]);
    });
    renderAll();
  }

  function rebuildAnswerKey() {
    saveEditor();
    if (!teacher) return show({ ok: false, error: "teacher yaml is not loaded" });
    const answers = [];
    sections(teacher).forEach((section) => {
      questionBlocks(section).forEach(({ block }) => {
        if (block.answer) answers.push({ number: String(answers.length + 1), answer: block.answer });
      });
    });
    let answerSection = sections(teacher).find((section) => section.type === "answer_key");
    if (!answerSection) {
      answerSection = { id: "answer-key", title: "答案速查", type: "answer_key", visibility: "teacher", blocks: [] };
      teacher.sections.push(answerSection);
    }
    let answerBlock = (answerSection.blocks || []).find((block) => block.type === "answers");
    if (!answerBlock) {
      answerBlock = { type: "answers", id: "answers-main", items: [] };
      answerSection.blocks = answerSection.blocks || [];
      answerSection.blocks.push(answerBlock);
    }
    answerBlock.items = answers;
    show({ status: "answer_key_rebuilt", count: answers.length });
  }

  async function saveReviewed() {
    saveEditor();
    show(await post("/api/save", { student, teacher }));
  }

  async function validateYaml() {
    saveEditor();
    show(await post("/api/validate", { student, teacher }));
  }

  async function renderLatex() {
    saveEditor();
    const result = await post("/api/render", { student, teacher });
    const first = result.results?.student || result.results?.teacher;
    lastTexPath = first?.out || "";
    $("compile-pdf").disabled = !lastTexPath || !first?.ok;
    show(result);
  }

  async function compilePdf() {
    if (!lastTexPath) return;
    show(await post("/api/compile", { tex_path: lastTexPath }));
  }

  async function saveAgentRequest() {
    const instruction = $("agent-instruction").value.trim();
    if (!instruction) return show({ ok: false, error: "instruction is required" });
    show(await post("/api/agent-request", { instruction, selection: { sectionIndex, blockIndex, blockId: currentStudentBlock()?.id || "" } }));
  }

  function field(prefix, name, label, value) {
    return `<label class="field">${label}<input data-prefix="${prefix}" data-field="${name}" value="${escapeAttr(value)}"></label>`;
  }

  function area(prefix, name, label, value, rows, mono = false) {
    return `<label class="field">${label}<textarea data-prefix="${prefix}" data-field="${name}" rows="${rows}" class="${mono ? "mono" : ""}">${escapeHtml(value)}</textarea></label>`;
  }

  function stemSummary(block) {
    return (block.stem_latex || block.stem || "").replace(/\s+/g, " ").slice(0, 120);
  }

  function countTypes(blocks) {
    return blocks.reduce((acc, block) => {
      acc[block.type || "unknown"] = (acc[block.type || "unknown"] || 0) + 1;
      return acc;
    }, {});
  }

  function parseJson(text, fallback) {
    try {
      return JSON.parse(text || "null") ?? fallback;
    } catch {
      return fallback;
    }
  }

  async function post(url, payload) {
    const response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const json = await response.json();
    if (!response.ok) return { ok: false, status: response.status, detail: json.detail || json };
    return json;
  }

  function show(value) {
    $("result-output").textContent = JSON.stringify(value, null, 2);
  }

  function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>"']/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]));
  }

  function escapeAttr(value) {
    return escapeHtml(value).replace(/\n/g, " ");
  }

  init();
})();
