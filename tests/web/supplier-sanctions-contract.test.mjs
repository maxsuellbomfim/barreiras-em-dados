import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import {
  formatSanctionCnpj,
  parseSupplierSanctionRows,
  sanctionRegistryLabel,
} from "../../apps/web/lib/supplier-sanctions.mjs";

const migration = await readFile(
  new URL(
    "../../supabase/migrations/20260819004720_publish_supplier_sanctions.sql",
    import.meta.url,
  ),
  "utf8",
);
const page = await readFile(
  new URL("../../apps/web/app/licitacoes/page.tsx", import.meta.url),
  "utf8",
);
const connector = await readFile(
  new URL(
    "../../workers/collectors/src/barreiras_collectors/connectors/cgu_sanctions.py",
    import.meta.url,
  ),
  "utf8",
);

const SHA = "e".repeat(64);

function sanctionRow(overrides = {}) {
  return {
    sanction_record_id: "9c1c6a1e-0000-4000-8000-000000000002",
    registry: "ceis",
    sanction_id: "288186",
    supplier_cnpj: "44493204000187",
    sanctioned_name: "COMERCIAL EXEMPLO LTDA",
    company_name: "COMERCIAL EXEMPLO LTDA",
    sanction_type: "Impedimento/proibição de contratar",
    sanctioning_body: "Prefeitura Municipal de Exemplo",
    sanctioning_body_sphere: "MUNICIPAL",
    sanctioning_body_uf: "BA",
    sanction_source: "CGU",
    process_number: "0000509",
    start_date_text: "14/12/2022",
    end_date_text: "14/12/2032",
    publication_date_text: null,
    reference_date_text: "18/08/2026",
    legal_basis_codes: ["LEI 8666 - ART. 87"],
    api_source_url:
      "https://api.portaldatransparencia.gov.br/api-de-dados/ceis",
    artifact_sha256: SHA,
    collected_at: "2026-08-18T21:00:00+00:00",
    methodology_version: "supplier-sanctions/1.0.0",
    ...overrides,
  };
}

test("sanção de fornecedor é publicada como espelho literal com evidência", () => {
  const parsed = parseSupplierSanctionRows([sanctionRow()]);
  assert.notEqual(parsed, null);
  assert.equal(parsed[0].registry, "ceis");
  assert.equal(parsed[0].startDateText, "14/12/2022");
  assert.deepEqual(parsed[0].legalBasisCodes, ["LEI 8666 - ART. 87"]);
  assert.equal(formatSanctionCnpj(parsed[0].supplierCnpj), "44.493.204/0001-87");
  assert.match(sanctionRegistryLabel("cnep"), /Lei Anticorrupção/);
});

test("documento fora do CNPJ de 14 dígitos invalida o lote no navegador", () => {
  assert.equal(
    parseSupplierSanctionRows([sanctionRow({ supplier_cnpj: "43515770453" })]),
    null,
  );
  assert.equal(
    parseSupplierSanctionRows([sanctionRow({ registry: "outro" })]),
    null,
  );
  assert.equal(
    parseSupplierSanctionRows([
      sanctionRow({ methodology_version: "supplier-sanctions/9.9.9" }),
    ]),
    null,
  );
});

test("a projeção SQL gate-a pessoa física e o coletor nunca a materializa", () => {
  assert.match(migration, /sanctioned_document' ~ '\^\[0-9\]\{14\}\$'/);
  assert.match(migration, /is distinct from 'Pessoa Física'/);
  assert.match(migration, /nao afirma culpa/);
  assert.match(
    connector,
    /len\(digits\) != 14 or person_type == "Pessoa Física"/,
    "o parser do coletor descarta pessoa física antes de materializar",
  );
  assert.match(connector, /chave-api-dados/);
  assert.doesNotMatch(
    connector,
    /TRANSPARENCIA_API_KEY\s*=\s*["'][0-9a-f]/,
    "nenhum valor de chave embutido no código",
  );
});

test("a página enquadra o painel como espelho, sem afirmação de culpa", () => {
  assert.match(page, /Fornecedores conferidos no CEIS e no CNEP/);
  assert.match(page, /não\s+afirma culpa nem irregularidade/);
  assert.match(page, /nenhum fornecedor verificado constava/);
});
