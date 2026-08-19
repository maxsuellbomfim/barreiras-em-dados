import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import {
  municipalCategoryLabel,
  municipalModalityLabel,
  municipalSourceCodeLabel,
  parseMunicipalProcurementProcessRows,
} from "../../apps/web/lib/municipal-procurement-processes.mjs";

const migration = await readFile(
  new URL(
    "../../supabase/migrations/20260819053000_public_municipal_procurement_processes.sql",
    import.meta.url,
  ),
  "utf8",
);
const page = await readFile(
  new URL("../../apps/web/app/licitacoes/page.tsx", import.meta.url),
  "utf8",
);
const workflow = await readFile(
  new URL(
    "../../.github/workflows/collect-finance-documents.yml",
    import.meta.url,
  ),
  "utf8",
);

const SHA = "f".repeat(64);

function processRow(overrides = {}) {
  return {
    process_record_id: "9c1c6a1e-0000-4000-8000-000000000003",
    source_process_id: "762",
    process_number: "026/2026",
    notice_number: null,
    publication_date_text: "2026-06-09",
    opening_date_text: "2026-06-22",
    process_object:
      "Registro de preços para futura aquisição de medicamentos hospitalares.",
    bidding_type_code: null,
    modality_code: "9",
    category_code: "6",
    situation_code: "6",
    result_code: "4",
    estimated_value_text: "14237586.12",
    awarded_value_text: "0.00",
    api_source_url:
      "https://portaldatransparencia.barreiras.ba.gov.br/api?resource=processos",
    artifact_sha256: SHA,
    collected_at: "2026-08-19T05:00:00+00:00",
    methodology_version: "municipal-procurement-processes/1.0.0",
    ...overrides,
  };
}

test("processo licitatório é publicado com valores e códigos literais", () => {
  const parsed = parseMunicipalProcurementProcessRows([processRow()]);
  assert.notEqual(parsed, null);
  assert.equal(parsed[0].estimatedValueText, "14237586.12");
  assert.equal(parsed[0].situationCode, "6");
  assert.equal(parsed[0].resultCode, "4");
});

test("legenda verificada acompanha o código; código sem legenda fica literal", () => {
  assert.equal(
    municipalModalityLabel("9"),
    "Pregão Eletrônico (código 9 da fonte)",
  );
  assert.equal(
    municipalCategoryLabel("6"),
    "Serviços Técnicos (código 6 da fonte)",
  );
  assert.equal(
    municipalModalityLabel("99"),
    "código 99 (sem legenda publicada pela fonte)",
  );
  assert.equal(
    municipalSourceCodeLabel("6"),
    "código 6 (a fonte não publica legenda)",
  );
  assert.equal(municipalSourceCodeLabel(null), "não informado na fonte");
});

test("linha fora do contrato invalida o lote inteiro no navegador", () => {
  assert.equal(
    parseMunicipalProcurementProcessRows([
      processRow({ process_number: "  " }),
    ]),
    null,
  );
  assert.equal(
    parseMunicipalProcurementProcessRows([
      processRow({ methodology_version: "municipal-procurement-processes/9.9.9" }),
    ]),
    null,
  );
  assert.equal(
    parseMunicipalProcurementProcessRows([
      processRow({ artifact_sha256: "curto" }),
    ]),
    null,
  );
});

test("a projeção entrega o estado mais recente de um processo mutável", () => {
  assert.match(
    migration,
    /partition by coalesce\(\s*nullif\(btrim\(record\.payload ->> 'id'\), ''\)/,
    "a deduplicação usa o id estável do processo, não a chave por conteúdo",
  );
  assert.match(migration, /municipal_transparency_processos/);
  assert.match(
    migration,
    /valores permanecem TEXTO literal/i,
  );
});

test("a página enquadra códigos sem legenda e valores como texto da fonte", () => {
  assert.match(page, /Processos licitatórios da Prefeitura/);
  assert.match(page, /a\s+fonte não publica a\s+legenda/);
  assert.match(page, /Valor estimado \(texto da fonte\)/);
  assert.match(
    page,
    /limitação de coleta ou consulta, não ausência\s+de processos/,
  );
});

test("a coleta agenda o recurso processos sem o passo de PDFs", () => {
  assert.match(workflow, /"processos"/);
  assert.match(workflow, /,"processos","rreo"/);
  assert.match(workflow, /if: matrix\.resource != 'processos'/);
});
