import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  parsePropertyRentalRows,
  serializePropertyRentalsCsv,
  rentalYear,
} from "../../apps/web/lib/property-rentals.mjs";

const read = (path) => readFileSync(new URL(`../../${path}`, import.meta.url), "utf8");
const migration = read("supabase/migrations/20260930181544_public_property_rentals.sql");
const page = read("apps/web/app/financas/alugueis/page.tsx");
const suffixFix = read(
  "supabase/migrations/20260930181847_property_rentals_contract_suffix.sql",
);
const formatsFix = read(
  "supabase/migrations/20260930182103_property_rentals_contract_formats.sql",
);

const row = {
  landlord_name: "MARIA LOCADORA",
  public_body: "FUNDO MUNICIPAL DE SAÚDE",
  contract_text: "0242/2020",
  commitments: 2,
  committed_amount: "5898.92",
  paid_amount: "5460.45",
  first_commitment_date: "2025-07-03",
  last_commitment_date: "2025-07-20",
  description: "Locação de imóvel para funcionamento de UBS.",
  latest_commitment_key: "O-2",
  grid_artifact_sha256: "a".repeat(64),
  year_landlords: 2,
  year_commitments: 3,
  year_committed_amount: "8398.92",
  year_paid_amount: "5460.45",
  year_grid_months: 12,
  source_page_url: "https://portaldatransparencia.barreiras.ba.gov.br/despesas-geral",
  methodology_version: "municipal-property-rentals/1.2.0",
};

test("linhas válidas viram aluguéis e resumo do ano, com valores em texto", () => {
  const parsed = parsePropertyRentalRows([row, { ...row, contract_text: null }]);
  assert.equal(parsed.rentals.length, 2);
  assert.equal(parsed.rentals[0].committedAmount, "5898.92");
  assert.equal(parsed.rentals[1].contractText, null);
  assert.deepEqual(parsed.summary, {
    landlords: 2,
    commitments: 3,
    committedAmount: "8398.92",
    paidAmount: "5460.45",
    gridMonths: 12,
    addresses: null,
  });
  assert.deepEqual(parsePropertyRentalRows([]), { summary: null, rentals: [] });
});

test("qualquer linha fora do contrato derruba o conjunto", () => {
  for (const broken of [
    { committed_amount: 5898.92 },
    { paid_amount: "5.460,45" },
    { latest_commitment_key: "E-1" },
    { grid_artifact_sha256: "abc" },
    { methodology_version: "municipal-property-rentals/0.9.0" },
    { year_grid_months: null },
    { source_page_url: "http://inseguro" },
    { contract_text: "" },
  ]) {
    assert.equal(parsePropertyRentalRows([row, { ...row, ...broken }]), null, JSON.stringify(broken));
  }
  assert.equal(parsePropertyRentalRows(null), null);
});

test("ano fora da série volta para o ano corrente", () => {
  assert.equal(rentalYear("2025", 2026), 2025);
  assert.equal(rentalYear("2023", 2026), 2026);
  assert.equal(rentalYear("2027", 2026), 2026);
  assert.equal(rentalYear(undefined, 2026), 2026);
});

test("RPC pública soma em numeric, mascara CPF e só usa a grade mais recente", () => {
  assert.match(migration, /grant execute on function api\.get_public_property_rentals\(integer\)\s+to anon, authenticated;/);
  assert.match(migration, /editorial\.mask_cpf_v1\(grouped\.description\)/);
  assert.match(migration, /::numeric/);
  assert.match(migration, /distinct on \(artifact\.metadata -> 'cursor' ->> 'month'\)/);
  assert.match(migration, /LOCA\[ÇC\]\[ÃA\]O DE IM\[ÓO\]VE\(L\|IS\)/);
  assert.doesNotMatch(migration, /::float|double precision/);
  // 1.1.0: número com sufixo do órgão ("002-FMS/2023") também é lido.
  assert.match(suffixFix, /\(\?:-\[a-z\]\{2,6\}\)\?/);
  assert.match(suffixFix, /municipal-property-rentals\/1\.1\.0/);
  // 1.2.0: "nº" opcional e letra colada ("contrato 181/2022", "0205A/2020").
  assert.match(formatsFix, /\(\?:n\\s\*\[º°o\.\]\*\\s\*\)\?/);
  assert.match(formatsFix, /\(\?:-\?\[a-z\]\{1,6\}\)\?/);
  assert.match(formatsFix, /municipal-property-rentals\/1\.2\.0/);
});

