const SHA256 = /^[0-9a-f]{64}$/;
const DECIMAL = /^-?\d+(?:\.\d{1,2})?$/;

export const SICONFI_ANNUAL_METRICS = Object.freeze([
  "gross_revenue_realized",
  "fundeb_deductions",
  "expense_committed",
  "expense_liquidated",
  "expense_paid",
  "nonprocessed_payables_registered",
  "processed_payables_registered",
]);

const METRIC_SET = new Set(SICONFI_ANNUAL_METRICS);

function text(value) {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function parseRow(row) {
  const totalId = text(row.total_id);
  const metricKey = text(row.metric_key);
  const amount = text(row.amount);
  const currency = text(row.currency);
  const officialAnnex = text(row.official_annex);
  const officialLabel = text(row.official_label);
  const officialColumnLabel = text(row.official_column_label);
  const officialAccountCode = text(row.official_account_code);
  const officialAccountLabel = text(row.official_account_label);
  const sourceUrl = text(row.source_url);
  const sourceArtifactSha256 = text(row.source_artifact_sha256);
  const sourceRetrievedAt = text(row.source_retrieved_at);
  const methodologyVersion = text(row.methodology_version);
  if (
    !totalId ||
    !Number.isSafeInteger(row.fiscal_year) ||
    row.fiscal_year < 1988 ||
    row.fiscal_year > 2200 ||
    !metricKey ||
    !METRIC_SET.has(metricKey) ||
    !amount ||
    !DECIMAL.test(amount) ||
    currency !== "BRL" ||
    !officialAnnex ||
    !officialLabel ||
    !officialColumnLabel ||
    !officialAccountCode ||
    !officialAccountLabel ||
    !sourceUrl?.startsWith("https://") ||
    !sourceArtifactSha256 ||
    !SHA256.test(sourceArtifactSha256) ||
    !sourceRetrievedAt ||
    Number.isNaN(Date.parse(sourceRetrievedAt)) ||
    methodologyVersion !== "siconfi-annual-totals/1.0.0"
  ) {
    return null;
  }
  return {
    totalId,
    fiscalYear: row.fiscal_year,
    metricKey,
    amount,
    currency,
    officialAnnex,
    officialLabel,
    officialColumnLabel,
    officialAccountCode,
    officialAccountLabel,
    sourceUrl,
    sourceArtifactSha256,
    sourceRetrievedAt,
    methodologyVersion,
  };
}

export function parseSiconfiAnnualRows(payload) {
  if (!Array.isArray(payload)) return null;
  const years = new Map();
  for (const rawRow of payload) {
    if (typeof rawRow !== "object" || rawRow === null) return null;
    const row = parseRow(rawRow);
    if (!row) return null;
    const metrics = years.get(row.fiscalYear) ?? new Map();
    if (metrics.has(row.metricKey)) return null;
    metrics.set(row.metricKey, row);
    years.set(row.fiscalYear, metrics);
  }
  const completeYears = [];
  for (const [fiscalYear, metrics] of years) {
    if (metrics.size !== SICONFI_ANNUAL_METRICS.length) return null;
    const orderedMetrics = SICONFI_ANNUAL_METRICS.map((metric) => metrics.get(metric));
    if (orderedMetrics.some((metric) => !metric)) return null;
    const sourceHashes = new Set(
      orderedMetrics.map((metric) => metric.sourceArtifactSha256),
    );
    if (sourceHashes.size !== 1) return null;
    completeYears.push({ fiscalYear, metrics: orderedMetrics });
  }
  return completeYears.sort((left, right) => right.fiscalYear - left.fiscalYear);
}
