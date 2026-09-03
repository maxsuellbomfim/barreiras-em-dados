import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const client = readFileSync(
  new URL("../../apps/web/lib/parliamentary-transfers.ts", import.meta.url),
  "utf8",
);
const page = readFileSync(
  new URL("../../apps/web/app/recursos/page.tsx", import.meta.url),
  "utf8",
);

const studyModule = await import(
  "../../apps/web/lib/state-loa-study.mjs"
).catch(() => ({
  parseStateLoaStudyRows: () => null,
  resolveStateLoaStudyFilters: () => ({
    page: 1,
    authorKey: null,
    executionStatus: null,
    query: null,
  }),
  resolveStateLoaStudyPage: () => 1,
  stateLoaStudyPageHref: () => "",
}));

const {
  parseStateLoaStudyRows,
  resolveStateLoaStudyFilters,
  resolveStateLoaStudyPage,
  stateLoaStudyPageHref,
} = studyModule;

test("estudo estadual valida página e mantém autorização separada da execução", () => {
  const parsed = parseStateLoaStudyRows([{
    amendment_items: [{
      amendment_number: "5715",
      evidence_sha256: "a".repeat(64),
    }],
    execution_items: [{
      amendment_number: "5715",
      loa_evidence_sha256: "a".repeat(64),
    }],
    total_count: 1,
    catalog_count: 27,
    available_authors: [{
      author_key: "marcone amaral",
      author_name: "Marcone Amaral",
    }],
    methodology_version: "bahia-state-loa-study/1.1.0",
  }]);

  assert.deepEqual(parsed, {
    amendmentRows: [{
      amendment_number: "5715",
      evidence_sha256: "a".repeat(64),
    }],
    executionRows: [{
      amendment_number: "5715",
      loa_evidence_sha256: "a".repeat(64),
    }],
    totalCount: 1,
    catalogCount: 27,
    availableAuthors: [{
      authorKey: "marcone amaral",
      authorName: "Marcone Amaral",
    }],
    methodologyVersion: "bahia-state-loa-study/1.1.0",
  });
  assert.equal(parseStateLoaStudyRows([{
    amendment_items: [],
    execution_items: [],
    total_count: 1,
    catalog_count: 27,
    available_authors: [],
    methodology_version: "bahia-state-loa-study/1.1.0",
  }]), null);
});

test("estudo estadual rejeita execução pertencente a outra autorização", () => {
  assert.equal(parseStateLoaStudyRows([{
    amendment_items: [{
      amendment_number: "5715",
      evidence_sha256: "a".repeat(64),
    }],
    execution_items: [{
      amendment_number: "9999",
      loa_evidence_sha256: "b".repeat(64),
    }],
    total_count: 1,
    catalog_count: 1,
    available_authors: [{
      author_key: "marcone amaral",
      author_name: "Marcone Amaral",
    }],
    methodology_version: "bahia-state-loa-study/1.1.0",
  }]), null);
});

test("filtros estaduais aceitam somente valores seguros e reiniciam na primeira página", () => {
  assert.deepEqual(resolveStateLoaStudyFilters({
    estadual_pagina: "3",
    estadual_autor: "  marcone amaral  ",
    estadual_situacao: "execution_confirmed",
    estadual_q: "  ônibus escolar  ",
  }), {
    page: 3,
    authorKey: "marcone amaral",
    executionStatus: "execution_confirmed",
    query: "ônibus escolar",
  });
  assert.deepEqual(resolveStateLoaStudyFilters({
    estadual_pagina: ["2", "3"],
    estadual_autor: "a".repeat(201),
    estadual_situacao: "pago",
    estadual_q: "q".repeat(101),
  }), {
    page: 1,
    authorKey: null,
    executionStatus: null,
    query: null,
  });
});

test("paginação estadual aceita somente uma página positiva e preserva o ano", () => {
  assert.equal(resolveStateLoaStudyPage("2"), 2);
  assert.equal(resolveStateLoaStudyPage(["2", "3"]), 1);
  assert.equal(resolveStateLoaStudyPage("0"), 1);
  assert.equal(resolveStateLoaStudyPage("2.5"), 1);
  assert.equal(
    stateLoaStudyPageHref(2026, 3, {
      page: 1,
      authorKey: "marcone amaral",
      executionStatus: "execution_confirmed",
      query: "ônibus escolar",
    }),
    "/recursos?origem=estadual&ano=2026&estadual_autor=marcone+amaral&estadual_situacao=execution_confirmed&estadual_q=%C3%B4nibus+escolar&estadual_pagina=3#emendas-estaduais",
  );
});

test("cliente carrega somente a página estadual visível e a interface informa o universo", () => {
  assert.match(client, /get_public_bahia_state_loa_study_filtered/);
  assert.match(client, /const stateLoaPageSize = 12/);
  assert.match(
    client,
    /page_offset:\s*\(resolvedStateLoaPage - 1\) \* stateLoaPageSize/,
  );
  assert.doesNotMatch(
    client,
    /get_public_bahia_state_loa_amendments[\s\S]+page_size:\s*200/,
  );
  assert.match(page, /\{amendments\.length\.toLocaleString\("pt-BR"\)\} nesta página de \{totalCount\.toLocaleString/);
  assert.match(page, /Página \{page\} de \{pageCount\.toLocaleString/);
  assert.match(page, /aria-label="Paginação das emendas estaduais"/);
  assert.match(page, /name="estadual_q"/);
  assert.match(page, /name="estadual_autor"/);
  assert.match(page, /name="estadual_situacao"/);
  assert.match(page, /Nenhuma emenda corresponde aos filtros informados/);
});
