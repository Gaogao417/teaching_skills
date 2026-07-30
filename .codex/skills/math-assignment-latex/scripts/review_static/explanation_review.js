(function () {
  const ORDER = ["solution", "problemcard", "route", "dual_explanation", "explanation_dual", "mistake", "method_reminder"];
  let state = null;
  let data = null;
  let sectionIndex = 0;
  let blockIndex = 0;
  let lastTexPath = "";

  const $ = (id) => document.getElementById(id);

  async function init() {
    const response = await fetch("/api/state");
    state = await response.json();
    data = state.data;
    $("doc-title").textContent = data.meta?.title || "讲义审核";
    $("doc-path").textContent = state.source_path;
    bindButtons();
    renderAll();
  }

  function bindButtons() {
    $("save-reviewed").addEventListener("click", saveReviewed);
    $("validate-yaml").addEventListener("click", validateYaml);
    $("render-latex").addEventListener("click", renderLatex);
    $("compile-pdf").addEventListener("click", compilePdf);
    $("save-agent-request").addEventListener("click", saveAgentRequest);
  }

  function renderAll() {
    renderSections();
    renderFlow();
    renderEditor();
  }

  function sections() {
    return data.sections || [];
  }

  function currentSection() {
    return sections()[sectionIndex] || { blocks: [] };
  }

  function sortedBlocks(section) {
    return (section.blocks || []).map((block, index) => ({ block, index })).sort((a, b) => {
      const ao = ORDER.indexOf(a.block.type);
      const bo = ORDER.indexOf(b.block.type);
      return (ao === -1 ? 99 : ao) - (bo === -1 ? 99 : bo) || a.index - b.index;
    });
  }

  function currentBlock() {
    return (currentSection().blocks || [])[blockIndex] || null;
  }

  function renderSections() {
    const target = $("section-list");
    target.innerHTML = "";
    sections().forEach((section, index) => {
      const counts = countTypes(section.blocks || []);
      const button = document.createElement("button");
      button.className = `section-card ${index === sectionIndex ? "is-selected" : ""}`;
      button.type = "button";
      button.innerHTML = `
        <span class="card-title">${escapeHtml(section.title || section.id || `Section ${index + 1}`)}</span>
        <span class="muted">${escapeHtml(section.id || "")}</span>
        <span class="chip-row">
          <span class="chip">${(section.blocks || []).length} blocks</span>
          <span class="chip">${counts.problemcard || 0} 例题</span>
          <span class="chip">${counts.route || 0} route</span>
          <span class="chip">${(counts.dual_explanation || 0) + (counts.explanation_dual || 0)} dual</span>
        </span>`;
      button.addEventListener("click", () => {
        saveEditor();
        sectionIndex = index;
        blockIndex = 0;
        renderAll();
      });
      target.appendChild(button);
    });
  }

  function renderFlow() {
    const section = currentSection();
    $("section-title").textContent = section.title || section.id || "教学流";
    $("section-meta").textContent = `${section.type || ""} · ${section.visibility || ""}`;
    const target = $("block-flow");
    target.innerHTML = "";
    sortedBlocks(section).forEach(({ block, index }) => {
      const button = document.createElement("button");
      button.className = `block-card ${index === blockIndex ? "is-selected" : ""}`;
      button.type = "button";
      button.innerHTML = `
        <span class="flow-type">${escapeHtml(block.type || "unknown")}</span>
        <span class="card-title">${escapeHtml(block.title || block.label || block.id || `Block ${index + 1}`)}</span>
        <span class="muted">${escapeHtml(summary(block))}</span>`;
      button.addEventListener("click", () => {
        saveEditor();
        blockIndex = index;
        renderFlow();
        renderEditor();
      });
      target.appendChild(button);
    });
  }

  function renderEditor() {
    const block = currentBlock();
    $("editor-title").textContent = block ? (block.title || block.label || block.id || "块编辑") : "块编辑";
    $("editor-meta").textContent = block ? `${block.type || ""} · ${block.id || ""}` : "";
    const target = $("editor");
    if (!block) {
      target.innerHTML = "<p class=\"muted\">当前 section 没有 block。</p>";
      return;
    }
    if (block.type === "solution") renderSolution(target, block);
    else if (block.type === "problemcard") renderProblemcard(target, block);
    else if (block.type === "route") renderRoute(target, block);
    else if (block.type === "dual_explanation" || block.type === "explanation_dual") renderDual(target, block);
    else if (block.type === "mistake") renderMistake(target, block);
    else if (block.type === "method_reminder" || block.type === "reminder") renderReminder(target, block);
    else renderRawBlock(target, block);
  }

  function renderSolution(target, block) {
    target.innerHTML = field("title", "标题", block.title || "") + area("items", "核心条目 JSON", JSON.stringify(block.items || [], null, 2), 14, true);
  }

  function renderProblemcard(target, block) {
    target.innerHTML = field("label", "例题标签", block.label || "") + area("stem_latex", "题干 LaTeX", block.stem_latex || block.stem || "", 14);
  }

  function renderRoute(target, block) {
    target.innerHTML = area("steps", "步骤 JSON", JSON.stringify(block.steps || [], null, 2), 20, true);
  }

  function renderDual(target, block) {
    target.innerHTML = [
      field("label", "标签", block.label || ""),
      area("stem_latex", "解决的问题", block.stem_latex || block.stem || "", 4),
      area("side_items", "左栏提示/易错 JSON", JSON.stringify(block.side_items || [], null, 2), 12, true),
      area("solution_step_ids", "引用 route step id JSON", JSON.stringify(block.solution_step_ids || [], null, 2), 7, true),
      area("connection_items", "承接/验算 JSON", JSON.stringify(block.connection_items || [], null, 2), 7, true),
    ].join("");
  }

  function renderMistake(target, block) {
    target.innerHTML = field("title", "标题", block.title || "") + area("content_latex", "内容 LaTeX", block.content_latex || block.content || "", 12);
  }

  function renderReminder(target, block) {
    target.innerHTML = field("title", "标题", block.title || "") + area("items", "条目 JSON", JSON.stringify(block.items || [], null, 2), 12, true);
  }

  function renderRawBlock(target, block) {
    target.innerHTML = area("raw_block", "当前 block JSON", JSON.stringify(block, null, 2), 22, true);
  }

  function saveEditor() {
    const block = currentBlock();
    if (!block || !$("editor")) return;
    const get = (name) => document.querySelector(`[data-field="${name}"]`);
    if (get("raw_block")) {
      replaceCurrentBlock(parseJson(get("raw_block").value, block));
      return;
    }
    ["title", "label", "stem_latex", "content_latex"].forEach((key) => {
      const node = get(key);
      if (node) block[key] = node.value;
    });
    ["items", "steps", "side_items", "solution_step_ids", "connection_items"].forEach((key) => {
      const node = get(key);
      if (node) block[key] = parseJson(node.value, block[key] || []);
    });
  }

  function replaceCurrentBlock(nextBlock) {
    currentSection().blocks[blockIndex] = nextBlock;
  }

  async function saveReviewed() {
    saveEditor();
    show(await post("/api/save", { data }));
  }

  async function validateYaml() {
    saveEditor();
    show(await post("/api/validate", { data }));
  }

  async function renderLatex() {
    saveEditor();
    const result = await post("/api/render", { data });
    if (result.out) lastTexPath = result.out;
    $("compile-pdf").disabled = !lastTexPath || !result.ok;
    show(result);
  }

  async function compilePdf() {
    if (!lastTexPath) return;
    show(await post("/api/compile", { tex_path: lastTexPath }));
  }

  async function saveAgentRequest() {
    const instruction = $("agent-instruction").value.trim();
    if (!instruction) return show({ ok: false, error: "instruction is required" });
    show(await post("/api/agent-request", { instruction, selection: { sectionIndex, blockIndex, blockId: currentBlock()?.id || "" } }));
  }

  function field(name, label, value) {
    return `<label class="field">${label}<input data-field="${name}" value="${escapeAttr(value)}"></label>`;
  }

  function area(name, label, value, rows, mono = false) {
    return `<label class="field">${label}<textarea data-field="${name}" rows="${rows}" class="${mono ? "mono" : ""}">${escapeHtml(value)}</textarea></label>`;
  }

  function countTypes(blocks) {
    return blocks.reduce((acc, block) => {
      acc[block.type || "unknown"] = (acc[block.type || "unknown"] || 0) + 1;
      return acc;
    }, {});
  }

  function summary(block) {
    if (block.type === "route") return `${(block.steps || []).length} steps`;
    if (block.type === "dual_explanation" || block.type === "explanation_dual") return `${(block.side_items || []).length} side items`;
    if (block.type === "solution" || block.type === "method_reminder") return `${(block.items || []).length} items`;
    return (block.stem_latex || block.content_latex || "").replace(/\s+/g, " ").slice(0, 90);
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
