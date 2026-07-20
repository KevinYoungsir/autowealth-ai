import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import ts from "typescript";


const frontendRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

async function sourceAt(...parts) {
  return readFile(path.join(frontendRoot, ...parts), "utf8");
}

async function importTypeScript(source) {
  const transpiled = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.ES2022,
      target: ts.ScriptTarget.ES2022
    }
  }).outputText;
  const url = `data:text/javascript;base64,${Buffer.from(transpiled).toString("base64")}`;
  return import(url);
}

const messagesModule = await importTypeScript(
  await sourceAt("i18n", "messages", "zh-CN.ts")
);
const machineLabelsModule = await importTypeScript(
  await sourceAt("i18n", "machine-labels.ts")
);
const warningGroupsModule = await importTypeScript(
  await sourceAt("lib", "warning-presentations.ts")
);

const { zhCNMessages: ui } = messagesModule;
const { machineLabel } = machineLabelsModule;
const { groupWarningPresentations } = warningGroupsModule;


test("zh-CN navigation, report sections and state labels are centralized", () => {
  assert.deepEqual(Object.values(ui.navigation), [
    "研究总览",
    "回测分析",
    "组合持仓",
    "因子分析",
    "宏观环境",
    "研究报告",
    "系统状态"
  ]);
  assert.equal(ui.report.sections.executiveSummary, "执行摘要");
  assert.equal(ui.report.sections.performanceReview, "历史表现复核");
  assert.equal(ui.report.sections.dataQualityReview, "数据质量复核");
  assert.equal(ui.report.sections.researchBoundaries, "研究边界");
  assert.equal(machineLabel("dataSource", "real_artifacts"), "真实研究数据");
  assert.equal(machineLabel("dataSource", "mock_demo"), "演示数据");
  assert.equal(machineLabel("dataSource", "api_unavailable"), "API 暂不可用");
  assert.equal(machineLabel("runStatus", "partial_success"), "部分完成");
  assert.equal(machineLabel("availability", "unavailable"), "暂不可用");
  assert.equal(machineLabel("generatedMode", "deterministic"), "确定性生成");
});


test("real report requests explicitly send locale=zh-CN", async () => {
  const apiSource = (await sourceAt("lib", "api.ts")).replace(
    'import { ui, type AppLocale } from "@/i18n";',
    'const ui = { errors: { apiRequestFailed: (status) => `API ${status}` } };'
  );
  const { fetchResearchReport } = await importTypeScript(apiSource);
  const calls = [];
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (url, init) => {
    calls.push({ url, init });
    return { ok: true, status: 200, json: async () => ({}) };
  };
  try {
    await fetchResearchReport("run_001");
    await fetchResearchReport("run_002", "en-US");
  } finally {
    globalThis.fetch = originalFetch;
  }
  assert.match(String(calls[0].url), /report\?locale=zh-CN$/);
  assert.match(String(calls[1].url), /report\?locale=en-US$/);
});


test("mock, loading, error and empty presentation text is Chinese", async () => {
  assert.equal(ui.pages.researchNotes.mockTitle, "演示研究报告");
  assert.match(ui.pages.researchNotes.mockDisclosure, /演示复核/);
  assert.equal(ui.common.syncing, "正在同步");
  assert.equal(ui.errors.apiUnavailable, "研究 API 不可用。");
  assert.equal(ui.pages.researchNotes.waitingReal, "真实研究复核报告尚未返回。");
  const provider = await sourceAt("components", "research-data-provider.tsx");
  const presenter = await sourceAt("i18n", "mock-report-presenter.ts");
  assert.match(provider, /localizeMockReport/);
  assert.match(presenter, /ui\.mock\.summary/);
  assert.match(presenter, /\.\.\.flag/);
});


test("warning overview limits first-view samples and retains all raw items", () => {
  const warnings = Array.from({ length: 193 }, (_, index) => ({
    source_message: `provider warning ${index}`,
    display_message: "行情数据源存在技术提示，请复核。",
    category: "price_provider",
    category_label: "行情数据源"
  }));
  const groups = groupWarningPresentations(warnings, 3);
  assert.equal(groups.length, 1);
  assert.equal(groups[0].count, 193);
  assert.equal(groups[0].samples.length, 3);
  assert.equal(groups[0].items.length, 193);
});


test("report UI keeps machine values and collapses original warnings", async () => {
  const source = await sourceAt("components", "real-research-report.tsx");
  assert.match(source, /font-mono/);
  assert.match(source, /technicalSubtitle/);
  assert.match(source, /<details/);
  assert.match(source, /group\.samples\.map/);
  assert.match(source, /group\.items\.map/);
  assert.doesNotMatch(source, /完整 Warning 记录/);
});


test("HTML and fonts are mainland-network-safe and Chinese-readable", async () => {
  const layout = await sourceAt("app", "layout.tsx");
  const css = await sourceAt("app", "globals.css");
  const tailwind = await sourceAt("tailwind.config.ts");
  const packageJson = await sourceAt("package.json");
  const combined = `${layout}\n${css}\n${tailwind}\n${packageJson}`;
  assert.match(layout, /<html lang="zh-CN">/);
  assert.match(css, /PingFang SC/);
  assert.match(css, /Microsoft YaHei UI/);
  assert.match(css, /Noto Sans CJK SC/);
  assert.match(css, /line-height: 1\.7/);
  assert.match(css, /overflow-wrap: anywhere/);
  assert.match(tailwind, /Source Han Sans SC/);
  assert.match(tailwind, /JetBrains Mono/);
  assert.doesNotMatch(combined, /next\/font|fonts\.googleapis|@font-face/);
});


test("app shell consumes localized navigation rather than English labels", async () => {
  const shell = await sourceAt("components", "app-shell.tsx");
  assert.match(shell, /ui\.navigation\.dashboard/);
  assert.match(shell, /ui\.navigation\.researchNotes/);
  assert.match(shell, /ui\.common\.refresh/);
  assert.doesNotMatch(shell, /label: "Dashboard"|label: "Research Notes"/);
});
