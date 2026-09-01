import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const pageUrl = new URL("../../apps/web/app/estado/page.tsx", import.meta.url);
const homeUrl = new URL("../../apps/web/app/page.tsx", import.meta.url);
const routeUrl = new URL(
  "../../apps/web/app/api/health/route.ts",
  import.meta.url,
);
const sitemapUrl = new URL("../../apps/web/app/sitemap.ts", import.meta.url);

test("estado público reutiliza a mesma fotografia operacional da API", async () => {
  const [page, route] = await Promise.all([
    readFile(pageUrl, "utf8"),
    readFile(routeUrl, "utf8"),
  ]);

  assert.match(page, /getOperationalHealthSnapshot/);
  assert.match(route, /getOperationalHealthSnapshot/);
  assert.doesNotMatch(route, /getOfficialDiaryCatalog/);
  assert.doesNotMatch(route, /getPublicFinanceCoverage/);
});

test("página distingue disponível, vazio e indisponível sem prometer cobertura", async () => {
  const page = await readFile(pageUrl, "utf8");

  assert.match(page, /Dados disponíveis agora/);
  assert.match(page, /Fonte consultada, sem registros neste recorte/);
  assert.match(page, /Consulta indisponível agora/);
  assert.match(page, /não mede a cobertura histórica completa/);
  assert.doesNotMatch(page, /100%/);
});

test("página inicial oferece acesso direto ao estado das fontes", async () => {
  const [home, sitemap] = await Promise.all([
    readFile(homeUrl, "utf8"),
    readFile(sitemapUrl, "utf8"),
  ]);

  assert.match(home, /Estado das fontes/);
  assert.match(home, /href:\s*["']\/estado["']/);
  assert.match(sitemap, /route:\s*["']\/estado["']/);
});
