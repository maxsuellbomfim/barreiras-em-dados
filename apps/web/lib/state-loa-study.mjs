const METHODOLOGY_VERSION = "bahia-state-loa-study/1.1.0";
const EXECUTION_STATUSES = new Set([
  "execution_confirmed",
  "ambiguous_official_key",
  "not_found_in_execution_source",
  "official_link_key_unavailable",
  "scope_not_available",
]);

function positiveInteger(value) {
  return Number.isSafeInteger(value) && value > 0 ? value : null;
}

export function parseStateLoaStudyRows(rows) {
  if (!Array.isArray(rows) || rows.length !== 1) return null;
  const row = rows[0];
  if (typeof row !== "object" || row === null) return null;
  if (
    !Array.isArray(row.amendment_items) ||
    !Array.isArray(row.execution_items) ||
    !Array.isArray(row.available_authors) ||
    !Number.isSafeInteger(row.total_count) ||
    row.total_count < 0 ||
    !Number.isSafeInteger(row.catalog_count) ||
    row.catalog_count < row.total_count ||
    row.amendment_items.length > row.total_count ||
    row.execution_items.length > row.amendment_items.length ||
    (row.total_count > 0 && row.amendment_items.length === 0) ||
    row.methodology_version !== METHODOLOGY_VERSION
  ) return null;
  const availableAuthors = row.available_authors.map((author) => {
    if (typeof author !== "object" || author === null) return null;
    const authorKey = typeof author.author_key === "string"
      ? author.author_key.trim()
      : "";
    const authorName = typeof author.author_name === "string"
      ? author.author_name.trim()
      : "";
    return authorKey && authorName ? { authorKey, authorName } : null;
  });
  if (
    availableAuthors.some((author) => author === null) ||
    new Set(availableAuthors.map((author) => author.authorKey)).size !==
      availableAuthors.length
  ) return null;
  const amendmentEvidence = new Set(row.amendment_items.map((item) => (
    typeof item === "object" && item !== null &&
      typeof item.evidence_sha256 === "string"
      ? item.evidence_sha256
      : null
  )));
  if (
    amendmentEvidence.has(null) ||
    amendmentEvidence.size !== row.amendment_items.length ||
    row.execution_items.some((item) => (
      typeof item !== "object" || item === null ||
      typeof item.loa_evidence_sha256 !== "string" ||
      !amendmentEvidence.has(item.loa_evidence_sha256)
    ))
  ) return null;
  return {
    amendmentRows: row.amendment_items,
    executionRows: row.execution_items,
    totalCount: row.total_count,
    catalogCount: row.catalog_count,
    availableAuthors,
    methodologyVersion: METHODOLOGY_VERSION,
  };
}

function singleSearchParam(value) {
  return typeof value === "string" ? value.trim() : null;
}

export function resolveStateLoaStudyFilters(params) {
  const authorKey = singleSearchParam(params?.estadual_autor);
  const executionStatus = singleSearchParam(params?.estadual_situacao);
  const query = singleSearchParam(params?.estadual_q);
  return {
    page: resolveStateLoaStudyPage(params?.estadual_pagina),
    authorKey: authorKey && authorKey.length <= 200 ? authorKey : null,
    executionStatus: EXECUTION_STATUSES.has(executionStatus)
      ? executionStatus
      : null,
    query: query && query.length <= 100 ? query : null,
  };
}

export function resolveStateLoaStudyPage(rawPage) {
  if (Array.isArray(rawPage) || typeof rawPage !== "string") return 1;
  if (!/^\d+$/.test(rawPage)) return 1;
  return positiveInteger(Number(rawPage)) ?? 1;
}

export function stateLoaStudyPageHref(fiscalYear, page, filters = {}) {
  const resolvedPage = positiveInteger(page) ?? 1;
  const query = new URLSearchParams({
    origem: "estadual",
    ano: String(fiscalYear),
  });
  if (filters.authorKey) query.set("estadual_autor", filters.authorKey);
  if (filters.executionStatus) {
    query.set("estadual_situacao", filters.executionStatus);
  }
  if (filters.query) query.set("estadual_q", filters.query);
  if (resolvedPage > 1) query.set("estadual_pagina", String(resolvedPage));
  return `/recursos?${query.toString()}#emendas-estaduais`;
}
