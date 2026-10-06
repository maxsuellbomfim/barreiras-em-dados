import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const migration = await readFile(
  new URL("../../supabase/migrations/20260808140000_camara_legislative_author_summary.sql", import.meta.url),
  "utf8",
);
const currentSummaryMigration = await readFile(
  new URL("../../supabase/migrations/20260808210000_current_legislature_author_summary.sql", import.meta.url),
  "utf8",
);
const aliasFilterMigration = await readFile(
  new URL("../../supabase/migrations/20260808230000_current_author_filter_aliases.sql", import.meta.url),
  "utf8",
);
const client = await readFile(new URL("../../apps/web/lib/camara-legislative.ts", import.meta.url), "utf8");
const page = await readFile(new URL("../../apps/web/app/camara/page.tsx", import.meta.url), "utf8");
const explorer = await readFile(new URL("../../apps/web/app/camara/laws-explorer.tsx", import.meta.url), "utf8");
const representativesPage = await readFile(
  new URL("../../apps/web/app/representantes/page.tsx", import.meta.url),
  "utf8",
);
const councillorsClient = await readFile(
  new URL("../../apps/web/lib/councillors.ts", import.meta.url),
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

test("grafico de autoria usa somente a composicao municipal atual", () => {
  assert.match(currentSummaryMigration, /get_camara_current_author_summary/);
  assert.match(currentSummaryMigration, /cm_barreiras_vereador/);
  assert.match(currentSummaryMigration, /representative_aliases/);
  assert.match(currentSummaryMigration, /where resolved\.current_author_name is not null/);
  assert.match(client, /get_camara_current_author_summary/);
  assert.match(page, /getCamaraCurrentAuthorSummary/);
  assert.match(explorer, /Somente os 19 nomes da/);
  assert.match(explorer, /visibleAuthors = authorSummary\.slice\(0, 19\)/);
  assert.match(explorer, /legislaturas anteriores aparecem no quadro seguinte/);
  assert.match(councillorsClient, /page_size: 19/);
});

test("clique no vereador usa aliases aprovados no resultado e no grafico", () => {
  assert.match(aliasFilterMigration, /normalize_public_author_name/);
  assert.match(aliasFilterMigration, /get_camara_legislative_page/);
  assert.match(aliasFilterMigration, /candidate_name\.canonical_key = filter_name\.canonical_key/);
  assert.match(aliasFilterMigration, /get_camara_current_author_summary/);
  assert.match(aliasFilterMigration, /filter_name\.canonical_name = resolved\.current_author_name/);
  assert.match(explorer, /Grafia, caixa alta e aliases aprovados/);
  assert.match(explorer, /legislative-kpis/);
});

test("pagina consulta e exibe a contagem global de autoria", () => {
  assert.match(client, /get_camara_legislative_author_summary/);
  assert.match(client, /item_count/);
  assert.match(page, /getCamaraCurrentAuthorSummary/);
  assert.match(page, /authorSummary/);
  assert.match(explorer, /contagem global no recorte atual/);
  assert.match(explorer, /authorQuery/);
  assert.match(page, /A maior parte das leis/);
  assert.match(page, /Apelidos, coautorias e suplentes continuam sem/);
});

test("perfil de vereador nao infere autoria nem promove bandeiras", () => {
  assert.doesNotMatch(representativesPage, /legislativeAuthorMatch|officialNameKey/);
  assert.doesNotMatch(representativesPage, /person-legislative-summary|principal bandeira/i);
});

const formerMigration = await readFile(
  new URL("../../supabase/migrations/20261006151700_camara_legislative_items_latest.sql", import.meta.url),
  "utf8",
);

test("ex-vereadores: vínculo só por nome oficial do TSE dentro de mandato encerrado", () => {
  assert.match(formerMigration, /term_end_year < current_year/);
  assert.match(formerMigration, /having count\(distinct mandate\.canonical_name\) = 1/);
  assert.match(formerMigration, /filtered\.reference_year between mandate\.term_start_year and mandate\.term_end_year/);
  assert.match(formerMigration, /item\.author_norm not in \(select name_key from current_names\)/);
  assert.match(client, /council-former-authors\/1\.0\.0/);
  assert.match(page, /getCamaraFormerAuthorSummary/);
  assert.match(page, /nome oficial do vereador eleito no TSE/);
  assert.match(explorer, /Autoria de vereadores de legislaturas anteriores/);
  assert.match(explorer, /suplentes em exercício ficam fora desta contagem/);
});

test("lista e resumos leem a tabela compacta mantida por gatilho, não o bruto inteiro", () => {
  assert.match(formerMigration, /after insert on raw\.raw_records/);
  assert.match(formerMigration, /where excluded\.collected_at >= political\.camara_legislative_items\.collected_at/);
  assert.match(formerMigration, /raw_record_id uuid not null references raw\.raw_records\(id\)/);
  assert.doesNotMatch(
    formerMigration.slice(formerMigration.indexOf("create or replace function api.get_camara_legislative_page")),
    /from raw\.raw_records as record\s+where record\.record_type = 'municipal_transparency/,
  );
});
