/**
 * @typedef {{
 *   fiscalYear: number,
 *   coverageStatus: string,
 *   publishedAmendmentCount: number | null,
 * }} TransferCoverageYear
 */

/**
 * Resolve o recorte anual sem aceitar anos que a matriz de cobertura ainda
 * não conhece. Um ano comprovadamente vazio continua selecionável; na abertura
 * da página, a prioridade é o exercício mais recente com emendas publicadas.
 *
 * @param {string | readonly string[] | undefined} requestedYear
 * @param {readonly TransferCoverageYear[] | null} coverage
 * @returns {number | null}
 */
export function resolveCurrentFederalTransferYear(requestedYear, coverage) {
  if (!coverage || coverage.length === 0) return null;

  const knownYears = [...new Set(
    coverage
      .map((row) => row.fiscalYear)
      .filter((year) => Number.isInteger(year)),
  )].sort((left, right) => right - left);
  if (knownYears.length === 0) return null;

  const requested = typeof requestedYear === "string" && /^\d{4}$/.test(requestedYear)
    ? Number(requestedYear)
    : null;
  if (requested !== null && knownYears.includes(requested)) return requested;

  const yearsWithPublishedAmendments = coverage
    .filter((row) => (
      row.coverageStatus === "complete" &&
      row.publishedAmendmentCount !== null &&
      row.publishedAmendmentCount > 0
    ))
    .map((row) => row.fiscalYear)
    .sort((left, right) => right - left);

  return yearsWithPublishedAmendments[0] ?? knownYears[0] ?? null;
}

/**
 * @param {"person" | "collective"} authorScope
 * @param {number | null} fiscalYear
 */
export function buildCurrentTransferRankingRequest(authorScope, fiscalYear) {
  if (authorScope !== "person" && authorScope !== "collective") {
    throw new TypeError("invalid parliamentary transfer author scope");
  }
  if (fiscalYear !== null && !Number.isInteger(fiscalYear)) {
    throw new TypeError("invalid parliamentary transfer fiscal year");
  }
  return {
    author_scope: authorScope,
    fiscal_year_filter: fiscalYear,
    page_size: 50,
  };
}

/**
 * @param {number} fiscalYear
 */
export function buildCurrentTransfersRequest(fiscalYear) {
  if (!Number.isInteger(fiscalYear)) {
    throw new TypeError("invalid parliamentary transfer fiscal year");
  }
  return {
    fiscal_year_filter: fiscalYear,
    author_kind_filter: null,
    page_size: 200,
  };
}
