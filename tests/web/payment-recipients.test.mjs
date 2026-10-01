import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  formatCnpj,
  parsePaymentRecipientRows,
  paymentYear,
} from "../../apps/web/lib/payment-recipients.mjs";

const read = (path) => readFileSync(new URL(`../../${path}`, import.meta.url), "utf8");
const page = read("apps/web/app/financas/quem-recebe/page.tsx");

const base = {
  creditors: 1,
  payments: 2,
  paid_amount: "334200.50",
  first_payment_date: "2025-07-10",
  last_payment_date: "2025-08-05",
  main_nature: "OUTROS SERVIÇOS DE TERCEIROS - PESSOA JURÍDICA",
  grid_artifact_sha256: "a".repeat(64),
  group_payments: 4,
  group_creditors: 3,
  group_paid_amount: "334500.49",
  year_payments: 7,
  year_paid_amount: "347500.49",
  year_prior_commitment_amount: "333200.00",
  year_uncollected_commitment_amount: "8299.99",
  year_bodies: [
    { public_body: "PREFEITURA MUNICIPAL DE BARREIRAS", payments: 6, paid_amount: "340500.49" },
    { public_body: "CÂMARA MUNICIPAL DE BARREIRAS", payments: 1, paid_amount: "7000.00" },
  ],
  year_grid_months: 2,
  year_unreadable_rows: 1,
  year_excluded_rows: 2,
  source_page_url: "https://portaldatransparencia.barreiras.ba.gov.br/despesas-geral",
  methodology_version: "municipal-payment-recipients/1.1.0",
  refreshed_at: "2026-10-01T01:39:49.591643+00:00",
};
const supplier = {
  ...base,
  payment_group: "compras_servicos",
  creditor_name: "RODE BEM LTDA",
  registry_cnpj: "11222333000181",
  registry_legal_name: "RODE BEM LOCACAO DE MAQUINAS LTDA",
  registry_legal_nature: "Sociedade Empresária Limitada",
  registry_month: "2026-09",
};
const people = {
  ...base,
  registry_cnpj: null,
  registry_legal_name: null,
  registry_legal_nature: null,
  registry_month: null,
  payment_group: "compras_servicos",
  creditor_name: null,
  creditors: 2,
  paid_amount: "299.99",
};

test("separa credores com nome do agregado sem nome e mantém decimais como texto", () => {
  const parsed = parsePaymentRecipientRows([supplier, people]);
  assert.equal(parsed.summary.paidAmount, "347500.49");
  assert.equal(parsed.summary.priorCommitmentAmount, "333200.00");
  assert.equal(parsed.summary.bodies[1].publicBody, "CÂMARA MUNICIPAL DE BARREIRAS");
  const [group] = parsed.groups;
  assert.equal(group.label, "Compras, obras, serviços e demais despesas");
  assert.deepEqual(group.recipients.map((row) => row.creditorName), ["RODE BEM LTDA"]);
  assert.equal(group.others.creditors, 2);
  assert.deepEqual(group.recipients[0].registry, {
    cnpj: "11222333000181", legalName: "RODE BEM LOCACAO DE MAQUINAS LTDA",
    legalNature: "Sociedade Empresária Limitada", month: "2026-09",
  });
  assert.equal(group.others.registry, null);
  assert.equal(formatCnpj("11222333000181"), "11.222.333/0001-81");
});

test("cadastro incompleto ou em agregado sem nome derruba o conjunto", () => {
  assert.equal(parsePaymentRecipientRows([{ ...supplier, registry_cnpj: "123" }]), null);
  assert.equal(parsePaymentRecipientRows([{ ...supplier, registry_legal_name: null }]), null);
  assert.equal(parsePaymentRecipientRows([{ ...people, registry_cnpj: "11222333000181",
    registry_legal_name: "X", registry_legal_nature: "Y", registry_month: "2026-09" }]), null);
  assert.equal(parsePaymentRecipientRows([{ ...supplier, registry_cnpj: null,
    registry_legal_name: null, registry_legal_nature: null, registry_month: null }])
    .groups[0].recipients[0].registry, null);
});

test("linha inválida derruba o conjunto", () => {
  assert.equal(parsePaymentRecipientRows([{ ...supplier, paid_amount: "334200.5" }]), null);
  assert.equal(parsePaymentRecipientRows([{ ...supplier, payment_group: "outro" }]), null);
  assert.equal(parsePaymentRecipientRows([{ ...supplier, methodology_version: "x/0" }]), null);
  assert.equal(parsePaymentRecipientRows([{ ...supplier, grid_artifact_sha256: "z" }]), null);
  assert.equal(parsePaymentRecipientRows([{ ...supplier, creditors: 2 }]), null, "nome é um credor");
  assert.equal(parsePaymentRecipientRows([{ ...supplier, year_bodies: [] }]), null);
  assert.equal(parsePaymentRecipientRows([{ ...supplier, refreshed_at: "ontem" }]), null);
  assert.equal(parsePaymentRecipientRows([people, people]), null, "um agregado por grupo");
  assert.equal(parsePaymentRecipientRows("x"), null);
  assert.deepEqual(parsePaymentRecipientRows([]), { summary: null, groups: [] });
});

test("ano fora da série volta para o ano corrente", () => {
  assert.equal(paymentYear("2025", 2026), 2025);
  assert.equal(paymentYear("2023", 2026), 2026);
  assert.equal(paymentYear("2027", 2026), 2026);
  assert.equal(paymentYear(undefined, 2026), 2026);
});

test("página traz as ressalvas e distingue falha de ausência", () => {
  assert.match(page, /não significa que não houve pagamentos/);
  assert.match(page, /isso não significa que nada foi pago/);
  assert.match(page, /não é a “despesa paga” do RREO/);
  assert.match(page, /Inclui pagamentos de restos a pagar/);
  assert.match(page, /Não entram pagamentos extraorçamentários/);
  assert.match(page, /não indicam irregularidade/);
  assert.match(page, /municipal-payment-recipients\/1\.1\.0/);
});
