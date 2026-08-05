const state = { library: "numbers", payload: null, search: "", family: "", status: "" };
const byId = (id) => document.getElementById(id);
const configs = {
  numbers: { title: "数库审核", endpoint: "/api/database", unit: "组", filter: "数值族" },
  trig: { title: "三角比库审核", endpoint: "/api/trig-ratios", unit: "组", filter: "来源" },
  triangles: { title: "三角形库审核", endpoint: "/api/triangles", unit: "个", filter: "三角形类型" },
};

function showToast(message) {
  const toast = byId("toast");
  toast.textContent = message;
  toast.hidden = false;
  clearTimeout(showToast.timer);
  showToast.timer = setTimeout(() => { toast.hidden = true; }, 1600);
}

function allEntries() {
  if (state.library === "numbers") return state.payload.families.flatMap((family) => family.entries.map((entry) => ({ ...entry, family_id: family.id, family_title: family.title })));
  return state.payload.entries || [];
}

function classification(entry) {
  if (state.library === "numbers") return [entry.family_id, entry.family_title];
  if (state.library === "trig") return ["derived", "由数库构造的锐角三角比"];
  const kinds = (entry.angles || []).map((angle) => angle.kind);
  const kind = kinds.includes("obtuse") ? "obtuse" : (kinds.includes("right") ? "right" : "acute");
  return [kind, { acute: "锐角三角形", right: "直角三角形", obtuse: "钝角三角形" }[kind]];
}

function searchable(entry) {
  if (state.library === "numbers") return [entry.id, entry.label, entry.relation, ...(entry.tags || []), ...(entry.latex_values || []), ...(entry.presentation_latex || [])].join(" ").toLowerCase();
  if (state.library === "trig") return [entry.id, ...Object.values(entry.ratios || {}).flatMap((value) => [value.latex, value.display]), ...(entry.source_number_entry_ids || [])].join(" ").toLowerCase();
  return [entry.id, ...Object.values(entry.sides || {}).flatMap((value) => [value.latex, value.display]), ...(entry.source_trig_ratio_ids || []), ...(entry.angles || []).flatMap((angle) => [angle.name, angle.kind, ...Object.values(angle.reference || {}).map((value) => value.display)])].join(" ").toLowerCase();
}

function visible(entry) {
  if (state.search && !searchable(entry).includes(state.search)) return false;
  if (state.status === "enabled" && entry.disabled) return false;
  if (state.status === "disabled" && !entry.disabled) return false;
  return !state.family || classification(entry)[0] === state.family;
}

function content(entry) {
  if (state.library === "numbers") {
    const values = entry.presentation_latex?.length ? entry.presentation_latex : entry.latex_values;
    return { main: `(${values.join(", ")})`, detail: entry.ratio_reduction ? `→ ${entry.ratio_reduction.normalized_latex.join(" : ")} → ${entry.ratio_reduction.reduced_integer_pair.join(" : ")}` : entry.relation, tags: (entry.tags || []).slice(0, 3).join(" · ") };
  }
  if (state.library === "trig") {
    const ratios = entry.ratios || {};
    return { main: `sin ${ratios.sin.latex}　cos ${ratios.cos.latex}`, detail: `tan ${ratios.tan.latex}　cot ${ratios.cot.latex}`, tags: `来源：${(entry.source_number_entry_ids || []).join("、")}` };
  }
  const sides = entry.sides || {};
  const angleText = (entry.angles || []).map((angle) => `${angle.name}:${angle.kind} cos=${angle.reference?.cos?.latex || "?"}`).join("　");
  return { main: `a=${sides.a?.latex}　b=${sides.b?.latex}　c=${sides.c?.latex}`, detail: angleText, tags: `来源三角比：${(entry.source_trig_ratio_ids || []).join("、")}` };
}

