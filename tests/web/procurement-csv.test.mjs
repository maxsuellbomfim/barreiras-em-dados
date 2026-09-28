import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import {
  loadProcurementExport,
  parseExactProcurementRows,
  PROCUREMENT_EXPORT_PAGE,
  serializeProcurementCsv,
} from "../../apps/web/lib/procurement-csv.mjs";
import {
  procurementExportHref,
  procurementFiltersFromParams,
} from "../../apps/web/lib/procurement-filters.mjs";

const EXPORTED_AT = "2026-09-28T20:00:00.000Z";

function row(sequencial, overrides = "") {
  return `{"control_number":"13654405000195-1-${String(sequencial).padStart(6, "0")}/2025",
    "ano":2025,"sequencial":${sequencial},"modalidade":"Pregão - Eletrônico",
    "objeto":"=HYPERLINK(\\"x\\") aquisição de material","situacao":"Divulgada no PNCP",
    "unidade":"Secretaria de Saúde","valor_estimado":123456789012.34,
    "valor_homologado":0.1,"data_publicacao":"2025-03-10",
    "itens":[{"numero_item":1}],
    "resultados":[{"numero_item":1,"fornecedor":"Empresa A","tipo_pessoa":"PJ","ni_fornecedor":"12345678000199"},
                  {"numero_item":2,"fornecedor":"Fulano de Tal","tipo_pessoa":"PF","ni_fornecedor":"12345678909"}],
    "execution_summary":{"state":"linked","contracts_count":2},
    "methodology_version":"pncp-procurements/1.5.0"${overrides}}`;
}
const page = (rows) => `[${rows.join(",")}]`;
const sourceUrl = (control) => `https://pncp.gov.br/app/editais/${control}`;

test("valores em dinheiro saem com o decimal exato do banco", () => {
  const [parsed] = parseExactProcurementRows(page([row(1)]));
  assert.equal(parsed.valor_estimado, "123456789012.34");
  assert.equal(parsed.valor_homologado, "0.1");
  assert.equal(parsed.ano, 2025, "números que não são dinheiro continuam números");
});

test("CSV protege fórmulas, não expõe documento de fornecedor e traz cobertura", async () => {
  const result = await loadProcurementExport(async () => page([row(1)]));
  assert.equal(result.status, "ready");
  const csv = serializeProcurementCsv(result, sourceUrl, EXPORTED_AT);
  assert.ok(csv.startsWith("﻿\"numero_controle_pncp\";"));
  assert.match(csv, /"'=HYPERLINK\(""x""\) aquisição de material"/);
  assert.match(csv, /"123456789012,34";"0,1"/);
  assert.match(csv, /"Empresa A \| Fulano de Tal"/);
  assert.doesNotMatch(csv, /12345678909|12345678000199/);
  assert.match(csv, /"contratos vinculados: 2"/);
  assert.match(csv, /não prova que ela não exista na fonte oficial/);
  assert.match(csv, /"pncp-procurements-csv\/1\.0\.0"/);
  assert.match(csv, /"2026-09-28T20:00:00\.000Z"\r\n$/);
});

test("percorre todas as páginas e para na primeira incompleta", async () => {
  const offsets = [];
  const full = Array.from({ length: PROCUREMENT_EXPORT_PAGE }, (_, index) => row(index + 1));
  const result = await loadProcurementExport(async (offset) => {
    offsets.push(offset);
    return offset === 0 ? page(full) : page([row(1001)]);
  });
  assert.deepEqual(offsets, [0, PROCUREMENT_EXPORT_PAGE]);
  assert.equal(result.rows.length, PROCUREMENT_EXPORT_PAGE + 1);
});

test("vazio, grande demais e resposta inválida têm estados próprios", async () => {
  assert.deepEqual(await loadProcurementExport(async () => "[]"), { status: "empty" });
  let next = 0;
  const huge = await loadProcurementExport(async () =>
    page(Array.from({ length: PROCUREMENT_EXPORT_PAGE }, () => row(++next))),
  );
  assert.deepEqual(huge, { status: "too_large" });
  const duplicated = await loadProcurementExport(async () => page([row(1), row(1)]));
  assert.deepEqual(duplicated, { status: "unavailable" });
  const invalid = await loadProcurementExport(async () =>
    page([row(1, ',"execution_summary":{"state":"inventado"}')]),
  );
  assert.deepEqual(invalid, { status: "unavailable" });
  const failed = await loadProcurementExport(async () => {
    throw Error("HTTP 500");
  });
  assert.deepEqual(failed, { status: "unavailable" });
});

test("filtros da página e do CSV são os mesmos", () => {
  const filters = procurementFiltersFromParams({
    ano: "2025", q: " merenda ", orgao: "Saúde", pagina: "3", fornecedor: "x".repeat(201),
  });
  assert.deepEqual(filters, { query: "merenda", unit: "Saúde", fiscalYear: 2025 });
  assert.equal(procurementExportHref(filters), "/licitacoes/exportar?q=merenda&orgao=Sa%C3%BAde&ano=2025");
  assert.equal(procurementExportHref({}), "/licitacoes/exportar");
});

test("página usa os filtros compartilhados e oferece o download", async () => {
  const source = await readFile(new URL("../../apps/web/app/licitacoes/page.tsx", import.meta.url), "utf8");
  assert.match(source, /procurementFiltersFromParams\(params\)/);
  assert.match(source, /href=\{procurementExportHref\(filters\)\} download/);
  const route = await readFile(
    new URL("../../apps/web/app/licitacoes/exportar/route.ts", import.meta.url),
    "utf8",
  );
  assert.match(route, /Isso não significa que a fonte oficial não tenha contratações/);
  assert.match(route, /PROCUREMENT_EXPORT_PARAMS\.includes\(key\)/);
});
