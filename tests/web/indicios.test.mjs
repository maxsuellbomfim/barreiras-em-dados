import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import { formatCnpj, parseIndicioRows } from "../../apps/web/lib/indicios.mjs";

const row = {
  finding_id: "07f4d4fa-ba5a-4ad2-bb23-c06579fcb012",
  rule_slug: "supplier-recent-opening",
  rule_name: "Empresa recém-aberta com contrato relevante",
  rule_description: "Contrato de R$ 100 mil ou mais com empresa aberta até 180 dias antes.",
  rule_methodology: "supplier-recent-opening/1.0.0",
  severity: "medium",
  public_explanation: "Merece apuração. Não é prova de irregularidade.",
  review_rationale: "Conferido contra o portal e a Receita.",
  review_kind: "automated",
  reviewed_at: "2026-10-19T11:50:00+00:00",
  supplier_name: "EMPRESA EXEMPLO LTDA",
  supplier_cnpj: "12345678000190",
  contract_number: "1/2024",
  contract_object: "Materiais",
  contract_value: 1009100.45,
  contract_start: "2024-12-09",
  opened_on: "2024-06-18",
  days_after_opening: 174,
  amendments_value: 1512866.11,
  contract_source_url: "https://barreiras.mtransparente.com.br/admin//data/X.pdf",
  contract_artifact_sha256: "a".repeat(64),
  registry_artifact_sha256: "b".repeat(64),
  methodology_version: "public-indicios/1.0.0",
};

test("indício válido chega à página com decimal exato e rótulo da revisão", () => {
  const [item] = parseIndicioRows([row]);
  assert.equal(item.contractValue, "1009100.45");
  assert.equal(item.amendmentsValue, "1512866.11");
  assert.equal(item.reviewKind, "automated");
  assert.equal(item.daysAfterOpening, 174);
});

test("lista vazia é resultado válido; linha fora do contrato derruba o conjunto", () => {
  assert.deepEqual(parseIndicioRows([]), []);
  assert.equal(parseIndicioRows([{ ...row, rule_slug: "regra-desconhecida" }]), null);
  assert.equal(parseIndicioRows([{ ...row, supplier_cnpj: "123" }]), null);
  assert.equal(parseIndicioRows([{ ...row, review_kind: null }]), null);
  assert.equal(parseIndicioRows([{ ...row, methodology_version: "public-indicios/0.9.0" }]), null);
  assert.equal(parseIndicioRows(null), null);
});

test("contestação aberta só aparece com a metodologia 1.1.0 e valor verdadeiro", () => {
  assert.equal(parseIndicioRows([row])[0].underContestation, false);
  const [item] = parseIndicioRows([
    { ...row, methodology_version: "public-indicios/1.1.0", under_contestation: true },
  ]);
  assert.equal(item.underContestation, true);
});

test("CNPJ formatado para leitura", () => {
  assert.equal(formatCnpj("12345678000190"), "12.345.678/0001-90");
});

test("página fala em indício, nunca em acusação, e mostra a revisão", async () => {
  const page = await readFile(
    new URL("../../apps/web/app/indicios/page.tsx", import.meta.url),
    "utf8",
  );
  assert.match(page, /Indício não é prova/);
  assert.match(page, /Conferido automaticamente — sem revisão humana/);
  assert.match(page, /Conteste/);
  // ADR 0099: nenhuma afirmação de crime sobre empresa ou pessoa.
  for (const word of [/fraudou/i, /corrupto/i, /desviou/i, /superfaturou/i]) {
    assert.doesNotMatch(page, word);
  }
});
