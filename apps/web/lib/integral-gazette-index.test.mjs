import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import { toIntegralGazetteIndex } from "./integral-gazette-index.mjs";

const edition = {
  edition: 4706,
  editionYear: 2026,
  editionDate: "2026-08-04",
  artifactSha256: "a".repeat(64),
  methodologyVersion: "integral-gazette-documents/1.0.0",
  officialPublicationUrl: "https://barreiras.ba.gov.br/diario/4706.pdf",
  catalogUrl: null,
  catalogDate: "2026-08-04",
  documents: [
    {
      documentId: "documento-1",
      documentOrder: 1,
      literalTitle: "Portaria nº 261",
      documentType: "Portaria",
      pageStart: 1,
      pageEnd: 2,
      fullText: "Portaria nº 261\nTexto integral muito extenso.",
      textSha256: "b".repeat(64),
      publicationStatus: "validated",
    },
  ],
};

test("índice do Diário remove o texto integral sem perder evidência e endereço", () => {
  const [summary] = toIntegralGazetteIndex([edition]);
  const [document] = summary.documents;

  assert.equal("fullText" in document, false);
  assert.equal(document.literalTitle, "Portaria nº 261");
  assert.equal(document.textSha256, "b".repeat(64));
  assert.equal(
    document.permalink,
    "/diario/2026/4706#document-documento-1",
  );
  assert.equal(edition.documents[0].fullText.includes("muito extenso"), true);
});

test("página de acervo usa índice leve e a página permanente conserva o leitor integral", async () => {
  const [indexPage, editionPage, indexComponent] = await Promise.all([
    readFile(new URL("../app/diario/page.tsx", import.meta.url), "utf8"),
    readFile(
      new URL("../app/diario/[ano]/[edicao]/page.tsx", import.meta.url),
      "utf8",
    ),
    readFile(
      new URL("../app/diario/integral-gazette-index.tsx", import.meta.url),
      "utf8",
    ),
  ]);

  assert.match(indexPage, /toIntegralGazetteIndex/);
  assert.match(indexPage, /IntegralGazetteIndex/);
  assert.doesNotMatch(indexPage, /IntegralGazetteExplorer/);
  assert.match(editionPage, /IntegralGazetteExplorer/);
  assert.doesNotMatch(indexComponent, /\.fullText\b/);
  assert.doesNotMatch(indexComponent, /<pre\b/);
});