test("página separa empenhado de pago e diz quando a consulta falhou", () => {
  assert.match(page, /Pago aos locadores/);
  assert.match(page, /Empenhado/);
  assert.match(page, /não significa que não haja aluguéis/);
  assert.match(page, /municipal-property-rentals\/1\.4\.0/);
  assert.match(page, /Baixar planilha/);
  assert.doesNotMatch(page, /contrato não citado/, "ausência de número não é ausência de contrato");
});

test("1.3.0 traz endereço e uso literais e endereços distintos do ano", () => {
  const located = {
    ...row,
    methodology_version: "municipal-property-rentals/1.3.0",
    address_text: "Rua A, 93",
    use_text: "UBS",
    year_addresses: 1,
  };
  const parsed = parsePropertyRentalRows([located, { ...located, address_text: null }]);
  assert.equal(parsed.rentals[0].addressText, "Rua A, 93");
  assert.equal(parsed.rentals[0].useText, "UBS");
  assert.equal(parsed.rentals[1].addressText, null);
  assert.equal(parsed.summary.addresses, 1);
  assert.equal(parsePropertyRentalRows([row]).summary.addresses, null, "1.2.0 não tem a contagem");
  assert.equal(parsePropertyRentalRows([{ ...located, year_addresses: -1 }]), null);
  assert.match(page, /não informado no histórico do empenho/);
});

test("1.4.0: endereço do Diário Oficial sempre aponta edição e página", () => {
  const gazette = {
    ...row,
    methodology_version: "municipal-property-rentals/1.4.0",
    address_text: "Rua Vasco da Gama, nº360, Vila Regina, Barreiras - BA",
    use_text: "Secretaria Municipal de Saúde",
    address_source: "diario_oficial",
    address_gazette_year: 2024,
    address_gazette_edition: 4195,
    address_gazette_page: 27,
    year_addresses: 1,
  };
  const parsed = parsePropertyRentalRows([gazette]);
  assert.deepEqual(parsed.rentals[0].addressGazette, { year: 2024, edition: 4195, page: 27 });
  assert.equal(parsed.rentals[0].addressSource, "diario_oficial");
  assert.equal(parsePropertyRentalRows([{ ...gazette, address_gazette_edition: null }]), null);
  assert.equal(parsePropertyRentalRows([{ ...gazette, address_source: "outra" }]), null);
  assert.equal(
    parsePropertyRentalRows([{ ...gazette, address_source: "historico_empenho" }]),
    null,
    "endereço do empenho não traz edição do Diário",
  );
});

test("planilha: BOM, ponto e vírgula, vírgula decimal e proteção contra fórmula", () => {
  const parsed = parsePropertyRentalRows([
    { ...row, landlord_name: "=HIPERLINK(1)", contract_text: "0242/2020" },
  ]);
  const csv = serializePropertyRentalsCsv(2025, { state: "available", ...parsed },
    "2026-10-01T00:00:00.000Z");
  assert.ok(csv.startsWith("\uFEFF\"ano\";\"locador\""));
  const [, line] = csv.trim().split("\r\n");
  assert.match(line, /"'=HIPERLINK\(1\)"/, "fórmula vira texto");
  assert.match(line, /"5898,92";"5460,45"/);
  assert.throws(() => serializePropertyRentalsCsv(2025, { state: "unavailable" }));
});
