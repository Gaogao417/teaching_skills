const DIFFICULTIES = { novice: 20000, intermediate: 12000, expert: 7000 };
const ROUND_LENGTH = 10;

const state = {
  difficulty: "novice",
  duration: DIFFICULTIES.novice,
  subcategories: [],
  questionIndex: 0,
  score: 0,
  streak: 0,
  correctCount: 0,
  responseTimes: [],
  mistakes: [],
  recentEntryIds: [],
  question: null,
  selected: [],
  startedAt: 0,
  timer: null,
  locked: false,
  roundSaved: false,
  savePromise: null,
  savedRecordId: null,
  historyMetric: "accuracy",
  historyRecords: [],
  historyReturnScreen: null,
};

const $ = (selector) => document.querySelector(selector);
const screens = [$("#setup-screen"), $("#play-screen"), $("#result-screen"), $("#history-screen")];

function showScreen(screen) {
  screens.forEach((candidate) => { candidate.hidden = candidate !== screen; });
  $("#settings-button").hidden = screen !== $("#play-screen");
  $("#history-button").hidden = screen === $("#history-screen");
}

function fractionMarkup(value) {
  const [numerator, denominator] = value.split("/");
  if (!denominator) return `<span class="whole-number">${numerator}</span>`;
  return `<span class="fraction"><i>${numerator}</i><i>${denominator}</i></span>`;
}

function selectedSubcategories() {
  return [...document.querySelectorAll('input[name="subcategory"]:checked')].map((input) => input.value);
}

async function requestQuestion() {
  const response = await fetch("/api/game/question", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      subcategories: state.subcategories,
      exclude_entry_ids: state.recentEntryIds.slice(-8),
    }),
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.detail || "题目加载失败");
  }
  return response.json();
}

function clearTimer() {
  if (state.timer) window.clearInterval(state.timer);
  state.timer = null;
}

function updateTimer() {
  const elapsed = performance.now() - state.startedAt;
  const remaining = Math.max(0, state.duration - elapsed);
  const ratio = remaining / state.duration;
  $("#timer-bar").style.transform = `scaleX(${ratio})`;
  $("#timer-bar").style.background = ratio < 0.3 ? "var(--coral)" : "var(--teal)";
  $("#time-left").textContent = (remaining / 1000).toFixed(1);
  if (remaining <= 0) judge(false, true);
}

function renderQuestion() {
  state.selected = [];
  state.locked = false;
  $("#question-number").textContent = state.questionIndex + 1;
  $("#score").textContent = state.score;
  $("#streak").textContent = state.streak;
  $("#target-multiplier").innerHTML = fractionMarkup(state.question.multiplier);
  $("#feedback").textContent = "请选择一对分数";
  $("#feedback").className = "feedback";
  const options = $("#options");
  options.replaceChildren();
  state.question.options.forEach((option, index) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "option-button";
    button.dataset.index = index;
    button.setAttribute("aria-pressed", "false");
    button.setAttribute("aria-label", `${option.values[0]} 和 ${option.values[1]}`);
    button.innerHTML = `<span class="pair-values">${fractionMarkup(option.values[0])}<span class="pair-divider">与</span>${fractionMarkup(option.values[1])}</span>`;
    button.addEventListener("click", () => selectOption(index, button));
    options.append(button);
  });
  state.startedAt = performance.now();
  clearTimer();
  state.timer = window.setInterval(updateTimer, 30);
  updateTimer();
}

function selectOption(index, button) {
  if (state.locked) return;
  state.selected = [index];
  button.classList.add("is-selected");
  button.setAttribute("aria-pressed", "true");
  judge(index === state.question.correct_index, false);
}

function judge(correct, timedOut) {
  if (state.locked) return;
  state.locked = true;
  clearTimer();
  const elapsed = Math.min(state.duration, Math.max(0, performance.now() - state.startedAt));
  const remaining = state.duration - elapsed;
  state.responseTimes.push(Math.round(elapsed));
  if (!correct) {
    state.mistakes.push({
      question_number: state.questionIndex + 1,
      entry_id: state.question.entry_id,
      subcategory: state.question.subcategory,
      multiplier: state.question.multiplier,
      options: state.question.options.map((option) => option.values),
      correct_index: state.question.correct_index,
      selected_index: timedOut ? null : (state.selected[0] ?? null),
      timed_out: timedOut,
      response_ms: Math.round(elapsed),
    });
  }
  const buttons = [...document.querySelectorAll(".option-button")];
  buttons.forEach((button, index) => {
    button.disabled = true;
    button.classList.remove("is-selected");
    if (index === state.question.correct_index) button.classList.add("is-correct");
    else if (state.selected.includes(index)) button.classList.add("is-wrong");
  });

  if (correct) {
    state.correctCount += 1;
    state.streak += 1;
    const speedBonus = Math.round((remaining / state.duration) * 50);
    const streakBonus = Math.min(state.streak - 1, 5) * 10;
    const earned = 100 + speedBonus + streakBonus;
    state.score += earned;
    $("#feedback").textContent = state.streak >= 3 ? `答对了！+${earned} 分 · 连续 ${state.streak} 题 🔥` : `答对了！+${earned} 分`;
    $("#feedback").className = "feedback correct";
  } else {
    state.streak = 0;
    $("#feedback").textContent = timedOut ? "时间到！绿色是正确的一对" : "再看一眼，绿色是正确的一对";
    $("#feedback").className = "feedback wrong";
  }
  $("#score").textContent = state.score;
  $("#streak").textContent = state.streak;
  window.setTimeout(nextQuestion, 760);
}

