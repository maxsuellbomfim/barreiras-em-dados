import assert from "node:assert/strict";
import test from "node:test";

const module = await import(
  "../../apps/web/lib/state-loa-representative-contributions.mjs"
).catch(() => ({
  parseStateLoaRepresentativeContributions: () => null,
  stateLoaContributionsForRepresentative: () => [],
}));

const {
  parseStateLoaRepresentativeContributions,
  stateLoaContributionsForRepresentative,
} = module;

const linked2026 = {
  representative_source_kind: "state",
  representative_external_id: "921264",
  representative_profile_url:
    "https://www.al.ba.gov.br/deputados/deputado-estadual/921264",
  author_key: "antonio henrique junior",
  author_name: "Antonio Henrique Júnior",
  fiscal_year: 2026,
  amendment_count: 2,
  authorized_amount: "300000.00",
  matched_amendment_count: 1,
  matched_authorized_amount: "200000.00",
  committed_amount: "150000.00",
  liquidated_amount: "100000.00",
  paid_amount: "90000.00",
  blocked_amendment_count: 1,
  methodology_version: "bahia-state-loa-representative-contributions/1.0.0",
};

test("valida contribuição anual sem transformar execução bloqueada em zero", () => {
  const rows = parseStateLoaRepresentativeContributions([
    linked2026,
    {
      ...linked2026,
      fiscal_year: 2022,
      amendment_count: 1,
      authorized_amount: "100000.00",
      matched_amendment_count: 0,
      matched_authorized_amount: null,
      committed_amount: null,
      liquidated_amount: null,
      paid_amount: null,
      blocked_amendment_count: 1,
    },
  ]);

  assert.equal(rows?.length, 2);
  assert.equal(rows?.[1]?.paidAmount, null);
  assert.equal(rows?.[1]?.blockedAmendmentCount, 1);
});

test("rejeita total financeiro quando nenhuma emenda possui ligação única", () => {
  assert.equal(parseStateLoaRepresentativeContributions([{
    ...linked2026,
    matched_amendment_count: 0,
    matched_authorized_amount: "0.00",
    committed_amount: "0.00",
    liquidated_amount: "0.00",
    paid_amount: "0.00",
    blocked_amendment_count: 2,
  }]), null);
});

test("seleciona somente o perfil oficial e ordena os exercícios recentes primeiro", () => {
  const rows = parseStateLoaRepresentativeContributions([
    { ...linked2026, fiscal_year: 2022 },
    linked2026,
    {
      ...linked2026,
      representative_external_id: "outro-perfil",
      fiscal_year: 2025,
    },
  ]);
  assert.ok(rows);
  assert.deepEqual(
    stateLoaContributionsForRepresentative(rows, "state", "921264")
      .map((row) => row.fiscalYear),
    [2026, 2022],
  );
});
