// CSV das contratações do PNCP (pncp-procurements-csv/1.0.0). Valores saem
// com o decimal exato que o banco enviou: o texto JSON é lido com `reviver`
// e `context.source`, sem passar por ponto flutuante.

export const PROCUREMENT_CSV_VERSION = "pncp-procurements-csv/1.0.0";
export const PROCUREMENT_EXPORT_LIMIT = 2000;
export const PROCUREMENT_EXPORT_PAGE = 100;
const MAX_BYTES = 4_000_000;

const MONEY_KEYS = new Set(["valor_estimado", "valor_homologado"]);
const DECIMAL = /^-?\d{1,15}(?:\.\d{1,6})?$/;
const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;
const CONTROL = /^[0-9]{14}-[0-9]-[0-9]{1,12}\/[0-9]{4}$/;

const COVERAGE =
  "Contratações publicadas no PNCP para a Prefeitura e fundos de Barreiras, " +
  "como coletadas pela plataforma; a ausência de uma contratação neste " +
  "arquivo não prova que ela não exista na fonte oficial. Valores estimado e " +
  "homologado não são somados nem representam pagamento.";

const LINK_STATES = {
  linked: (summary) => `contratos vinculados: ${summary.contracts_count}`,
  no_linked_execution: () =>
    "sem vínculo publicado (não prova ausência na fonte)",
  not_normalized: () => "vínculos em preparação",
  not_available: () => "resumo de vínculos indisponível",
};

/** Lê o JSON da RPC guardando os valores em dinheiro como texto exato. */
export function parseExactProcurementRows(text) {
  return JSON.parse(text, (key, value, context) => {
    if (MONEY_KEYS.has(key) && typeof value === "number") {
      const source = context?.source;
      if (typeof source !== "string" || !DECIMAL.test(source)) {
        throw Error("Decimal source unavailable");
      }
      return source;
    }
    return value;
  });
}

function validRow(row) {
  return (
    row !== null &&
    typeof row === "object" &&
    typeof row.control_number === "string" &&
    CONTROL.test(row.control_number) &&
    Number.isSafeInteger(row.ano) &&
    Number.isSafeInteger(row.sequencial) &&
    typeof row.objeto === "string" &&
    row.objeto.trim().length > 0 &&
    (row.data_publicacao === null || ISO_DATE.test(row.data_publicacao)) &&
    (row.valor_estimado === null || DECIMAL.test(row.valor_estimado)) &&
    (row.valor_homologado === null || DECIMAL.test(row.valor_homologado)) &&
    Array.isArray(row.resultados) &&
    Array.isArray(row.itens) &&
    typeof row.methodology_version === "string" &&
    row.execution_summary !== null &&
    typeof row.execution_summary === "object" &&
    Object.hasOwn(LINK_STATES, row.execution_summary.state)
  );
}

/**
 * Busca todas as páginas do filtro. `fetchPageText(offset)` devolve o texto
 * JSON de uma página de PROCUREMENT_EXPORT_PAGE linhas.
 */
export async function loadProcurementExport(fetchPageText) {
  const rows = [];
  const seen = new Set();
  for (let offset = 0; ; offset += PROCUREMENT_EXPORT_PAGE) {
    let page;
    try {
      page = parseExactProcurementRows(await fetchPageText(offset));
    } catch {
      return { status: "unavailable" };
    }
    if (!Array.isArray(page) || page.length > PROCUREMENT_EXPORT_PAGE) {
      return { status: "unavailable" };
    }
    for (const row of page) {
      if (!validRow(row) || seen.has(row.control_number)) {
        return { status: "unavailable" };
      }
      seen.add(row.control_number);
      rows.push(row);
    }
    if (rows.length > PROCUREMENT_EXPORT_LIMIT) return { status: "too_large" };
    if (page.length < PROCUREMENT_EXPORT_PAGE) break;
  }
  return rows.length === 0 ? { status: "empty" } : { status: "ready", rows };
}

const quote = (value) => `"${value.replaceAll('"', '""')}"`;

function textCell(value) {
  // Aspas delimitam, mas não impedem a planilha de executar fórmula nem de
  // converter identificador numérico.
  const text = value ?? "";
  const guarded =
    /^[\s﻿]*[=+\-@＝＋－＠]/u.test(text) ||
    /^\s*\d+(?:[.,]\d+)?(?:[eE][+-]?\d+)?\s*$/.test(text)
      ? `'${text}`
      : text;
  return quote(guarded);
}

const moneyCell = (value) => quote(value === null ? "" : value.replace(".", ","));

function suppliers(resultados) {
  const names = [];
  for (const result of resultados) {
    const name = typeof result?.fornecedor === "string" ? result.fornecedor.trim() : "";
    // Só o nome, como na página: documento de pessoa física nunca sai.
    if (name && !names.includes(name)) names.push(name);
  }
  return names.join(" | ");
}

export function serializeProcurementCsv(result, sourceUrl, exportedAt = new Date().toISOString()) {
  if (
    result.status !== "ready" ||
    result.rows.length === 0 ||
    result.rows.length > PROCUREMENT_EXPORT_LIMIT ||
    !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/.test(exportedAt)
  ) {
    throw Error("Invalid procurement export");
  }
  const header = [
    "numero_controle_pncp", "ano_compra", "sequencial", "data_publicacao",
    "modalidade", "situacao", "orgao_unidade", "objeto",
    "valor_estimado_brl", "valor_homologado_brl", "fornecedores_homologados",
    "itens", "vinculos_publicados", "link_pncp", "metodologia",
    "formato", "cobertura", "extraido_em_utc",
  ];
  const lines = [header.map(quote).join(";")];
  for (const row of result.rows) {
    lines.push([
      textCell(row.control_number),
      quote(String(row.ano)),
      quote(String(row.sequencial)),
      quote(row.data_publicacao ?? ""),
      textCell(row.modalidade),
      textCell(row.situacao),
      textCell(row.unidade),
      textCell(row.objeto),
      moneyCell(row.valor_estimado),
      moneyCell(row.valor_homologado),
      textCell(suppliers(row.resultados)),
      quote(String(row.itens.length)),
      quote(LINK_STATES[row.execution_summary.state](row.execution_summary)),
      quote(sourceUrl(row.control_number) ?? ""),
      quote(row.methodology_version),
      quote(PROCUREMENT_CSV_VERSION),
      quote(COVERAGE),
      quote(exportedAt),
    ].join(";"));
  }
  const csv = "﻿" + lines.join("\r\n") + "\r\n";
  if (new TextEncoder().encode(csv).byteLength > MAX_BYTES) {
    throw Error("Procurement export size exceeded");
  }
  return csv;
}