async function updateEntry(entry, button) {
  if (button.dataset.saving === "true") return;
  const base = { numbers: "/api/entries", trig: "/api/trig-ratios", triangles: "/api/triangles" }[state.library];
  button.dataset.saving = "true";
  try {
    const response = await fetch(`${base}/${encodeURIComponent(entry.id)}`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ disabled: !entry.disabled }) });
    if (!response.ok) throw new Error(await response.text());
    const result = await response.json();
    entry.disabled = result.disabled;
    state.payload.disabled_count = result.disabled_count;
    byId("disabled-count").textContent = result.disabled_count;
    showToast(entry.disabled ? "已禁用；下次重建下游库时生效" : "已恢复可用");
    render();
  } catch (error) { showToast(`保存失败：${error.message}`); }
  finally { delete button.dataset.saving; }
}

function makeButton(entry) {
  const data = content(entry);
  const button = document.createElement("button");
  button.type = "button";
  button.className = `number-button${entry.disabled ? " is-disabled" : ""}`;
  button.setAttribute("aria-pressed", String(entry.disabled));
  button.title = entry.id;
  const main = document.createElement("span"); main.className = "number-label"; main.textContent = data.main;
  const detail = document.createElement("span"); detail.className = "number-reduction"; detail.textContent = data.detail;
  const status = document.createElement("span"); status.className = "number-state"; status.textContent = "已禁用"; status.hidden = !entry.disabled;
  const tags = document.createElement("span"); tags.className = "number-tags"; tags.textContent = data.tags;
  button.append(main, detail, status, tags);
  button.addEventListener("click", () => updateEntry(entry, button));
  return button;
}

function render() {
  const root = byId("families"); root.replaceChildren();
  const groups = new Map();
  allEntries().filter(visible).forEach((entry) => {
    const [id, title] = classification(entry);
    if (!groups.has(id)) groups.set(id, { title, entries: [] });
    groups.get(id).entries.push(entry);
  });
  let count = 0;
  groups.forEach((group) => {
    count += group.entries.length;
    const card = document.createElement("article"); card.className = "family-card";
    const header = document.createElement("header"); header.className = "family-header";
    const heading = document.createElement("h2"); heading.textContent = group.title;
    const tally = document.createElement("span"); tally.className = "family-count"; tally.textContent = `${group.entries.length} 项 · ${group.entries.filter((entry) => entry.disabled).length} 禁用`;
    header.append(heading, tally);
    const grid = document.createElement("div"); grid.className = state.library === "triangles" ? "number-grid triangle-grid" : "number-grid";
    group.entries.forEach((entry) => grid.append(makeButton(entry)));
    card.append(header, grid); root.append(card);
  });
  byId("visible-count").textContent = `当前显示 ${count} ${configs[state.library].unit}`;
  if (!count) root.innerHTML = '<p class="empty">没有符合当前筛选条件的条目。</p>';
}

function fillFilter() {
  const select = byId("family-filter"); select.replaceChildren(new Option("全部", ""));
  const values = new Map(allEntries().map((entry) => classification(entry)));
  values.forEach((title, id) => select.append(new Option(title, id)));
}

async function loadLibrary(library) {
  state.library = library; state.family = ""; state.search = "";
  byId("search").value = ""; byId("family-filter-label").textContent = configs[library].filter;
  byId("page-title").textContent = configs[library].title;
  document.querySelectorAll("[data-library]").forEach((button) => button.setAttribute("aria-current", button.dataset.library === library ? "page" : "false"));
  const response = await fetch(configs[library].endpoint); if (!response.ok) throw new Error(await response.text());
  state.payload = await response.json();
  byId("total-count").textContent = state.payload.total_count; byId("disabled-count").textContent = state.payload.disabled_count;
  fillFilter(); render();
}

byId("search").addEventListener("input", (event) => { state.search = event.target.value.trim().toLowerCase(); render(); });
byId("family-filter").addEventListener("change", (event) => { state.family = event.target.value; render(); });
byId("status-filter").addEventListener("change", (event) => { state.status = event.target.value; render(); });
document.querySelectorAll("[data-library]").forEach((button) => button.addEventListener("click", () => loadLibrary(button.dataset.library).catch((error) => showToast(error.message))));
loadLibrary("numbers").catch((error) => { byId("families").innerHTML = `<p class="empty">加载失败：${error.message}</p>`; });
