// Filtros públicos de /licitacoes, lidos igual pela página e pelo CSV.

function cleanFilter(value, maxLength) {
  const normalized = typeof value === "string" ? value.trim() : "";
  return normalized && normalized.length <= maxLength ? normalized : undefined;
}

function parseYear(value) {
  if (typeof value !== "string" || !/^\d{4}$/.test(value)) return undefined;
  const year = Number(value);
  return year >= 1900 && year <= 2200 ? year : undefined;
}

// Parâmetro da URL → chave do filtro da RPC, com o limite de tamanho.
const TEXT_FILTERS = [
  ["fornecedor", "supplierKey", 200],
  ["q", "query", 120],
  ["modalidade", "modality", 120],
  ["situacao", "status", 120],
  ["orgao", "unit", 160],
];

export function procurementFiltersFromParams(params) {
  const filters = {};
  for (const [param, key, max] of TEXT_FILTERS) {
    const value = cleanFilter(params[param], max);
    if (value !== undefined) filters[key] = value;
  }
  const year = parseYear(params.ano);
  if (year !== undefined) filters.fiscalYear = year;
  return filters;
}

export function procurementExportHref(filters) {
  const query = new URLSearchParams();
  for (const [param, key] of TEXT_FILTERS) {
    if (filters[key] !== undefined) query.set(param, filters[key]);
  }
  if (filters.fiscalYear !== undefined) query.set("ano", String(filters.fiscalYear));
  const text = query.toString();
  return "/licitacoes/exportar" + (text ? `?${text}` : "");
}

export const PROCUREMENT_EXPORT_PARAMS = Object.freeze([
  ...TEXT_FILTERS.map(([param]) => param),
  "ano",
]);
