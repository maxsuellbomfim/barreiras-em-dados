const STATUSES = new Set(["published", "not_found", "in_progress"]);

export function buildDcaAnnualCoverage(
  years,
  { yearFrom = 2021, currentYear = new Date().getFullYear() } = {},
) {
  if (
    !Array.isArray(years) ||
    !Number.isInteger(yearFrom) ||
    !Number.isInteger(currentYear) ||
    yearFrom < 2000 ||
    currentYear < yearFrom
  ) {
    return null;
  }

  const published = new Map();
  for (const item of years) {
    if (
      !item ||
      !Number.isInteger(item.fiscalYear) ||
      item.fiscalYear < yearFrom ||
      item.fiscalYear > currentYear ||
      !Array.isArray(item.metrics) ||
      item.metrics.length !== 7 ||
      published.has(item.fiscalYear)
    ) {
      return null;
    }
    const sourceUrl = item.metrics[0]?.sourceUrl;
    if (typeof sourceUrl !== "string" || !sourceUrl.startsWith("https://")) {
      return null;
    }
    published.set(item.fiscalYear, sourceUrl);
  }

  const coverage = [];
  for (let fiscalYear = currentYear; fiscalYear >= yearFrom; fiscalYear -= 1) {
    const sourceUrl = published.get(fiscalYear) ?? null;
    coverage.push({
      fiscalYear,
      status: sourceUrl
        ? "published"
        : fiscalYear === currentYear
          ? "in_progress"
          : "not_found",
      sourceUrl,
    });
  }
  return coverage;
}

export function dcaAnnualCoverageStatusLabel(status) {
  if (!STATUSES.has(status)) throw new Error("Estado de cobertura DCA desconhecido.");
  if (status === "published") return "DCA publicada";
  if (status === "not_found") return "Não localizada na consulta";
  return "Exercício em andamento";
}
