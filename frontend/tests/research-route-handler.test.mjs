import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import ts from "typescript";


const frontendRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const routeSource = await readFile(
  path.join(
    frontendRoot,
    "app",
    "api",
    "research",
    "runs",
    "[[...path]]",
    "route.ts"
  ),
  "utf8"
);
const instrumentedSource = routeSource.replace(
  'import { proxyResearchJson } from "@/lib/server-api";',
  `
const proxyCalls = [];
function proxyResearchJson(path, init) {
  proxyCalls.push({ path, init });
  return { path, init };
}
export { proxyCalls };
`
);
const transpiled = ts.transpileModule(instrumentedSource, {
  compilerOptions: {
    module: ts.ModuleKind.ES2022,
    target: ts.ScriptTarget.ES2022
  }
}).outputText;
const moduleUrl = `data:text/javascript;base64,${Buffer.from(transpiled).toString("base64")}`;
const { GET, proxyCalls } = await import(moduleUrl);


test("route handler declares and awaits asynchronous params", () => {
  assert.match(routeSource, /params:\s*Promise<\{/);
  assert.match(routeSource, /const \{ path = \[\] \} = await context\.params;/);
  assert.doesNotMatch(routeSource, /context\.params\.path/);
});


test("catch-all segments keep order, encoding and query parameters", async () => {
  const originalFetch = globalThis.fetch;
  const fetchCalls = [];
  globalThis.fetch = async (...args) => {
    fetchCalls.push(args);
    throw new Error("network access is not expected");
  };

  try {
    const result = await GET(
      new Request(
        "http://127.0.0.1:3000/api/research/runs/run?locale=zh-CN&raw=a%2Fb&tag=x+y"
      ),
      {
        params: Promise.resolve({
          path: ["run/001", "空 格", "report?full"]
        })
      }
    );

    assert.equal(
      result.path,
      "/research/runs/run%2F001/%E7%A9%BA%20%E6%A0%BC/report%3Ffull?locale=zh-CN&raw=a%2Fb&tag=x+y"
    );
    assert.equal(result.init, undefined);
    assert.deepEqual(proxyCalls.at(-1), { path: result.path, init: undefined });
    assert.deepEqual(fetchCalls, []);
  } finally {
    globalThis.fetch = originalFetch;
  }
});


test("missing catch-all path keeps the base research runs route", async () => {
  const result = await GET(
    new Request("http://127.0.0.1:3000/api/research/runs"),
    { params: Promise.resolve({}) }
  );

  assert.equal(result.path, "/research/runs");
  assert.equal(result.init, undefined);
});
