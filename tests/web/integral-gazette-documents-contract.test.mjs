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
const index = await readFile(
  new URL(
    "../../apps/web/app/diario/integral-gazette-index.tsx",
    import.meta.url,
  ),
  "utf8",
);
const editionPage = await readFile(
  new URL(
    "../../apps/web/app/diario/[ano]/[edicao]/page.tsx",
    import.meta.url,
  ),
  "utf8",
);
const coverage = await readFile(
  new URL("../../apps/web/lib/public-diary-coverage.ts", import.meta.url),
  "utf8",
);
const notice = await readFile(
  new URL("../../apps/web/app/diario/diary-extraction-notice.tsx", import.meta.url),
  "utf8",
);

test("aviso acessível explica omissões, busca e limite do hash sem acusar a fonte", () => {
  assert.match(notice, /<aside/);
  assert.match(notice, /aria-label="Limitações do texto extraído"/);
  assert.match(notice, /páginas do acervo com texto incompleto/);
  assert.match(notice, /nomes, números e tabelas/);
  assert.match(notice, /não prova que ele não esteja no Diário/);
  assert.match(notice, /não comprova que a/);
});

test("Diário não confunde extração disponível com transcrição integral validada", () => {
  assert.match(page, /DiaryExtractionNotice/);
  assert.match(editionPage, /DiaryExtractionNotice/);
  assert.doesNotMatch(editionPage, /Transcrição integral|Fonte oficial, texto completo|na íntegra e pesquisável/);
  assert.doesNotMatch(index, /Ler documento na íntegra/);
  assert.doesNotMatch(explorer, /Texto literal preservado/);
});

test("paginacao do diario integral usa RPC com offset e navegacao publica", () => {
  assert.match(client, /get_integral_gazette_index_page/);
  assert.match(client, /page_offset/);
  assert.match(client, /hasMore/);
  assert.match(client, /pageSize \+ 1/);
  assert.match(page, /searchParams/);
  assert.match(page, /pageNumber/);
  assert.match(page, /Edi/);
});

test("busca global mantém o termo e pagina sem expor tabelas brutas", () => {
  assert.match(client, /search_integral_gazette_index/);
  assert.match(client, /query_text/);
  assert.match(page, /diary-global-query/);
  assert.match(page, /querySuffix/);
  assert.match(page, /IntegralGazetteIndex/);
  assert.doesNotMatch(index, /type="search"/);
});

test("diario explica cobertura sem confundir pagina com acervo total", () => {
  assert.match(page, /DiaryCoverageSummary/);
  assert.match(page, /Edições preservadas/);
  assert.match(page, /Catálogo oficial consultado/);
  assert.match(page, /Nesta página/);
});

test("diario informa a faixa da API sem prometer cobertura diária", () => {
  assert.match(page, /coverageStart/);
  assert.match(page, /coverageEnd/);
  assert.match(page, /Faixa de publicações preservadas pela API/);
  assert.match(page, /não uma\s+garantia de que todos os dias/);
});

test("cobertura pública classifica janela coletada sem chamar ausência de vazio", () => {
  assert.match(coverage, /get_public_querido_diario_coverage/);
  assert.match(coverage, /unclassified/);
  assert.match(page, /DiaryCoverageDetails/);
  assert.match(page, /Sem classificação/);
});

test("contrato público usa a RPC integral e rejeita payload incompleto", () => {
  assert.match(client, /get_integral_gazette_edition`/);
  assert.match(client, /get_integral_gazette_index_page/);
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
  assert.match(page, /IntegralGazetteIndex/);
  assert.match(editionPage, /IntegralGazetteExplorer/);
  assert.match(explorer, /<pre/);
  assert.match(explorer, /fullText/);
  assert.doesNotMatch(index, /fullText/);
  assert.match(explorer, /Texto da edição — separação segura indisponível/);
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
