function decimalToCents(value) {
  if (typeof value !== "string" || !/^-?\d+(?:\.\d{1,2})?$/.test(value)) {
    throw new TypeError("Valor monetário inválido no acervo CGU.");
  }
  const negative = value.startsWith("-");
  const [units, fraction = ""] = (negative ? value.slice(1) : value).split(".");
  const cents = BigInt(units) * 100n + BigInt(fraction.padEnd(2, "0"));
  return negative ? -cents : cents;
}

function centsToDecimal(value) {
  const negative = value < 0n;
  const absolute = negative ? -value : value;
  const units = absolute / 100n;
  const cents = String(absolute % 100n).padStart(2, "0");
  return `${negative ? "-" : ""}${units}.${cents}`;
}

/**
 * Resume somente o que a série territorial da CGU permite afirmar sobre um
 * autor. Cobertura de outras fontes é ignorada e ausência nunca vira R$ 0.
 */
export function buildCguAuthorCoverageSummary(
  amendments,
  coverage,
  authorKey,
  minimumCoverageYear = 2021,
) {
  if (typeof authorKey !== "string" || !authorKey.trim()) return null;
  const normalizedAuthorKey = authorKey.trim();
  const authorRows = amendments.filter(
    (amendment) => amendment.authorKey === normalizedAuthorKey,
  );
  if (authorRows.length === 0) return null;

  const foundYears = [...new Set(authorRows.map((row) => row.fiscalYear))]
    .sort((left, right) => right - left);
  const foundYearSet = new Set(foundYears);
  let committedCents = 0n;
  let effectivePaidCents = 0n;
  for (const row of authorRows) {
    committedCents += decimalToCents(row.committedAmount);
    effectivePaidCents += decimalToCents(row.effectivePaidAmount);
  }

  const cguCoverage = coverage
    .filter((row) => (
      row.sourceKey === "cgu_execution" &&
      row.fiscalYear >= minimumCoverageYear &&
      !foundYearSet.has(row.fiscalYear)
    ))
    .sort((left, right) => right.fiscalYear - left.fiscalYear);

  return {
    authorKey: normalizedAuthorKey,
    authorName: authorRows[0].authorName,
    recordCount: authorRows.length,
    foundYears,
    committedAmount: centsToDecimal(committedCents),
    effectivePaidAmount: centsToDecimal(effectivePaidCents),
    observedWithoutAuthorYears: cguCoverage
      .filter((row) => row.coverageStatus === "observed")
      .map((row) => row.fiscalYear),
    emptyMunicipalYears: cguCoverage
      .filter((row) => row.coverageStatus === "empty")
      .map((row) => row.fiscalYear),
    unresolvedYears: cguCoverage
      .filter((row) => !["observed", "empty"].includes(row.coverageStatus))
      .map((row) => row.fiscalYear),
  };
}
