import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const digestMigration = await readFile(
  new URL("../../supabase/migrations/20260808030000_public_diary_edition_dates.sql", import.meta.url),
  "utf8",
);
const integralClient = await readFile(
  new URL("../../apps/web/lib/integral-gazette-documents.ts", import.meta.url),
  "utf8",
);
const explorer = await readFile(
  new URL("../../apps/web/app/diario/integral-gazette-explorer.tsx", import.meta.url),
  "utf8",
);
const diaryPage = await readFile(
  new URL("../../apps/web/app/diario/page.tsx", import.meta.url),
  "utf8",
);
const acts = await readFile(
  new URL("../../apps/web/app/atos/act-explorer.tsx", import.meta.url),
  "utf8",
);
const procurement = await readFile(
  new URL("../../apps/web/app/licitacoes/procurement-explorer.tsx", import.meta.url),
  "utf8",
);
const finance = await readFile(
  new URL("../../apps/web/app/financas/page.tsx", import.meta.url),
  "utf8",
);

test("diário publica a data da fonte e mantém os documentos recolhidos", () => {
  assert.match(digestMigration, /edition_date date/);
  assert.match(digestMigration, /querido_diario_gazette/);
  assert.match(integralClient, /editionDate/);
  assert.match(diaryPage, /IntegralGazetteExplorer/);
  assert.match(explorer, /Data da edição não informada/);
});

test("atos padronizam título e data sem esconder a evidência", () => {
  assert.match(acts, /inferredPersonName/);
  assert.match(acts, /Ato de \$\{formatDate\(act\.gazetteDate\)\}/);
  assert.match(acts, /Nome recuperado do resumo assistido/);
});

test("compras explicam valores ausentes e começam com detalhes recolhidos", () => {
  assert.match(procurement, /orçamento sob sigilo/);
  assert.match(procurement, /Ainda não há valor homologado/);
  assert.match(procurement, /className="procurement-results"\>/);
});

test("finanças mostram resumo cidadão e ordenam fechamentos recentes", () => {
  assert.match(finance, /Quanto entrou, quanto saiu e quanto devemos/);
  assert.match(finance, /sortedMonthlyClosures/);
  assert.match(finance, /Dívida registrada/);
});
