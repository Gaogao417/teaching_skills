/**
 * Layer B — 浏览器交互 E2E：题库审核 UI 的筛选 + 检索。
 *
 * 用 puppeteer 驱动真实浏览器，点真控件 → 断真 DOM 变化（而非断 JSON）。
 * 服务端起真实 uvicorn（绑定 free port）加载真实 artifacts/题库。
 *
 * 前置：``npx puppeteer browsers install chrome``（仓库 package.json 已声明 puppeteer 依赖）。
 *
 * 运行：``node tests/e2e/test_question_bank_filters_ui.mjs``
 *
 * 覆盖的 golden path（详见各 test_* 函数注释）：
 *   B1  页面渲染所有新控件（filter-kind/grade/year/exam-type/search-input/bank-select 下拉框）
 *   B2  facets 填充 grade/year 下拉（真实数据）
 *   B3  选 kind=真题 → 列表只剩 staging
 *   B4  选 exam_type=二模 → 列表只剩 ERMO
 *   B5  选 year=2025 → 排除 GEN-TERM
 *   B6  搜索框输入 → debounce 后只发 1 次请求 + 列表收窄
 *   B7  组合 kind=真题 + q=杨浦
 *   B8  无匹配 → 空状态不崩 + 无 JS 报错
 *   B9  过滤后选题 → 详情加载（选中链路没断）
 *   B10 清除过滤 → 列表恢复全量
 *   B11 深链 ?bank= 启动即选中正确 bank
 *   B12 占位 token 被替换干净（浏览器侧验证）
 */

import { spawn } from "node:child_process";
import net from "node:net";
import os from "node:os";
import fs from "node:fs";
import path from "node:path";
import assert from "node:assert/strict";
import puppeteer from "puppeteer";

const REPO_ROOT = new URL("../../", import.meta.url).pathname;
const PYTHON = `${REPO_ROOT}.venv/bin/python`;
const SERVER_MODULE_DIR = `${REPO_ROOT}.codex/skills/math-topic-question-bank/scripts`;
const BANK_ROOT = `${REPO_ROOT}artifacts/题库`;

// ---- 端口 / 服务端管理 ----

function freePort() {
  return new Promise((resolve, reject) => {
    const srv = net.createServer();
    srv.unref();
    srv.on("error", reject);
    srv.listen({ host: "127.0.0.1", port: 0 }, () => {
      const { port } = srv.address();
      srv.close(() => resolve(port));
    });
  });
}

async function waitForHealthy(baseUrl, timeoutMs = 30000) {
  // 给 Python 3.14 + uvicorn 在 macOS 上足够的冷启动时间（首次启动有时 >8s）。
  // 注意 baseUrl 以 "/" 结尾，拼接 healthz 时不要产生 "//healthz"（某些 uvicorn 版本会 404）。
  const healthUrl = `${baseUrl.replace(/\/$/, "")}/healthz`;
  const deadline = Date.now() + timeoutMs;
  let lastErr = "";
  while (Date.now() < deadline) {
    try {
      const r = await fetch(healthUrl);
      if (r.ok) return;
      lastErr = `status=${r.status}`;
    } catch (e) {
      lastErr = e.message;
      // 还没起来，继续等。
    }
    await new Promise((r) => setTimeout(r, 200));
  }
  throw new Error(`server at ${baseUrl} did not become healthy in ${timeoutMs}ms (last: ${lastErr})`);
}

