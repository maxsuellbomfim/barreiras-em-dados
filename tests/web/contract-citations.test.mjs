import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import {
  citationYear,
  parseContractCitationRows,
} from "../../apps/web/lib/contract-citations.mjs";

const base = {
  review_state: "approved",
  approved_at: "2026-10-09T12:00:00+00:00",
  category: "sem_correspondencia",
  public_body: "FUNDO MUNICIPAL DE SAÚDE DE BARREIRAS",
  commitments: 2,
  payments: 2,
  unreadable_payments: 0,
  paid_amount: "1500.00",
  first_issue_date: "2025-07-10",
  last_issue_date: "2025-07-12",
  list_read_on: "2026-09-24",
  source_page_url: "https://portaldatransparencia.barreiras.ba.gov.br/despesas-geral",
  methodology_version: "contract-citation-comparison/1.0.0",
};
const entity = {
  ...base,
  row_kind: "entity",
  creditor_name: "CLINICA SANTA LTDA",
  cited_number: "338/2020",
  cited_excerpt: "Contrato nº 338/2020",
  latest_commitment_key: "O-2",
  pncp_url: null,
};
const person = {
  ...base,
  row_kind: "pf_aggregate",
  creditor_name: null,
  cited_number: null,
  cited_excerpt: null,
  latest_commitment_key: null,
  pncp_url: null,
};

test("antes da conferência só o estado chega à página", () => {
  assert.deepEqual(parseContractCitationRows([{
    review_state: "awaiting_review", row_kind: "status", creditor_name: null,
    methodology_version: "contract-citation-comparison/1.0.0",
  }]), { state: "awaiting_review" });
});

test("aprovado publica empresas e o agregado de pessoas físicas sem nome", () => {
  const parsed = parseContractCitationRows([entity, person]);
  assert.equal(parsed.state, "approved");
  assert.deepEqual(parsed.groups.map((group) => [group.kind, group.creditorName]), [
    ["entity", "CLINICA SANTA LTDA"],
    ["pf_aggregate", null],
  ]);
});

test("linha inválida ou pessoa física com nome derruba o conjunto", () => {
  assert.equal(parseContractCitationRows([{ ...person, creditor_name: "FULANA" }]), null);
  assert.equal(parseContractCitationRows([{ ...entity, paid_amount: "1500" }]), null);
  assert.equal(parseContractCitationRows([{ ...entity, category: "publicado_no_pncp" }]), null,
    "PNCP sem link não é publicado");
  assert.equal(parseContractCitationRows([{ ...entity, methodology_version: "x/2.0.0" }]), null);
  assert.equal(parseContractCitationRows([]), null);
});

test("ano fora do intervalo cai no ano corrente", () => {
  assert.equal(citationYear("2025", 2026), 2025);
  assert.equal(citationYear("2019", 2026), 2026);
  assert.equal(citationYear(undefined, 2026), 2026);
});

test("página fica fora do índice e sem link até a publicação", async () => {
  const page = await readFile(
    new URL("../../apps/web/app/financas/contratos-citados/page.tsx", import.meta.url), "utf8");
  assert.match(page, /robots: \{ index: false, follow: false \}/);
  assert.match(page, /Não indica irregularidade/);
  const finance = await readFile(new URL("../../apps/web/app/financas/page.tsx", import.meta.url),
    "utf8");
  const sitemap = await readFile(new URL("../../apps/web/app/sitemap.ts", import.meta.url), "utf8");
  assert.doesNotMatch(finance + sitemap, /contratos-citados/);
});
