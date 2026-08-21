/**
 * Resolve filtros públicos apenas contra valores que realmente existem no
 * lote validado. Entrada repetida ou desconhecida volta ao acervo completo;
 * assim, uma URL manipulada nunca é apresentada como ausência oficial.
 *
 * @param {string | readonly string[] | undefined} requestedAuthor
 * @param {string | readonly string[] | undefined} requestedYear
 * @param {readonly { authorKey: string, fiscalYear: number }[]} amendments
 */
export function resolveCguExecutionFilters(
  requestedAuthor,
  requestedYear,
  amendments,
) {
  const availableAuthors = new Set(amendments.map((row) => row.authorKey));
  const availableYears = new Set(amendments.map((row) => row.fiscalYear));
  const authorKey = typeof requestedAuthor === "string" &&
      availableAuthors.has(requestedAuthor)
    ? requestedAuthor
    : null;
  const parsedYear = typeof requestedYear === "string" && /^\d{4}$/.test(requestedYear)
    ? Number(requestedYear)
    : null;
  const fiscalYear = parsedYear !== null && availableYears.has(parsedYear)
    ? parsedYear
    : null;
  return { authorKey, fiscalYear };
}

/**
 * @template {{ authorKey: string, fiscalYear: number }} T
 * @param {readonly T[]} amendments
 * @param {{ authorKey: string | null, fiscalYear: number | null }} filters
 * @returns {readonly T[]}
 */
export function filterCguExecutionAmendments(amendments, filters) {
  return amendments.filter((row) => (
    (filters.authorKey === null || row.authorKey === filters.authorKey) &&
    (filters.fiscalYear === null || row.fiscalYear === filters.fiscalYear)
  ));
}

/**
 * @param {number} count
 */
export function cguExecutionResultCountCopy(count) {
  return count === 1
    ? "1 linha oficial encontrada com estes filtros."
    : `${count.toLocaleString("pt-BR")} linhas oficiais encontradas com estes filtros.`;
}
