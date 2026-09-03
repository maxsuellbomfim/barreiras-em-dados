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
  resolveStateLoaStudyPage: () => 1,
  stateLoaStudyPageHref: () => "",
}));

const {
  parseStateLoaStudyRows,
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
    total_count: 27,
    methodology_version: "bahia-state-loa-study/1.0.0",
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
    totalCount: 27,
    methodologyVersion: "bahia-state-loa-study/1.0.0",
  });
  assert.equal(parseStateLoaStudyRows([{
    amendment_items: [],
    execution_items: [],
    total_count: 1,
    methodology_version: "bahia-state-loa-study/1.0.0",
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
    methodology_version: "bahia-state-loa-study/1.0.0",
  }]), null);
});

test("paginação estadual aceita somente uma página positiva e preserva o ano", () => {
  assert.equal(resolveStateLoaStudyPage("2"), 2);
  assert.equal(resolveStateLoaStudyPage(["2", "3"]), 1);
  assert.equal(resolveStateLoaStudyPage("0"), 1);
  assert.equal(resolveStateLoaStudyPage("2.5"), 1);
  assert.equal(
    stateLoaStudyPageHref(2026, 3),
    "/recursos?origem=estadual&ano=2026&estadual_pagina=3#emendas-estaduais",
  );
});

test("cliente carrega somente a página estadual visível e a interface informa o universo", () => {
  assert.match(client, /get_public_bahia_state_loa_study/);
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
});
