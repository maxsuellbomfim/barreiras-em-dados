import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  parseBahiaSpecialTransferPayments,
  parseBahiaSpecialTransferRanking,
} from "../../apps/web/lib/bahia-special-transfers.mjs";

const page = readFileSync(
  new URL("../../apps/web/app/recursos/page.tsx", import.meta.url),
  "utf8",
);
const panel = readFileSync(
  new URL(
    "../../apps/web/app/recursos/bahia-special-transfers-panel.tsx",
    import.meta.url,
  ),
  "utf8",
);

function payment(overrides = {}) {
  return {
    fiscal_year: 2022,
    amendment_number: "40720003",
    amendment_year: 2021,
    official_amendment_code: "202140720003",
    source_author_name: "TITO",
    author_key: "tito",
    official_author_name: "Carlos Tito Marques Cordeiro",
    representative_source_kind: "federal",
    representative_external_id: "197438",
    representative_profile_url: "https://www.camara.leg.br/deputados/197438",
    association_status: "approved_official_author_code_crosswalk",
    agency_name: "SECRETARIA DA SAUDE",
    budget_unit_name: "FUNDO ESTADUAL DE SAUDE",
    action_name: "Apoio financeiro",
    payment_id: "202240720003000001",
    payment_number: "1234",
    payment_date: "2022-10-05",
    payment_amount: "594841.25",
    payment_status: "Sim",
    object_text: "Apoio a unidade de saude no municipio de Barreiras",
    payment_url: "https://www.transparencia.ba.gov.br/Pagamento/1234",
    financial_stage: "paid_by_bahia_state",
    territorial_scope: "payment_object_literal_barreiras",
    federal_link_status: "matched_cgu_unique",
    aggregation_policy: "single_source_no_cross_source_sum",
    evidence_text: "Barreiras - apoio financeiro",
    evidence_sha256: "a".repeat(64),
    source_url: "https://dados.ba.gov.br/dataset/transferencias-especiais",
    source_artifact_sha256: "b".repeat(64),
    source_collected_at: "2026-08-21T03:00:00+00:00",
    methodology_version: "bahia-special-transfer-payments/1.0.0",
    ...overrides,
  };
}

function ranking(overrides = {}) {
  return {
    rank_position: 1,
    author_key: "tito",
    official_author_name: "Carlos Tito Marques Cordeiro",
    representative_source_kind: "federal",
    representative_external_id: "197438",
    representative_profile_url: "https://www.camara.leg.br/deputados/197438",
    payment_count: 3,
    amendment_count: 2,
    paid_amount: "756904.75",
    first_payment_date: "2022-10-05",
    last_payment_date: "2022-11-17",
    ranking_amount_stage: "paid_by_bahia_state",
    territorial_scope: "payment_object_literal_barreiras",
    aggregation_policy: "single_source_no_cross_source_sum",
    methodology_version: "bahia-special-transfer-ranking/1.0.0",
    ...overrides,
  };
}

test("parsers aceitam somente fatos estaduais com escopo e metodologia exatos", () => {
  const payments = parseBahiaSpecialTransferPayments([payment()]);
  const rankings = parseBahiaSpecialTransferRanking([ranking()]);
  assert.equal(payments?.[0].paymentAmount, "594841.25");
  assert.equal(payments?.[0].federalLinkStatus, "matched_cgu_unique");
  assert.equal(rankings?.[0].paidAmount, "756904.75");
  assert.equal(rankings?.[0].amendmentCount, 2);

  assert.equal(
    parseBahiaSpecialTransferPayments([
      payment({ territorial_scope: "municipality_received" }),
    ]),
    null,
  );
  assert.equal(
    parseBahiaSpecialTransferRanking([
      ranking({ aggregation_policy: "sum_all_sources" }),
    ]),
    null,
  );
});

test("parsers rejeitam duplicidade, URL insegura e campos pessoais inesperados", () => {
  assert.equal(
    parseBahiaSpecialTransferPayments([payment(), payment()]),
    null,
  );
  assert.equal(
    parseBahiaSpecialTransferPayments([
      payment({ payment_url: "http://example.test/pagamento" }),
    ]),
    null,
  );
  assert.equal(
    parseBahiaSpecialTransferPayments([
      payment({ creditor_cnpj: "00000000000191" }),
    ]),
    null,
  );
  assert.equal(
    parseBahiaSpecialTransferRanking([
      ranking({ representative_profile_url: "javascript:alert(1)" }),
    ]),
    null,
  );
});

test("aba estadual separa pagamento, receita municipal e entrega fisica", () => {
  assert.match(page, /getPublicBahiaSpecialTransfers/);
  assert.match(page, /BahiaSpecialTransfersPanel/);
  assert.match(page, /Estadual · Bahia/);
  assert.match(panel, /Pagamentos do Estado cujo objeto menciona Barreiras/);
  assert.match(panel, /não comprova que a Prefeitura recebeu o dinheiro/);
  assert.match(panel, /não comprova que o bem, serviço ou obra foi entregue/);
  assert.match(panel, /não é somado aos valores da LOA, da CGU ou do Transferegov/);
  assert.match(panel, /Ranking desta fonte estadual/);
  assert.match(panel, /Trecho oficial e rastreabilidade/);
});
