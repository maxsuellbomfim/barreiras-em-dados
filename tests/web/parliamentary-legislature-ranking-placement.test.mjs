import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const resourcesPage = await readFile(
  new URL("../../apps/web/app/recursos/page.tsx", import.meta.url),
  "utf8",
);
const representativesPage = await readFile(
  new URL("../../apps/web/app/representantes/page.tsx", import.meta.url),
  "utf8",
);
const rankingComponent = await readFile(
  new URL(
    "../../apps/web/app/recursos/legislature-transfer-rankings.tsx",
    import.meta.url,
  ),
  "utf8",
);

test("keeps the complete legislature ranking in the Resources journey", () => {
  assert.match(resourcesPage, /import LegislatureTransferRankings from "\.\/legislature-transfer-rankings"/u);
  assert.match(resourcesPage, /getPublicParliamentaryLegislatureRankings\(\)/u);
  assert.match(resourcesPage, /getPublicParliamentaryLegislatureCoverage\(\)/u);
  assert.match(resourcesPage, /getPublicParliamentaryLegislatureYearCoverage\(\)/u);
  assert.match(resourcesPage, /href="\/recursos\?origem=legislaturas#emendas-por-legislatura"/u);
  assert.match(resourcesPage, /sourceSelection\.showLegislatures/u);
  assert.match(resourcesPage, /<LegislatureTransferRankings/u);
  assert.match(resourcesPage, /yearCoverage=\{legislatureYearCoverage\}/u);
  assert.match(rankingComponent, /id="emendas-por-legislatura"/u);
  assert.match(rankingComponent, /Quem aparece com mais recursos no acervo de cada legislatura\?/u);
  assert.match(rankingComponent, /Recorte parcial:/u);
});

test("removes the complete ranking from Quem decide but preserves discovery", () => {
  assert.doesNotMatch(representativesPage, /import LegislatureTransferRankings/u);
  assert.doesNotMatch(representativesPage, /<LegislatureTransferRankings/u);
  assert.match(
    representativesPage,
    /href="\/recursos\?origem=legislaturas#emendas-por-legislatura">Emendas por legislatura/u,
  );
  assert.match(representativesPage, /Emendas encontradas na legislatura atual/u);
});
