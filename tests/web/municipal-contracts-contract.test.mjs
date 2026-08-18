import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import {
  municipalSupplierLabel,
  parseMunicipalContractRows,
} from "../../apps/web/lib/municipal-contracts.mjs";

const migration = await readFile(
  new URL(
    "../../supabase/migrations/20260818180000_public_municipal_contracts.sql",
    import.meta.url,
  ),
  "utf8",
);
const page = await readFile(
  new URL("../../apps/web/app/licitacoes/page.tsx", import.meta.url),
  "utf8",
);

const SHA = "d".repeat(64);

function contractRow(overrides = {}) {
  return {
    contract_id: "9c1c6a1e-0000-4000-8000-000000000001",
    source_contract_id: "1549",
    contract_number: "222/2024",
    contract_object: "Aquisição de materiais de expediente.",
    supplier_name: "COMERCIAL VALOIS LTDA",
    supplier_document_kind: "cnpj",
    supplier_document: "44493204000187",
    contract_value_text: "R$ 105.460,50",
    referential_value_text: null,
    modality_code: "6",
    category_code: "2",
    validity_start_text: "11/09/2024",
    validity_end_text: "11/09/2025",
    document_url: "https://barreiras.mtransparente.com.br/x.pdf",
    api_source_url:
      "https://portaldatransparencia.barreiras.ba.gov.br/api?resource=contratos",
    artifact_sha256: SHA,
    document_artifact_sha256: null,
    document_preserved: false,
    collected_at: "2026-08-18T18:00:00+00:00",
    methodology_version: "municipal-contracts/1.0.0",
    ...overrides,
  };
}

test("contrato com CNPJ é publicado com valor literal e evidência", () => {
  const parsed = parseMunicipalContractRows([contractRow()]);
  assert.notEqual(parsed, null);
  assert.equal(parsed[0].contractValueText, "R$ 105.460,50");
  assert.equal(parsed[0].supplierDocument, "44493204000187");
  assert.equal(
    municipalSupplierLabel(parsed[0]),
    "CNPJ 44.493.204/0001-87",
  );
});

test("pessoa física aparece sem nenhum dígito de CPF, em qualquer camada", () => {
  const parsed = parseMunicipalContractRows([
    contractRow({
      supplier_name: "ALMERY MESSIAS DA SILVEIRA",
      supplier_document_kind: "cpf_pessoa_fisica",
      supplier_document: null,
    }),
  ]);
  assert.notEqual(parsed, null);
  assert.equal(parsed[0].supplierDocument, null);
  assert.match(municipalSupplierLabel(parsed[0]), /CPF não publicado/);
  assert.equal(
    parseMunicipalContractRows([
      contractRow({
        supplier_document_kind: "cpf_pessoa_fisica",
        supplier_document: "46300000000",
      }),
    ]),
    null,
    "qualquer CPF vindo da API invalida o lote inteiro",
  );
  assert.equal(
    parseMunicipalContractRows([
      contractRow({ supplier_document: "463.000.000-00" }),
    ]),
    null,
    "documento fora do formato CNPJ de 14 dígitos é rejeitado",
  );
});

test("a projeção SQL nunca publica CPF nem converte valores", () => {
  assert.match(migration, /cpf_pessoa_fisica/);
  assert.match(
    migration,
    /when length\(candidate\.document_digits\) = 14\s*\n\s*then candidate\.document_digits/,
    "apenas o CNPJ de 14 dígitos sai da projeção",
  );
  assert.doesNotMatch(
    migration,
    /valor[^\n]*::numeric/i,
    "valores permanecem texto literal da fonte",
  );
  assert.match(migration, /municipal-contracts\/1\.0\.0/);
});

test("a página cita a série municipal sem prometer avaliação", () => {
  assert.match(page, /Contratos da Prefeitura/);
  assert.match(page, /CPF de pessoa\s+física nunca é exibido/);
  assert.match(page, /não são convertidos nem somados/);
});
