import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const client = await readFile(
  new URL("../../apps/web/lib/integral-gazette-documents.ts", import.meta.url),
  "utf8",
);
const page = await readFile(
  new URL("../../apps/web/app/diario/page.tsx", import.meta.url),
  "utf8",
);
const explorer = await readFile(
  new URL(
    "../../apps/web/app/diario/integral-gazette-explorer.tsx",
    import.meta.url,
  ),
  "utf8",
);

test("paginacao do diario integral usa RPC com offset e navegacao publica", () => {
  assert.match(client, /get_integral_gazette_editions_page/);
  assert.match(client, /page_offset/);
  assert.match(client, /hasMore/);
  assert.match(client, /pageSize \+ 1/);
  assert.match(page, /searchParams/);
  assert.match(page, /pageNumber/);
  assert.match(page, /Edi/);
});

test("busca global mantém o termo e pagina sem expor tabelas brutas", () => {
  assert.match(client, /search_integral_gazette_editions/);
  assert.match(client, /query_text/);
  assert.match(page, /diary-global-query/);
  assert.match(page, /querySuffix/);
  assert.match(explorer, /initialQuery/);
});

test("diario explica cobertura sem confundir pagina com acervo total", () => {
  assert.match(page, /DiaryCoverageSummary/);
  assert.match(page, /Acervo integral preservado/);
  assert.match(page, /Catálogo oficial consultado/);
  assert.match(page, /Nesta página/);
});

test("contrato público usa a RPC integral e rejeita payload incompleto", () => {
  assert.match(client, /get_integral_gazette_editions/);
  assert.match(client, /function parseIntegralGazetteEdition/);
  assert.match(client, /textSha256/);
  assert.match(client, /pageStart/);
  assert.match(client, /pageEnd/);
  assert.match(client, /publicationStatus/);
  assert.match(client, /return \{ state: "unavailable" \}/);
  assert.match(client, /documents\.length === 0/);
});

test("interface mostra texto literal completo e não usa digest ou paráfrase", () => {
  assert.match(page, /getIntegralGazetteEditions/);
  assert.match(page, /IntegralGazetteExplorer/);
  assert.match(explorer, /<pre/);
  assert.match(explorer, /fullText/);
  assert.match(explorer, /Edição integral — separação segura indisponível/);
  assert.match(explorer, /type="search"/);
  assert.match(explorer, /document\.literalTitle/);
  assert.doesNotMatch(page, /Resumo oficial|Explicação em palavras simples|Diário Oficial traduzido/);
  assert.doesNotMatch(explorer, /Resumo oficial|Explicação em palavras simples|gerado com IA/);
});

test("documentos ficam recolhidos e a evidência da fonte permanece visível", () => {
  assert.match(explorer, /<details/);
  assert.match(explorer, /pageStart/);
  assert.match(explorer, /formatHash\(document\.textSha256\)/);
  assert.match(explorer, /officialPublicationUrl/);
  assert.match(explorer, /preservado/);
});