async function nextQuestion() {
  state.questionIndex += 1;
  if (state.questionIndex >= ROUND_LENGTH) {
    finishRound();
    return;
  }
  try {
    state.question = await requestQuestion();
    state.recentEntryIds.push(state.question.entry_id);
    renderQuestion();
  } catch (error) {
    $("#feedback").textContent = error.message;
    $("#feedback").className = "feedback wrong";
  }
}

async function startRound() {
  state.questionIndex = 0;
  state.score = 0;
  state.streak = 0;
  state.correctCount = 0;
  state.responseTimes = [];
  state.mistakes = [];
  state.recentEntryIds = [];
  state.roundSaved = false;
  state.savePromise = null;
  state.savedRecordId = null;
  showScreen($("#play-screen"));
  try {
    state.question = await requestQuestion();
    state.recentEntryIds.push(state.question.entry_id);
    renderQuestion();
  } catch (error) {
    showScreen($("#setup-screen"));
    $("#setup-error").textContent = error.message;
    $("#setup-error").hidden = false;
  }
}

function finishRound() {
  clearTimer();
  const accuracy = Math.round((state.correctCount / ROUND_LENGTH) * 100);
  const averageResponseMs = Math.round(state.responseTimes.reduce((total, value) => total + value, 0) / ROUND_LENGTH);
  $("#final-score").textContent = state.score;
  $("#correct-count").textContent = `${state.correctCount} / ${ROUND_LENGTH}`;
  $("#accuracy").textContent = `${accuracy}%`;
  $("#average-time").textContent = `${(averageResponseMs / 1000).toFixed(1)} 秒`;
  $("#result-mistakes-button").hidden = state.mistakes.length === 0;
  $("#result-mistakes-button").textContent = `查看本轮错题（${state.mistakes.length}）`;
  $("#result-title").textContent = accuracy >= 90 ? "倍数达人！" : accuracy >= 60 ? "反应很快！" : "再来一轮就更稳了";
  $("#result-medal").textContent = accuracy >= 90 ? "★" : accuracy >= 60 ? "✓" : "↗";
  showScreen($("#result-screen"));
  state.savePromise = saveRound();
}

async function saveRound() {
  if (state.roundSaved) return;
  state.roundSaved = true;
  try {
    const response = await fetch("/api/game/history", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        difficulty: state.difficulty,
        duration_ms: state.duration,
        subcategories: state.subcategories,
        score: state.score,
        correct_count: state.correctCount,
        total_questions: ROUND_LENGTH,
        average_response_ms: Math.round(state.responseTimes.reduce((total, value) => total + value, 0) / ROUND_LENGTH),
        mistakes: state.mistakes,
      }),
    });
    if (!response.ok) throw new Error("训练记录保存失败");
    const savedRecord = await response.json();
    state.savedRecordId = savedRecord.id;
    return savedRecord;
  } catch (error) {
    state.roundSaved = false;
    console.error(error);
  }
}

const DIFFICULTY_LABELS = { novice: "新手", intermediate: "进阶", expert: "高手" };
const SUBCATEGORY_SHORT_LABELS = {
  numerator_multiple_only: "只有分子",
  denominator_multiple_only: "只有分母",
  numerator_and_denominator_multiple: "分子分母同时",
};

function svgElement(name, attributes = {}, text = "") {
  const element = document.createElementNS("http://www.w3.org/2000/svg", name);
  Object.entries(attributes).forEach(([key, value]) => element.setAttribute(key, value));
  if (text) element.textContent = text;
  return element;
}

