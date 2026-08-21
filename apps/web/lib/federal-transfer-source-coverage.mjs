const SOURCE_KEYS = new Set([
  "cgu_execution",
  "transferegov_historical",
  "transferegov_current",
]);
const SOURCE_ORDER = new Map([
  ["cgu_execution", 0],
  ["transferegov_historical", 1],
  ["transferegov_current", 2],
]);
const STATUSES = new Set([
  "observed",
  "empty",
  "partial",
  "failed",
  "blocked",
  "unclassified",
]);
const COUNTED_STATUSES = new Set(["observed", "empty"]);
const METHODOLOGY = "federal-transfer-source-coverage/1.0.0";

function parseRow(row) {
  if (typeof row !== "object" || row === null) return null;
  const sourceKey = typeof row.source_key === "string" &&
      SOURCE_KEYS.has(row.source_key)
    ? row.source_key
    : null;
  const fiscalYear = Number.isSafeInteger(row.fiscal_year) &&
      row.fiscal_year >= 2014 && row.fiscal_year <= 2100
    ? row.fiscal_year
    : null;
  const coverageStatus = typeof row.coverage_status === "string" &&
      STATUSES.has(row.coverage_status)
    ? row.coverage_status
    : null;
  const recordCount = row.record_count === null
    ? null
    : Number.isSafeInteger(row.record_count) && row.record_count >= 0
      ? row.record_count
      : null;
  const lastAttemptedAt = typeof row.last_attempted_at === "string" &&
      !Number.isNaN(Date.parse(row.last_attempted_at))
    ? row.last_attempted_at
    : null;
  const sourceUrl = typeof row.source_url === "string" &&
      row.source_url.startsWith("https://")
    ? row.source_url
    : null;
  if (
    !sourceKey || fiscalYear === null || !coverageStatus || !sourceUrl ||
    row.methodology_version !== METHODOLOGY ||
    (coverageStatus === "observed" && (recordCount === null || recordCount < 1)) ||
    (coverageStatus === "empty" && recordCount !== 0) ||
    (!COUNTED_STATUSES.has(coverageStatus) && recordCount !== null)
  ) return null;
  return {
    sourceKey,
    fiscalYear,
    coverageStatus,
    recordCount,
    lastAttemptedAt,
    sourceUrl,
    methodologyVersion: METHODOLOGY,
  };
}

export function parseFederalTransferSourceCoverageRows(rows) {
  if (!Array.isArray(rows)) return null;
  const parsed = rows.map(parseRow);
  if (parsed.some((row) => row === null)) return null;
  const keys = new Set();
  for (const row of parsed) {
    const key = `${row.sourceKey}:${row.fiscalYear}`;
    if (keys.has(key)) return null;
    keys.add(key);
  }
  return parsed;
}

export function groupFederalTransferSourceCoverage(rows) {
  const groups = new Map();
  for (const row of rows) {
    const sources = groups.get(row.fiscalYear) ?? [];
    sources.push(row);
    groups.set(row.fiscalYear, sources);
  }
  return [...groups.entries()]
    .sort(([left], [right]) => right - left)
    .map(([fiscalYear, sources]) => ({
      fiscalYear,
      sources: sources.sort((left, right) => (
        SOURCE_ORDER.get(left.sourceKey) - SOURCE_ORDER.get(right.sourceKey)
      )),
    }));
}
