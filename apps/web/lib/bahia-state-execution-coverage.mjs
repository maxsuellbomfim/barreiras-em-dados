const TERRITORIAL_STATUS = "territorial_key_unavailable_in_source";
const SNAPSHOT_STATUS = "source_snapshot_observed";
const METHOD = "bahia-state-execution-source-coverage/1.0.0";
const SHA256 = /^[0-9a-f]{64}$/;

function positiveCount(value) {
  return Number.isSafeInteger(value) && value > 0 ? value : null;
}

function parseRow(row) {
  if (typeof row !== "object" || row === null) return null;
  const fiscalYear = Number.isSafeInteger(row.fiscal_year) &&
      row.fiscal_year >= 2021 && row.fiscal_year <= 2100
    ? row.fiscal_year
    : null;
  const sourceAggregateCount = positiveCount(row.source_aggregate_count);
  const sourceAuthorCount = positiveCount(row.source_author_count);
  const sourceUrl = typeof row.source_url === "string" &&
      row.source_url.startsWith("https://")
    ? row.source_url
    : null;
  const sourceArtifactSha256 = typeof row.source_artifact_sha256 === "string" &&
      SHA256.test(row.source_artifact_sha256)
    ? row.source_artifact_sha256
    : null;
  const sourceCollectedAt = typeof row.source_collected_at === "string" &&
      !Number.isNaN(Date.parse(row.source_collected_at))
    ? row.source_collected_at
    : null;
  if (
    fiscalYear === null || sourceAggregateCount === null ||
    sourceAuthorCount === null || sourceAuthorCount > sourceAggregateCount ||
    !sourceUrl || !sourceArtifactSha256 || !sourceCollectedAt ||
    row.territorial_key_status !== TERRITORIAL_STATUS ||
    row.source_snapshot_status !== SNAPSHOT_STATUS ||
    row.methodology_version !== METHOD
  ) return null;
  return {
    fiscalYear,
    sourceAggregateCount,
    sourceAuthorCount,
    territorialKeyStatus: TERRITORIAL_STATUS,
    sourceSnapshotStatus: SNAPSHOT_STATUS,
    sourceUrl,
    sourceArtifactSha256,
    sourceCollectedAt,
    methodologyVersion: METHOD,
  };
}

export function parseBahiaStateExecutionCoverageRows(rows) {
  if (!Array.isArray(rows) || rows.length === 0) return null;
  const parsed = rows.map(parseRow);
  if (parsed.some((row) => row === null)) return null;
  const years = new Set();
  for (const row of parsed) {
    if (years.has(row.fiscalYear)) return null;
    years.add(row.fiscalYear);
  }
  return parsed.sort((left, right) => right.fiscalYear - left.fiscalYear);
}
