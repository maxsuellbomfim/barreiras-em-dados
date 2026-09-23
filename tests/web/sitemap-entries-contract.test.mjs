import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import test from "node:test";

const requireWeb = createRequire(new URL("../../apps/web/package.json", import.meta.url));
const ts = requireWeb("typescript");
const source = readFileSync(new URL("../../apps/web/lib/sitemap-entries.ts", import.meta.url), "utf8");
const mod = { exports: {} };
new Function("module", "exports", ts.transpileModule(source, { compilerOptions: {
  module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022,
}}).outputText)(mod, mod.exports);
const { parseSitemapEntries } = mod.exports;

const migration = readFileSync(
  new URL("../../supabase/migrations/20260923170208_public_sitemap_entries.sql", import.meta.url),
  "utf8",
);
const sitemap = readFileSync(new URL("../../apps/web/app/sitemap.ts", import.meta.url), "utf8");

const at = "2026-09-23T12:00:00Z";

test("só chaves das páginas próprias válidas entram no sitemap", () => {
  const entries = parseSitemapEntries([
    { entry_kind: "diario_edicao", entry_key: "2026/4741", last_modified: at },
    { entry_kind: "contratacao", entry_key: "13654405000195-1-000040/2026", last_modified: at },
    { entry_kind: "fornecedor", entry_key: "44493204000187", last_modified: at },
    { entry_kind: "fornecedor", entry_key: "43515770453", last_modified: at },
    { entry_kind: "fornecedor", entry_key: "Fulano de Tal", last_modified: at },
    { entry_kind: "outro", entry_key: "x", last_modified: at },
    { entry_kind: "diario_edicao", entry_key: "2026/4741", last_modified: "ontem" },
  ]);
  assert.deepEqual(entries.map((entry) => entry.key), [
    "2026/4741",
    "13654405000195-1-000040/2026",
    "44493204000187",
  ]);
  assert.deepEqual(parseSitemapEntries({ code: "57014" }), []);
});

test("a RPC só lista fornecedor pessoa jurídica e nenhum conteúdo", () => {
  assert.match(migration, /tipoPessoa' = 'PJ'/);
  assert.match(migration, /niFornecedor' ~ '\^\[0-9\]\{14\}\$'/);
  const executable = migration.replace(/--.*$/gm, "").replace(/comment on[\s\S]*?';/g, "");
  assert.doesNotMatch(executable, /full_text|valor|nomeRazaoSocial/);
  assert.match(migration, /grant execute on function api\.get_public_sitemap_entries\(\) to anon/);
});

test("o sitemap só indexa meses com receita e despesa publicadas", () => {
  assert.match(sitemap, /coverageStatus === "complete"/);
  assert.match(sitemap, /encodeURIComponent\(key\)/);
});