function renderChart() {
  const metric = state.historyMetric;
  const records = state.historyRecords
    .slice(0, 20)
    .reverse()
    .filter((record) => record[metric] !== null && record[metric] !== undefined);
  const values = records.map((record) => record[metric]);
  const maxValue = metric === "accuracy"
    ? 100
    : metric === "average_response_seconds"
      ? Math.max(5, Math.ceil(Math.max(...values, 0) / 5) * 5)
      : Math.max(100, Math.ceil(Math.max(...values, 0) / 100) * 100);
  const metricSuffix = metric === "accuracy" ? "%" : metric === "average_response_seconds" ? " 秒" : "";
  const left = 52;
  const right = 696;
  const top = 26;
  const bottom = 224;
  const width = right - left;
  const height = bottom - top;
  const xFor = (index) => records.length === 1 ? left + width / 2 : left + (index / (records.length - 1)) * width;
  const yFor = (value) => bottom - (value / maxValue) * height;

  const grid = $("#chart-grid");
  const pointsGroup = $("#chart-points");
  const labelsGroup = $("#chart-labels");
  grid.replaceChildren();
  pointsGroup.replaceChildren();
  labelsGroup.replaceChildren();

  if (!records.length) {
    $("#chart-line").setAttribute("points", "");
    $("#chart-area").setAttribute("points", "");
    labelsGroup.append(svgElement("text", { x: 374, y: 135, class: "chart-axis-label", "text-anchor": "middle" }, "旧记录暂无平均用时数据"));
    return;
  }

  [0, 0.5, 1].forEach((ratio) => {
    const y = bottom - ratio * height;
    grid.append(svgElement("line", { x1: left, y1: y, x2: right, y2: y, class: "chart-grid-line" }));
    const axisValue = metric === "average_response_seconds" ? Number((maxValue * ratio).toFixed(1)) : Math.round(maxValue * ratio);
    labelsGroup.append(svgElement("text", { x: left - 10, y: y + 4, class: "chart-axis-label", "text-anchor": "end" }, `${axisValue}${metricSuffix}`));
  });

  const pointText = records.map((record, index) => `${xFor(index)},${yFor(record[metric])}`).join(" ");
  $("#chart-line").setAttribute("points", pointText);
  $("#chart-area").setAttribute("points", pointText ? `${xFor(0)},${bottom} ${pointText} ${xFor(records.length - 1)},${bottom}` : "");
  records.forEach((record, index) => {
    const x = xFor(index);
    const y = yFor(record[metric]);
    pointsGroup.append(svgElement("circle", { cx: x, cy: y, r: index === records.length - 1 ? 7 : 5, class: `chart-dot${index === records.length - 1 ? " latest" : ""}` }));
    if (records.length <= 10 || index === records.length - 1) {
      labelsGroup.append(svgElement("text", { x, y: Math.max(14, y - 12), class: "chart-value" }, `${record[metric]}${metricSuffix}`));
    }
  });
}

