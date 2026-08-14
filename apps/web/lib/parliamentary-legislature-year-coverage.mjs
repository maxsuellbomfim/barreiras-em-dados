const SPHERES = new Set(["federal", "state"]);
const STATUSES = new Set(["observed", "not_observed"]);
const METHOD = "parliamentary-legislature-year-coverage/1.0.0";

function text(value) {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function integer(value, minimum = 0) {
  return Number.isSafeInteger(value) && value >= minimum ? value : null;
}

function parseRow(row) {
  if (typeof row !== "object" || row === null) return null;
  const sphere = text(row.sphere);
  const legislatureNumber = integer(row.legislature_number, 1);
  const fiscalYear = integer(row.fiscal_year, 1900);
  const observationStatus = text(row.observation_status);
  const contributionCount = integer(row.contribution_count);
  const authorCount = integer(row.author_count);
  const primaryEvidenceCount = integer(row.primary_evidence_count);
  if (
    !sphere || !SPHERES.has(sphere) || legislatureNumber === null ||
    fiscalYear === null || !observationStatus || !STATUSES.has(observationStatus) ||
    contributionCount === null || authorCount === null ||
    primaryEvidenceCount === null || authorCount > contributionCount ||
    primaryEvidenceCount > contributionCount ||
    (observationStatus === "observed" && contributionCount === 0) ||
    (observationStatus === "not_observed" && contributionCount !== 0) ||
    row.methodology_version !== METHOD
  ) return null;
  return {
    sphere,
    legislatureNumber,
    fiscalYear,
    observationStatus,
    contributionCount,
    authorCount,
    primaryEvidenceCount,
    methodologyVersion: METHOD,
  };
}

export function parseParliamentaryLegislatureYearCoverageRows(rows) {
  if (!Array.isArray(rows)) return null;
  const parsed = rows.map(parseRow);
  if (parsed.some((row) => row === null)) return null;
  const keys = new Set();
  for (const row of parsed) {
    const key = `${row.sphere}:${row.legislatureNumber}:${row.fiscalYear}`;
    if (keys.has(key)) return null;
    keys.add(key);
  }
  return parsed;
}
