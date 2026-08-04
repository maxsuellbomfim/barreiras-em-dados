import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const catalogMigration = await readFile(
  new URL(
    "../../supabase/migrations/20260803223641_official_diary_catalog.sql",
    import.meta.url,
  ),
  "utf8",
);
const projectionMigration = await readFile(
  new URL(
    "../../supabase/migrations/20260803223652_public_diary_catalog_projection.sql",
    import.meta.url,
  ),
  "utf8",
);
const workflow = await readFile(
  new URL(
    "../../.github/workflows/collect-querido-diario.yml",
    import.meta.url,
  ),
  "utf8",
);
const diaryPage = await readFile(
  new URL("../../apps/web/app/diario/page.tsx", import.meta.url),
  "utf8",
);
const catalogClient = await readFile(
  new URL("../../apps/web/lib/official-diary-catalog.ts", import.meta.url),
  "utf8",
);
const collectionStatusClient = await readFile(
  new URL("../../apps/web/lib/collection-status.ts", import.meta.url),
  "utf8",
);
const catalogFallbackMigration = await readFile(
  new URL(
    "../../supabase/migrations/20260804021751_public_official_diary_catalog.sql",
    import.meta.url,
  ),
  "utf8",
);

test("catálogo oficial preserva bruto e publica campos oficiais separados da IA", () => {
  assert.match(catalogMigration, /catalogo-publicacoes/);
  assert.match(catalogMigration, /pmbarreiras\.diariomtransparente\.com\.br/);
  assert.match(projectionMigration, /official_title text/);
  assert.match(projectionMigration, /barreiras_diario_publication/);
  assert.match(projectionMigration, /edition-digests\/1\.2\.0/);
  assert.match(workflow, /collect_official_diary_catalog/);
  assert.match(diaryPage, /Resumo oficial da Prefeitura/);
  assert.match(diaryPage, /officialPublicationUrl/);
});

test("edições recentes aparecem pelo catálogo antes do PDF integral", () => {
  assert.match(catalogFallbackMigration, /get_official_diary_catalog/);
  assert.match(catalogFallbackMigration, /barreiras_diario_publication/);
  assert.match(catalogClient, /get_official_diary_catalog/);
  assert.match(diaryPage, /Explicação detalhada ainda não disponível/);
  assert.match(diaryPage, /catalogOnlyEntries/);
});

test("links do catálogo público são aceitos somente em HTTPS", () => {
  assert.match(catalogClient, /function optionalHttpsUrl/);
  assert.match(catalogClient, /startsWith\("https:\/\/"\)/);
});

test("diário informa quando a fonte oficial foi consultada", () => {
  assert.match(diaryPage, /latestCatalogCollectedAt/);
  assert.match(diaryPage, /source-freshness/);
  assert.match(diaryPage, /Catálogo oficial preservado em/);
  assert.match(diaryPage, /getQueridoDiarioCollectionStatus/);
  assert.match(diaryPage, /Ver estado da coleta automática/);
  assert.match(collectionStatusClient, /get_querido_diario_collection_status/);
});
