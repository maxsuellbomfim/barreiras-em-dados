const METHODOLOGY_VERSION = "bahia-state-loa-study/1.0.0";

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
    !Number.isSafeInteger(row.total_count) ||
    row.total_count < 0 ||
    row.amendment_items.length > row.total_count ||
    row.execution_items.length > row.amendment_items.length ||
    (row.total_count > 0 && row.amendment_items.length === 0) ||
    row.methodology_version !== METHODOLOGY_VERSION
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
    methodologyVersion: METHODOLOGY_VERSION,
  };
}

export function resolveStateLoaStudyPage(rawPage) {
  if (Array.isArray(rawPage) || typeof rawPage !== "string") return 1;
  if (!/^\d+$/.test(rawPage)) return 1;
  return positiveInteger(Number(rawPage)) ?? 1;
}

export function stateLoaStudyPageHref(fiscalYear, page) {
  const resolvedPage = positiveInteger(page) ?? 1;
  const query = new URLSearchParams({
    origem: "estadual",
    ano: String(fiscalYear),
  });
  if (resolvedPage > 1) query.set("estadual_pagina", String(resolvedPage));
  return `/recursos?${query.toString()}#emendas-estaduais`;
}