async function startServer(port) {
  if (process.env.E2E_DEBUG) {
    console.error("[debug] REPO_ROOT=", REPO_ROOT);
    console.error("[debug] PYTHON=", PYTHON, "exists=", fs.existsSync(PYTHON));
    console.error("[debug] BANK_ROOT=", BANK_ROOT);
  }
  // 把 boot script 写到临时 .py 文件而不是用 ``python -c``，避免多行/非 ASCII
  // 在 ``-c`` argv 下被宿主 shell 或 Python 源码编码处理出问题。
  const bootScript = `# -*- coding: utf-8 -*-
import sys, uvicorn
sys.path.insert(0, ${JSON.stringify(SERVER_MODULE_DIR)})
from question_bank_review_server import create_question_bank_app, DEFAULT_NUMBER_REVIEW_URL
from pathlib import Path
app = create_question_bank_app(Path(${JSON.stringify(BANK_ROOT)}), DEFAULT_NUMBER_REVIEW_URL)
uvicorn.run(app, host="127.0.0.1", port=${port}, log_level="warning")
`;
  const bootFile = path.join(os.tmpdir(), `qbank-e2e-boot-${port}-${process.pid}.py`);
  fs.writeFileSync(bootFile, bootScript, { encoding: "utf-8" });
  // Python 的 stdout/stderr 重定向到日志文件：避免 Node pipe 在某些环境下静默吞掉输出。
  const logFile = path.join(os.tmpdir(), `qbank-e2e-log-${port}-${process.pid}.log`);
  const logFd = fs.openSync(logFile, "w");
  const proc = spawn(PYTHON, [bootFile], {
    stdio: ["ignore", logFd, logFd],
  });
  if (process.env.E2E_DEBUG) {
    console.error("[debug] bootFile=", bootFile, "logFile=", logFile);
  }
  const cleanup = () => {
    try { fs.unlinkSync(bootFile); } catch {}
    try { fs.closeSync(logFd); } catch {}
    try { fs.unlinkSync(logFile); } catch {}
  };
  proc.on("exit", (code, sig) => {
    if (process.env.E2E_DEBUG) console.error("[debug] python exit code=", code, "sig=", sig);
  });
  proc.on("error", (e) => {
    if (process.env.E2E_DEBUG) console.error("[debug] spawn error:", e.message);
  });
  const baseUrl = `http://127.0.0.1:${port}/`;
  const readLog = () => { try { return fs.readFileSync(logFile, "utf-8"); } catch { return ""; } };
  try {
    await waitForHealthy(baseUrl);
  } catch (e) {
    proc.kill("SIGKILL");
    const log = readLog();
    cleanup();
    throw new Error(`${e.message}\npython log:\n${log}`);
  }
  return { proc, baseUrl, cleanup };
}

// ---- puppeteer helpers ----

async function newPage(browser) {
  const page = await browser.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  page.on("console", (msg) => {
    if (msg.type() === "error") errors.push(`console.error: ${msg.text()}`);
  });
  page.errors = errors;
  // 只收集未捕获 JS 异常（pageerror）；console.error 可能含与本次改动无关的
  // 历史 404 图片资源，单独用 helper 过滤。
  page.jsErrors = () => errors.filter((e) => !e.startsWith("console.error"));
  page.consoleErrors = () => errors.filter((e) => e.startsWith("console.error"));
  return page;
}

async function waitForBankSelectReady(page) {
  // 等列表进入稳定态：不再 disabled，且 page-status 要么隐藏、要么不在加载过渡文案。
  // applyFilters 期间 status="正在筛选题库…"（可见）；selectBank 期间 status="正在读取题库…"（可见）。
  // selectBank 成功后会 hidden=true，所以检查可见性即可区分过渡态与终态。
  await page.waitForFunction(
    () => {
      const sel = document.getElementById("bank-select");
      if (!sel || sel.disabled || sel.options.length === 0) return false;
      const status = document.getElementById("page-status");
      if (!status || status.hidden) return true;
      const text = status.textContent.trim();
      return !text.includes("正在筛选") && !text.includes("正在读取");
    },
    { timeout: 8000 },
  );
}

async function optionTexts(page, selectId) {
  return page.evaluate((id) => {
    const sel = document.getElementById(id);
    return Array.from(sel.options).map((o) => o.textContent.trim());
  }, selectId);
}

async function optionCount(page, selectId) {
  return page.evaluate((id) => document.getElementById(id).options.length, selectId);
}

async function selectValue(page, selectId, value) {
  // 用真实 change 事件触发（不是直接赋值），保证 JS 监听器跑起来。
  await page.evaluate(
    ({ id, val }) => {
      const sel = document.getElementById(id);
      sel.value = val;
      sel.dispatchEvent(new Event("change", { bubbles: true }));
    },
    { id: selectId, val: value },
  );
}

