import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import {
  getMunicipalControlDocument,
  searchMunicipalControlDocuments,
} from "../../apps/web/lib/municipal-control-documents.ts";

const indexPage = await readFile(
  new URL("../../apps/web/app/financas/base-legal/page.tsx", import.meta.url),
  "utf8",
);
const detailPage = await readFile(
  new URL(
    "../../apps/web/app/financas/base-legal/[documentId]/page.tsx",
    import.meta.url,
  ),
  "utf8",
);
const financePage = await readFile(
  new URL("../../apps/web/app/financas/page.tsx", import.meta.url),
  "utf8",
);
const sitemapSource = await readFile(
  new URL("../../apps/web/app/sitemap.ts", import.meta.url),
  "utf8",
);

const originalFetch = globalThis.fetch;
const originalUrl = process.env.PUBLIC_DATA_SUPABASE_URL;
const originalKey = process.env.PUBLIC_DATA_SUPABASE_PUBLISHABLE_KEY;

test.afterEach(() => {
  globalThis.fetch = originalFetch;
  process.env.PUBLIC_DATA_SUPABASE_URL = originalUrl;
  process.env.PUBLIC_DATA_SUPABASE_PUBLISHABLE_KEY = originalKey;
});

function configurePublicData() {
  process.env.PUBLIC_DATA_SUPABASE_URL = "https://example.supabase.co";
  process.env.PUBLIC_DATA_SUPABASE_PUBLISHABLE_KEY = "sb_publishable_fixture";
}

test("busca retorna metadados e trecho sem hidratar o texto integral", async () => {
  configurePublicData();
  globalThis.fetch = async (_url, request) => {
    assert.deepEqual(JSON.parse(request.body), {
      search_query: "controle interno",
      page_size: 20,
      page_offset: 0,
    });
    return {
      ok: true,
      json: async () => [{
        document_id: "00000000-0000-0000-0000-000000000911",
        title: "Lei de controle interno",
        reference_date: "01/01/2024",
        excerpt: "Art. 1º Esta lei organiza o controle interno.",
        document_source_url: "https://barreiras.ba.gov.br/lei-controle.docx",
        document_artifact_sha256: "b".repeat(64),
        collected_at: "2026-09-01T10:01:00.000Z",
        total_count: 1,
        methodology_version: "municipal-control-text/1.0.0",
      }],
    };
  };

  const result = await searchMunicipalControlDocuments({
    query: "controle interno",
    pageSize: 20,
    offset: 0,
  });

  assert.equal(result.state, "available");
  assert.equal(result.documents.length, 1);
  assert.equal(result.totalCount, 1);
  assert.equal("fullText" in result.documents[0], false);
});

test("detalhe exige hashes válidos e conserva o texto literal", async () => {
  configurePublicData();
  globalThis.fetch = async (_url, request) => {
    assert.deepEqual(JSON.parse(request.body), {
      document_id_filter: "00000000-0000-0000-0000-000000000911",
    });
    return {
      ok: true,
      json: async () => [{
        document_id: "00000000-0000-0000-0000-000000000911",
        title: "Lei de controle interno",
        reference_date: "01/01/2024",
        description: null,
        full_text: "Art. 1º Texto integral oficial.",
        document_source_url: "https://barreiras.ba.gov.br/lei-controle.docx",
        document_artifact_sha256: "b".repeat(64),
        text_sha256: "d".repeat(64),
        parser_version: "docx-wordprocessingml/1.0.0",
        collected_at: "2026-09-01T10:01:00.000Z",
        methodology_version: "municipal-control-text/1.0.0",
      }],
    };
  };

  const result = await getMunicipalControlDocument(
    "00000000-0000-0000-0000-000000000911",
  );

  assert.equal(result.state, "available");
  assert.equal(result.document.fullText, "Art. 1º Texto integral oficial.");
  assert.equal(result.document.documentArtifactSha256, "b".repeat(64));
  assert.equal(result.document.textSha256, "d".repeat(64));
});

test("páginas explicam o limite e ligam lista, detalhe e fonte oficial", () => {
  assert.match(indexPage, /Buscar na base legal/);
  assert.match(indexPage, /texto literal/i);
  assert.match(indexPage, /não são demonstrativos financeiros/i);
  assert.match(detailPage, /Texto integral preservado/);
  assert.match(detailPage, /Abrir documento oficial/);
  assert.match(detailPage, /SHA-256/);
  assert.match(financePage, /href="\/financas\/base-legal"/);
});

test("sitemap publica a coleção e somente detalhes verificados", () => {
  assert.match(sitemapSource, /route:\s*["']\/financas\/base-legal["']/);
  assert.match(sitemapSource, /searchMunicipalControlDocuments\(\{ pageSize: 50 \}\)/);
  assert.match(sitemapSource, /legalDocuments\.state === ["']available["']/);
  assert.match(sitemapSource, /financas\/base-legal\/\$\{document\.documentId\}/);
});
