import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  groupLinksByContract,
  parseCommitmentLinkRows,
} from "../../apps/web/lib/commitment-links.mjs";

const read = (path) => readFileSync(new URL(`../../${path}`, import.meta.url), "utf8");
const migration = read(
  "supabase/migrations/20260924021132_public_commitment_contract_links.sql",
);
const page = read("apps/web/app/licitacoes/page.tsx");
const sqlBody = migration.replace(/--[^\n]*/g, "");

const row = {
  link_id: "2f0c4c43-8f6d-4f5c-9a5e-1c0b4c0a8a11",
  contract_portal_id: "1520",
  commitment_key: "O-252163",
  commitment_number: "2281/5",
  issue_date_text: "23/09/2026",
  public_body: "FUNDO MUNICIPAL DE SAÚDE DE BARREIRAS",
  creditor_name: "CONSTRUTORA E SERVIÇOS CHAGAS EIRELI",
  note_type: "Estimativa",
  amount_text: "70287,86",
  cited_excerpt: "Contrato nº 070-FMS/2025",
  rule_version: "commitment-contract-link/1.0.0",
  review_mode: "automated",
  grid_artifact_sha256: "a".repeat(64),
  grid_retrieved_at: "2026-09-24T01:41:08Z",
  source_page_url: "https://portaldatransparencia.barreiras.ba.gov.br/despesas-geral",
  methodology_version: "commitment-contract-links/1.0.0",
};

test("o site só aceita ligações automáticas de empenhos orçamentários", () => {
  const [parsed] = parseCommitmentLinkRows([row]);
  assert.equal(parsed.commitmentNumber, "2281/5");
  assert.equal(parsed.amountText, "70287,86");
  for (const broken of [
    { commitment_key: "E-57409" },
    { review_mode: "human" },
    { methodology_version: "commitment-contract-links/0.9.0" },
    { grid_artifact_sha256: "curto" },
    { cited_excerpt: "" },
    { issue_date_text: "2026-09-23" },
  ]) {
    assert.equal(parseCommitmentLinkRows([{ ...row, ...broken }]), null);
  }
  assert.equal(parseCommitmentLinkRows({}), null);
});

test("ligações são agrupadas pelo id oficial do contrato", () => {
  const second = { ...row, link_id: "b".repeat(8), commitment_key: "O-1" };
  const grouped = groupLinksByContract(parseCommitmentLinkRows([row, second]));
  assert.equal(grouped.get("1520").length, 2);
});

test("a projeção publica só ligados vigentes, retirada auditável e sem somas", () => {
  assert.match(sqlBody, /link\.state = 'ligado'/);
  assert.match(sqlBody, /link\.rule_version = 'commitment-contract-link\/1\.0\.0'/);
  assert.match(sqlBody, /review\.target_type = 'finance\.commitment_contract_links'/);
  assert.match(sqlBody, /<> 'withdrawn'/);
  assert.match(sqlBody, /newer\.source_record_key = record\.source_record_key/);
  assert.match(sqlBody, /cardinality\(contract_ids\) > 200/);
  assert.doesNotMatch(sqlBody, /\bsum\(/i);
  // O histórico inteiro do empenho não sai: só o trecho que cita o contrato.
  assert.doesNotMatch(sqlBody, /field1144634/);
  assert.match(migration, /to anon, authenticated;/);
});

test("a página rotula a ligação e não trata ausência como zero", () => {
  assert.match(page, /getCommitmentLinksForContracts\(/);
  assert.match(page, /Ligação automática verificada por código, sujeita a correção/);
  assert.match(page, /não significa que\s+não existam/);
  assert.match(page, /Nenhum empenho já coletado cita este contrato pelo número/);
});