// ---- 测试主体 ----

const tests = [];

function test(name, fn) {
  tests.push({ name, fn });
}

// B1
test("page renders all new filter controls and dropdown bank-select", async ({ page }) => {
  for (const id of [
    "filter-kind",
    "filter-grade",
    "filter-year",
    "filter-exam-type",
    "search-input",
    "bank-select",
  ]) {
    const el = await page.$(`#${id}`);
    assert.ok(el, `缺少 #${id}`);
    assert.ok(await el.isIntersectingViewport(), `#${id} 不可见`);
  }
  const size = await page.$eval("#bank-select", (s) => s.getAttribute("size"));
  assert.ok(!size, `bank-select 应是单行下拉框（无 size 属性），实际 size=${size}`);
});

// B2
test("facets populate grade and year dropdowns with real data", async ({ page }) => {
  const grades = await optionTexts(page, "filter-grade");
  const years = await optionTexts(page, "filter-year");
  assert.ok(grades.includes("九年级"), `filter-grade 应含真实年级，实际 ${JSON.stringify(grades)}`);
  assert.ok(years.includes("2025"), `filter-year 应含真实年份，实际 ${JSON.stringify(years)}`);
  // exam_type 是 HTML 写死的 5 种枚举。
  const examTypes = await optionTexts(page, "filter-exam-type");
  for (const t of ["一模", "二模", "期中", "期末", "中考"]) {
    assert.ok(examTypes.includes(t), `filter-exam-type 应含 ${t}（前瞻留位），实际 ${JSON.stringify(examTypes)}`);
  }
});

// B3
test("selecting kind=真题 narrows list to staging only", async ({ page, baseline }) => {
  await selectValue(page, "filter-kind", "staging_exam");
  await waitForBankSelectReady(page);
  const count = await optionCount(page, "bank-select");
  assert.ok(count < baseline.totalBanks, `筛选后 option 数 ${count} 应小于全量 ${baseline.totalBanks}`);
  // 所有 option 文本应以"试卷"开头（renderBankList 对 staging 用"试卷"前缀）。
  const texts = await optionTexts(page, "bank-select");
  assert.ok(
    texts.every((t) => t.startsWith("试卷")),
    `筛选后应全是 staging，实际 ${JSON.stringify(texts.slice(0, 3))}`,
  );
});

// B4
test("selecting exam_type=二模 keeps only ERMO papers", async ({ page, freshPage }) => {
  await freshPage();
  await selectValue(page, "filter-exam-type", "二模");
  await waitForBankSelectReady(page);
  const texts = await optionTexts(page, "bank-select");
  assert.ok(texts.length > 0, "二模应至少有 1 份");
  // ERMO 卷的 topic 多含"二模"或区名；关键是不能混入"一模"字样。
  assert.ok(
    texts.every((t) => !t.includes("一模") || t.includes("二模")),
    `二模筛选结果不应混入纯一模，实际 ${JSON.stringify(texts.slice(0, 3))}`,
  );
});

// B5
test("selecting year=2025 excludes yearless GEN-TERM", async ({ page, freshPage }) => {
  await freshPage();
  await selectValue(page, "filter-year", "2025");
  await waitForBankSelectReady(page);
  const texts = await optionTexts(page, "bank-select");
  // GEN-TERM 的 topic 是"初三数学期末练习卷"且无 year；不应出现在 2025 结果里。
  assert.ok(texts.length > 0, "2025 应至少命中 1 份");
  // GEN-TERM 无 year，必须被排除；它 topic 含"期末练习卷"且 option 尾部无年份。
  // 同时验证所有结果都带 2025 年份标记（renderBankList 把 year 拼进 option 文本）。
  assert.ok(
    texts.every((t) => t.includes("2025·")),
    `2025 筛选结果应都带 2025 年份，实际 ${JSON.stringify(texts.slice(0, 3))}`,
  );
});

