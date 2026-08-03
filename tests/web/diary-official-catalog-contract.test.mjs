import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const catalogMigration = await readFile(
  new URL(
    "../../supabase/migrations/20260808050000_official_diary_catalog.sql",
    import.meta.url,
  ),
  "utf8",
);
const projectionMigration = await readFile(
  new URL(
    "../../supabase/migrations/20260808060000_public_diary_catalog_projection.sql",
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

