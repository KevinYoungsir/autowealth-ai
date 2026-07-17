import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import ts from "typescript";


const frontendRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const source = await readFile(
  path.join(frontendRoot, "lib", "research-report-loader.ts"),
  "utf8"
);
const transpiled = ts.transpileModule(source, {
  compilerOptions: {
    module: ts.ModuleKind.ES2022,
    target: ts.ScriptTarget.ES2022
  }
}).outputText;
const moduleUrl = `data:text/javascript;base64,${Buffer.from(transpiled).toString("base64")}`;
const { loadResearchReportForSource } = await import(moduleUrl);


test("real artifacts load the selected run report without mock requests", async () => {
  const calls = [];
  const realReport = {
    run_id: "real_run",
    data_source: "real_artifacts",
    generated_mode: "deterministic"
  };

  const result = await loadResearchReportForSource(
    "real_artifacts",
    "real_run",
    {
      fetchRealReport: async (runId) => {
        calls.push(`real:${runId}`);
        return realReport;
      },
      fetchDemo: async () => {
        calls.push("demo");
        throw new Error("demo must not be called");
      },
      fetchMockReport: async () => {
        calls.push("mock");
        throw new Error("mock report must not be called");
      }
    }
  );

  assert.deepEqual(calls, ["real:real_run"]);
  assert.equal(result.dataSource, "real_artifacts");
  assert.equal(result.report, realReport);
  assert.equal(result.demo, null);
});


test("mock demo remains available when there is no real run", async () => {
  const calls = [];
  const demo = { result: { experiment_name: "demo" } };
  const mockReport = { metadata: { mock_mode: true } };

  const result = await loadResearchReportForSource(
    "mock_demo",
    null,
    {
      fetchRealReport: async () => {
        calls.push("real");
        throw new Error("real report must not be called");
      },
      fetchDemo: async () => {
        calls.push("demo");
        return demo;
      },
      fetchMockReport: async (researchResult) => {
        calls.push(`mock:${researchResult.experiment_name}`);
        return mockReport;
      }
    }
  );

  assert.deepEqual(calls, ["demo", "mock:demo"]);
  assert.equal(result.dataSource, "mock_demo");
  assert.equal(result.report, mockReport);
  assert.equal(result.demo, demo);
});


test("real source without a selected run never falls back to mock", async () => {
  const calls = [];

  await assert.rejects(
    loadResearchReportForSource("real_artifacts", null, {
      fetchRealReport: async () => {
        calls.push("real");
      },
      fetchDemo: async () => {
        calls.push("demo");
      },
      fetchMockReport: async () => {
        calls.push("mock");
      }
    }),
    /selected run_id/
  );

  assert.deepEqual(calls, []);
});