// B6
test("typing in search narrows list with debounce (single request)", async ({ page, freshPage, baseline }) => {
  await freshPage();
  const qRequests = [];
  page.on("request", (req) => {
    const u = req.url();
    if (u.includes("/api/banks?") && u.includes("q=")) qRequests.push(u);
  });
  await page.focus("#search-input");
  await page.type("#search-input", "静安", { delay: 40 });
  // debounce=200ms；等列表收窄到全量以下（说明 q=静安 的 refetch 已落地）。
  await page.waitForFunction(
    (prev) => {
      const sel = document.getElementById("bank-select");
      return !sel.disabled && sel.options.length < prev;
    },
    { timeout: 8000 },
    baseline.totalBanks,
  );
  const count = await optionCount(page, "bank-select");
  assert.ok(count < baseline.totalBanks, `检索后应收窄，实际 ${count} vs 全量 ${baseline.totalBanks}`);
  // 核心断言：debounce 让多次按键只产生 1 次 /api/banks?q= 请求。
  assert.equal(qRequests.length, 1, `debounce 应合并为 1 次请求，实际 ${qRequests.length}：${JSON.stringify(qRequests)}`);
});

// B7
test("combined kind=真题 + q=杨浦 narrows to yangpu real exams only", async ({ page, freshPage }) => {
  await freshPage();
  await selectValue(page, "filter-kind", "staging_exam");
  await waitForBankSelectReady(page);
  const afterKind = await optionCount(page, "bank-select");
  await page.focus("#search-input");
  await page.type("#search-input", "杨浦", { delay: 30 });
  // 等列表收窄到比"仅 kind=真题"更少（说明 q=杨浦 的 refetch 已落地）。
  await page.waitForFunction(
    (prev) => {
      const sel = document.getElementById("bank-select");
      return !sel.disabled && sel.options.length < prev
        && Array.from(sel.options).every((o) => o.textContent.includes("杨浦"));
    },
    { timeout: 8000 },
    afterKind,
  );
  const texts = await optionTexts(page, "bank-select");
  assert.ok(texts.length > 0, "应至少命中 1 份杨浦真题");
  assert.ok(
    texts.every((t) => t.includes("杨浦")),
    `组合筛选结果应全是杨浦真题，实际 ${JSON.stringify(texts.slice(0, 3))}`,
  );
});

// B8
test("no-match filter shows empty state without JS errors", async ({ page, freshPage }) => {
  await freshPage();
  // freshPage 触发的 applyFilters 可能与随后的逐键 input debounce 竞态；直接设值 +
  // 派发一次 input（绕开逐键 debounce 的并发窗口），更稳定地复现"无匹配"路径。
  await page.evaluate(() => {
    const search = document.getElementById("search-input");
    search.value = "zzzznomatchxyz";
    search.dispatchEvent(new Event("input", { bubbles: true }));
  });
  // 等空状态文案出现（debounce 200ms + refetch）。
  await page.waitForFunction(
    () => /没有匹配/.test(document.getElementById("page-status").textContent),
    { timeout: 8000 },
  );
  const status = await page.$eval("#page-status", (el) => el.textContent.trim());
  assert.match(status, /没有匹配/, `空状态文案错误，实际 "${status}"`);
  // review-layout 应隐藏。
  const layoutHidden = await page.$eval("#review-layout", (el) => el.hidden);
  assert.ok(layoutHidden, "无匹配时 review-layout 应隐藏");
  // 只断未捕获 JS 异常；console.error 里的 404 多为历史 staging 图片缺失，与本次改动无关。
  assert.equal(page.jsErrors().length, 0, `不应有未捕获 JS 异常，实际 ${JSON.stringify(page.jsErrors())}`);
});

