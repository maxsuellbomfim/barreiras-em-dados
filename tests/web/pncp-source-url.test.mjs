import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import test from "node:test";
const requireWeb = createRequire(new URL("../../apps/web/package.json", import.meta.url));
const ts = requireWeb("typescript");
let source = "";
try { source = readFileSync(new URL("../../apps/web/lib/pncp-source-url.ts", import.meta.url), "utf8"); }
catch (error) { if (error.code !== "ENOENT") throw error; }
const mod = { exports: { pncpProcurementSourceUrl: () => null } };
if (source) new Function("module", "exports", ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
}).outputText)(mod, mod.exports);
const { pncpProcurementSourceUrl } = mod.exports;
test("link oficial conserva CNPJ, ano e sequência do controle publicado", () => {
  assert.equal(pncpProcurementSourceUrl("13250888000162-1-000003/2026"), "https://pncp.gov.br/app/editais/13250888000162/2026/3");
  assert.equal(pncpProcurementSourceUrl("13654405000195-1-000027/2025"), "https://pncp.gov.br/app/editais/13654405000195/2025/27");
});
test("controle inválido ou de contrato não fabrica link para uma compra", () => {
  for (const control of ["", "other", "13654405000195-2-000023/2026", "13250888000162-1-0/2026", "13250888000162-1-3/2026?evil=1", "13250888000162-1-3/2026\n"])
    assert.equal(pncpProcurementSourceUrl(control), null);
});
