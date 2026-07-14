const state = {
  payload: null,
  search: "",
  family: "",
  status: "",
};

const byId = (id) => document.getElementById(id);

function searchable(entry) {
  return [entry.id, entry.label, entry.relation, entry.subcategory_title || "", ...entry.tags, ...entry.latex_values]
    .join(" ")
    .toLowerCase();
}

function entryVisible(entry) {
  if (state.search && !searchable(entry).includes(state.search)) return false;
  if (state.status === "enabled" && entry.disabled) return false;
  if (state.status === "disabled" && !entry.disabled) return false;
  return true;
}

function makeButton(entry) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = `number-button${entry.disabled ? " is-disabled" : ""}`;
  button.dataset.entryId = entry.id;
  button.dataset.testid = `number-${entry.id}`;
  button.setAttribute("aria-pressed", String(entry.disabled));
  button.title = `${entry.latex_values.join(", ")}\n${entry.relation}\n${entry.id}`;

  const label = document.createElement("span");
  label.className = "number-label";
  label.textContent = entry.label;
  const tags = document.createElement("span");
  tags.className = "number-tags";
  tags.textContent = entry.tags.slice(0, 3).join(" · ");
  const status = document.createElement("span");
  status.className = "number-state";
  status.setAttribute("aria-hidden", "true");
  status.textContent = "已禁用";
  status.hidden = !entry.disabled;
  button.append(label, status, tags);
  button.addEventListener("click", () => updateEntry(entry, button));
  return button;
}

function render() {
  const root = byId("families");
  root.replaceChildren();
  let visible = 0;
  for (const family of state.payload.families) {
    if (state.family && family.id !== state.family) continue;
    const entries = family.entries.filter(entryVisible);
    if (!entries.length) continue;
    visible += entries.length;

    const card = document.createElement("article");
    card.className = "family-card";
    card.dataset.familyId = family.id;
    const header = document.createElement("header");
    header.className = "family-header";
    header.innerHTML = `<div><h2>${family.title}</h2><p>${family.description}</p></div>`;
    const count = document.createElement("span");
    count.className = "family-count";
    const disabled = entries.filter((entry) => entry.disabled).length;
    count.textContent = `${entries.length} 组 · ${disabled} 禁用`;
    header.append(count);
    card.append(header);
    if (family.id === "rational_multiple_pairs") {
      const subcategoryOrder = [
        "numerator_multiple_only",
        "denominator_multiple_only",
        "numerator_and_denominator_multiple",
        "not_integer_multiple",
      ];
      for (const subcategory of subcategoryOrder) {
        const subgroupEntries = entries.filter((entry) => entry.subcategory === subcategory);
        if (!subgroupEntries.length) continue;
        const subgroup = document.createElement("section");
        subgroup.className = "number-subcategory";
        subgroup.dataset.subcategory = subcategory;
        const subgroupHeader = document.createElement("div");
        subgroupHeader.className = "subcategory-header";
        const subgroupTitle = document.createElement("h3");
        subgroupTitle.textContent = subgroupEntries[0].subcategory_title;
        const subgroupCount = document.createElement("span");
        subgroupCount.className = "subcategory-count";
        subgroupCount.textContent = `${subgroupEntries.length} 组 · ${subgroupEntries.filter((entry) => entry.disabled).length} 禁用`;
        subgroupHeader.append(subgroupTitle, subgroupCount);
        const grid = document.createElement("div");
        grid.className = "number-grid";
        subgroupEntries.forEach((entry) => grid.append(makeButton(entry)));
        subgroup.append(subgroupHeader, grid);
        card.append(subgroup);
      }
    } else {
      const grid = document.createElement("div");
      grid.className = "number-grid";
      entries.forEach((entry) => grid.append(makeButton(entry)));
      card.append(grid);
    }
    root.append(card);
  }
  byId("visible-count").textContent = `当前显示 ${visible} 组`;
  if (!visible) {
    const empty = document.createElement("p");
    empty.className = "empty";
    empty.textContent = "没有符合当前筛选条件的数值组。";
    root.append(empty);
  }
}

function updateFamilyCount(entry) {
  const family = state.payload.families.find((candidate) =>
    candidate.entries.some((candidateEntry) => candidateEntry.id === entry.id));
  if (!family) return;
  const card = [...document.querySelectorAll(".family-card")]
    .find((candidate) => candidate.dataset.familyId === family.id);
  if (!card) return;
  const visibleEntries = family.entries.filter(entryVisible);
  const disabled = visibleEntries.filter((candidate) => candidate.disabled).length;
  card.querySelector(".family-count").textContent = `${visibleEntries.length} 组 · ${disabled} 禁用`;
  if (entry.subcategory) {
    const subgroup = [...card.querySelectorAll(".number-subcategory")]
      .find((candidate) => candidate.dataset.subcategory === entry.subcategory);
    if (subgroup) {
      const subgroupEntries = visibleEntries.filter((candidate) => candidate.subcategory === entry.subcategory);
      const subgroupDisabled = subgroupEntries.filter((candidate) => candidate.disabled).length;
      subgroup.querySelector(".subcategory-count").textContent = `${subgroupEntries.length} 组 · ${subgroupDisabled} 禁用`;
    }
  }
}

function showToast(message) {
  const toast = byId("toast");
  toast.textContent = message;
  toast.hidden = false;
  clearTimeout(showToast.timer);
  showToast.timer = setTimeout(() => { toast.hidden = true; }, 1600);
}

async function updateEntry(entry, button) {
  if (button.dataset.saving === "true") return;
  const nextDisabled = !entry.disabled;
  button.dataset.saving = "true";
  button.setAttribute("aria-busy", "true");
  try {
    const response = await fetch(`/api/entries/${encodeURIComponent(entry.id)}`, {
      method: "PUT",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({disabled: nextDisabled}),
    });
    if (!response.ok) throw new Error(await response.text());
    const result = await response.json();
    entry.disabled = result.disabled;
    state.payload.disabled_count = result.disabled_count;
    byId("disabled-count").textContent = result.disabled_count;
    button.classList.toggle("is-disabled", entry.disabled);
    button.setAttribute("aria-pressed", String(entry.disabled));
    button.querySelector(".number-state").hidden = !entry.disabled;
    showToast(entry.disabled ? "已禁用这组数" : "已恢复这组数");
    if (state.status) render();
    else updateFamilyCount(entry);
  } catch (error) {
    showToast(`保存失败：${error.message}`);
  } finally {
    delete button.dataset.saving;
    button.removeAttribute("aria-busy");
  }
}

async function load() {
  const response = await fetch("/api/database");
  if (!response.ok) throw new Error(await response.text());
  state.payload = await response.json();
  byId("total-count").textContent = state.payload.total_count;
  byId("disabled-count").textContent = state.payload.disabled_count;

  const select = byId("family-filter");
  state.payload.families.forEach((family) => {
    const option = document.createElement("option");
    option.value = family.id;
    option.textContent = `${family.title}（${family.count}）`;
    select.append(option);
  });
  render();
}

byId("search").addEventListener("input", (event) => {
  state.search = event.target.value.trim().toLowerCase();
  render();
});
byId("family-filter").addEventListener("change", (event) => {
  state.family = event.target.value;
  render();
});
byId("status-filter").addEventListener("change", (event) => {
  state.status = event.target.value;
  render();
});

load().catch((error) => {
  byId("families").innerHTML = `<p class="empty">加载失败：${error.message}</p>`;
});
