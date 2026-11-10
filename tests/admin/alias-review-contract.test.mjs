import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";
import test from "node:test";

const root = new URL("../../", import.meta.url);
const page = readFileSync(new URL("apps/admin/app/page.tsx", root), "utf8");
const FUNCTION = "review_representative_alias_suggestion";

// O PostgREST resolve a RPC pelos NOMES dos argumentos: renomear parâmetros na
// migration sem acompanhar o painel fazia toda revisão de alias falhar.
function latestParameterNames() {
  const directory = new URL("supabase/migrations/", root);
  const definition = new RegExp(
    `create (?:or replace )?function api\\.${FUNCTION}\\(([^)]*)\\)`,
  );
  let names = null;
  for (const file of readdirSync(directory).sort()) {
    const match = readFileSync(new URL(file, directory), "utf8").match(definition);
    if (!match) continue;
    names = match[1]
      .split(",")
      .map((parameter) => parameter.trim().split(/\s+/)[0])
      .filter(Boolean);
  }
  return names;
}

test("painel chama a revisão de alias com os nomes da definição vigente", () => {
  const names = latestParameterNames();
  assert.ok(names && names.length === 3, "definição da função não encontrada");
  const call = page.slice(page.indexOf(`"${FUNCTION}"`)).slice(0, 400);
  for (const name of names) {
    assert.match(call, new RegExp(`\\b${name}:`), `argumento ${name} ausente`);
  }
});