function renderHistory(payload) {
  state.historyRecords = payload.records;
  $("#history-rounds").textContent = payload.summary.rounds;
  $("#history-best-accuracy").textContent = `${payload.summary.best_accuracy}%`;
  $("#history-fastest-time").textContent = payload.summary.fastest_average_response_seconds === null ? "—" : `${payload.summary.fastest_average_response_seconds} 秒`;
  $("#history-best-score").textContent = payload.summary.best_score;
  const hasRecords = payload.records.length > 0;
  $("#mistake-review").hidden = true;
  $("#history-empty").hidden = hasRecords;
  $("#history-content").hidden = !hasRecords;
  if (!hasRecords) return;

  const tableBody = $("#history-table-body");
  tableBody.replaceChildren();
  payload.records.slice(0, 10).forEach((record) => {
    const row = document.createElement("tr");
    const date = new Date(record.completed_at).toLocaleString("zh-CN", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" });
    const content = record.subcategories.map((key) => SUBCATEGORY_SHORT_LABELS[key]).join("、");
    const averageTime = record.average_response_seconds === null ? "—" : `${record.average_response_seconds} 秒`;
    row.innerHTML = `<td>${date}</td><td><span class="difficulty-pill">${DIFFICULTY_LABELS[record.difficulty]}</span></td><td class="content-cell">${content}</td><td><strong>${record.accuracy}%</strong></td><td><strong>${averageTime}</strong></td><td class="mistake-cell"></td><td><strong>${record.score}</strong></td>`;
    const mistakeCell = row.querySelector(".mistake-cell");
    if (!record.mistakes_recorded) {
      mistakeCell.innerHTML = '<span class="mistake-record-status">未记录</span>';
    } else if (record.mistake_count === 0) {
      mistakeCell.innerHTML = '<span class="mistake-record-status">0 题</span>';
    } else {
      const mistakeButton = document.createElement("button");
      mistakeButton.type = "button";
      mistakeButton.className = "mistake-link";
      mistakeButton.textContent = `查看 ${record.mistake_count} 题`;
      mistakeButton.addEventListener("click", () => showMistakes(record));
      mistakeCell.append(mistakeButton);
    }
    tableBody.append(row);
  });
  renderChart();
}

function showMistakes(record) {
  const panel = $("#mistake-review");
  const list = $("#mistake-review-list");
  const date = new Date(record.completed_at).toLocaleString("zh-CN", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" });
  $("#mistake-review-meta").textContent = `${date} · ${DIFFICULTY_LABELS[record.difficulty]} · ${record.mistake_count} 道错题`;
  list.replaceChildren();

  if (!record.mistakes_recorded) {
    const empty = document.createElement("p");
    empty.className = "mistake-empty";
    empty.textContent = "这轮训练完成于错题记录功能启用之前，无法还原当时的具体题目。";
    list.append(empty);
  } else if (!record.mistakes.length) {
    const empty = document.createElement("p");
    empty.className = "mistake-empty";
    empty.textContent = "这一轮没有错题。";
    list.append(empty);
  } else {
    record.mistakes.forEach((mistake) => {
      const card = document.createElement("article");
      card.className = "mistake-card";
      const status = mistake.timed_out ? "超时" : "答错";
      card.innerHTML = `<div class="mistake-card-header"><div><h4>第 ${mistake.question_number} 题 · <strong class="mistake-target">× ${mistake.multiplier}</strong></h4><span>${SUBCATEGORY_SHORT_LABELS[mistake.subcategory]}</span></div><span>${status} · ${(mistake.response_ms / 1000).toFixed(1)} 秒</span></div>`;
      const options = document.createElement("div");
      options.className = "mistake-options";
      mistake.options.forEach((pair, index) => {
        const option = document.createElement("div");
        option.className = "mistake-option";
        option.innerHTML = `${fractionMarkup(pair[0])}<span class="pair-divider">与</span>${fractionMarkup(pair[1])}`;
        if (index === mistake.correct_index) {
          option.classList.add("is-correct");
          option.insertAdjacentHTML("beforeend", '<span class="mistake-option-badge">正确答案</span>');
        } else if (index === mistake.selected_index) {
          option.classList.add("is-selected-wrong");
          option.insertAdjacentHTML("beforeend", '<span class="mistake-option-badge">你的选择</span>');
        }
        options.append(option);
      });
      card.append(options);
      list.append(card);
    });
  }
  panel.hidden = false;
  panel.scrollIntoView({ behavior: "smooth", block: "start" });
}

async function openHistory(returnScreen = null) {
  clearTimer();
  state.historyReturnScreen = returnScreen || ($("#result-screen").hidden ? $("#setup-screen") : $("#result-screen"));
  showScreen($("#history-screen"));
  try {
    if (state.savePromise) await state.savePromise;
    const response = await fetch("/api/game/history?limit=50");
    if (!response.ok) throw new Error("训练记录加载失败");
    const payload = await response.json();
    renderHistory(payload);
    return payload;
  } catch (error) {
    $("#history-empty").hidden = false;
    $("#history-content").hidden = true;
    $("#history-empty").innerHTML = `<strong>记录暂时无法加载</strong><p>${error.message}</p>`;
    return null;
  }
}

function returnToSettings() {
  clearTimer();
  showScreen($("#setup-screen"));
}

$("#setup-form").addEventListener("submit", (event) => {
  event.preventDefault();
  state.subcategories = selectedSubcategories();
  if (!state.subcategories.length) {
    $("#setup-error").textContent = "请至少选择一种练习内容。";
    $("#setup-error").hidden = false;
    return;
  }
  $("#setup-error").hidden = true;
  state.difficulty = new FormData(event.currentTarget).get("difficulty");
  state.duration = DIFFICULTIES[state.difficulty];
  startRound();
});

$("#settings-button").addEventListener("click", returnToSettings);
$("#back-settings-button").addEventListener("click", returnToSettings);
$("#replay-button").addEventListener("click", startRound);
$("#history-button").addEventListener("click", () => openHistory());
$("#result-history-button").addEventListener("click", () => openHistory($("#result-screen")));
$("#result-mistakes-button").addEventListener("click", async () => {
  const payload = await openHistory($("#result-screen"));
  if (!payload) return;
  const record = payload.records.find((candidate) => candidate.id === state.savedRecordId) || payload.records[0];
  if (record) showMistakes(record);
});
$("#history-back-button").addEventListener("click", () => showScreen(state.historyReturnScreen || $("#setup-screen")));
$("#close-mistakes-button").addEventListener("click", () => { $("#mistake-review").hidden = true; });
document.querySelectorAll("[data-metric]").forEach((button) => {
  button.addEventListener("click", () => {
    state.historyMetric = button.dataset.metric;
    document.querySelectorAll("[data-metric]").forEach((candidate) => candidate.classList.toggle("is-active", candidate === button));
    renderChart();
  });
});