// B9
test("selecting a bank after filter loads its detail", async ({ page, freshPage }) => {
  await freshPage();
  await selectValue(page, "filter-exam-type", "二模");
  await waitForBankSelectReady(page);
  // 点列表第一个 bank option。
  const firstValue = await page.$eval("#bank-select", (s) => s.options[0].value);
  await page.select("#bank-select", firstValue);
  // 等 detail API 返回 + review-layout 显示。
  await page.waitForFunction(
    () => !document.getElementById("review-layout").hidden,
    { timeout: 8000 },
  );
  const topic = await page.$eval("#topic-summary", (el) => el.textContent.trim());
  assert.ok(topic.length > 0, `选中后 topic-summary 应有内容，实际 "${topic}"`);
  assert.equal(page.jsErrors().length, 0, `选题不应产生未捕获 JS 异常，实际 ${JSON.stringify(page.jsErrors())}`);
});

// B10
test("clearing filter restores full list", async ({ page, freshPage, baseline }) => {
  await freshPage();
  await selectValue(page, "filter-year", "2025");
  await waitForBankSelectReady(page);
  const narrowed = await optionCount(page, "bank-select");
  assert.ok(narrowed < baseline.totalBanks, "先确认确实收窄了");
  await selectValue(page, "filter-year", "");
  await waitForBankSelectReady(page);
  const restored = await optionCount(page, "bank-select");
  assert.equal(restored, baseline.totalBanks, `清除过滤后应恢复全量 ${baseline.totalBanks}，实际 ${restored}`);
});

// B11
test("deep-link ?bank= loads the correct bank on startup", async ({ browser, baseUrl }) => {
  const deepBankId = "staging:2026-07-24-上海初三试卷原题库:2025-JINGAN-YIMO";
  const page = await newPage(browser);
  await page.goto(`${baseUrl}?bank=${encodeURIComponent(deepBankId)}`, { waitUntil: "networkidle0" });
  await waitForBankSelectReady(page);
  await page.waitForFunction(
    () => !document.getElementById("review-layout").hidden,
    { timeout: 8000 },
  );
  const topic = await page.$eval("#topic-summary", (el) => el.textContent.trim());
  assert.ok(topic.includes("静安"), `深链应选中静安卷，topic 实际 "${topic}"`);
  const selected = await page.$eval("#bank-select", (s) => s.value);
  assert.equal(selected, deepBankId, `深链应设置 bank-select.value，实际 "${selected}"`);
});

// B12
test("static version / number review url placeholders fully substituted", async ({ page }) => {
  const html = await page.content();
  assert.ok(!html.includes("__STATIC_VERSION__"), "运行时 HTML 不应残留 __STATIC_VERSION__");
  assert.ok(!html.includes("__NUMBER_REVIEW_URL__"), "运行时 HTML 不应残留 __NUMBER_REVIEW_URL__");
});

// ---- runner ----

async function main() {
  const port = await freePort();
  const { proc, baseUrl, cleanup } = await startServer(port);
  const browser = await puppeteer.launch({ headless: "new" });

  const page = await newPage(browser);
  await page.goto(baseUrl, { waitUntil: "networkidle0" });
  await waitForBankSelectReady(page);
  const totalBanks = await optionCount(page, "bank-select");
  const baseline = { totalBanks };

  const freshPage = async () => {
    // 真正的隔离：重新加载页面到一个干净 URL，避免上一个测试遗留的并发
    // applyFilters / selectBank 把状态带进来（共享 page 时这是 flakiness 的主因）。
    await page.goto(baseUrl, { waitUntil: "networkidle0" });
    await waitForBankSelectReady(page);
  };

  let failed = 0;
  for (const { name, fn } of tests) {
    try {
      await fn({ page, browser, baseUrl, baseline, freshPage });
      console.log(`  ok  ${name}`);
    } catch (e) {
      failed += 1;
      console.error(`  FAIL ${name}`);
      console.error(`       ${e.message.split("\n")[0]}`);
    }
  }

  await browser.close();
  proc.kill("SIGTERM");
  await new Promise((r) => proc.once("exit", r).once("error", r));
  cleanup();

  const total = tests.length;
  console.log(`\n${total - failed}/${total} passed`);
  process.exit(failed === 0 ? 0 : 1);
}

main().catch((e) => {
  console.error("fatal:", e);
  process.exit(1);
});
