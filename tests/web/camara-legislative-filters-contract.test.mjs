import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const migration = await readFile(
  new URL("../../supabase/migrations/20260808140000_camara_legislative_author_summary.sql", import.meta.url),
  "utf8",
);
const client = await readFile(new URL("../../apps/web/lib/camara-legislative.ts", import.meta.url), "utf8");
const page = await readFile(new URL("../../apps/web/app/camara/page.tsx", import.meta.url), "utf8");
const explorer = await readFile(new URL("../../apps/web/app/camara/laws-explorer.tsx", import.meta.url), "utf8");
const representativesPage = await readFile(
  new URL("../../apps/web/app/representantes/page.tsx", import.meta.url),
  "utf8",
);

test("resumo de autoria usa a mesma taxonomia e filtros do acervo", () => {
  assert.match(migration, /get_camara_legislative_author_summary/);
  assert.match(migration, /item_kind_filter/);
  assert.match(migration, /year_filter/);
  assert.match(migration, /author_filter/);
  assert.match(migration, /query_filter/);
  assert.match(migration, /group by filtered\.author_name/);
  assert.match(migration, /raw\.raw_records/);
});

test("página consulta e exibe a contagem global de autoria", () => {
  assert.match(client, /get_camara_legislative_author_summary/);
  assert.match(client, /item_count/);
  assert.match(page, /getCamaraLegislativeAuthorSummary/);
  assert.match(page, /authorSummary/);
  assert.match(explorer, /Contagem global no recorte atual/);
  assert.match(explorer, /authorQuery/);
  assert.match(page, /A maior parte das leis/);
  assert.match(page, /não consolidamos pessoas/);
});

test("perfil de vereador não infere autoria nem promove bandeiras", () => {
  assert.doesNotMatch(representativesPage, /legislativeAuthorMatch|officialNameKey/);
  assert.doesNotMatch(representativesPage, /person-legislative-summary|principal bandeira/i);
});
