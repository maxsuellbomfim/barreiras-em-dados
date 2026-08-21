const LOA_STATUSES = new Set([
  "observed",
  "empty",
  "partial",
  "failed",
  "blocked",
  "unclassified",
]);
const EXECUTION_STATUSES = new Set([
  "observed",
  "partial",
  "blocked_missing_official_key",
  "scope_not_indexed",
  "loa_unavailable",
  "unclassified",
]);
const DECIMAL = /^-?\d+(?:\.\d{1,2})?$/;
const METHODS = new Set([
  "state-amendment-source-coverage/1.0.0",
  "state-amendment-source-coverage/1.1.0",
]);

function count(value) {
  return Number.isSafeInteger(value) && value >= 0 ? value : null;
}

function decimal(value) {
  if (typeof value === "string" && DECIMAL.test(value)) return value;
  if (typeof value === "number" && Number.isFinite(value)) {
    const roundedCents = Math.round(value * 100);
    if (!Number.isSafeInteger(roundedCents)) return null;
    const normalizedValue = roundedCents / 100;
    const tolerance = Number.EPSILON * Math.max(1, Math.abs(value)) * 4;
    if (Math.abs(value - normalizedValue) > tolerance) return null;
    return normalizedValue.toFixed(2);
  }
  return null;
}

function parseRow(row) {
  if (typeof row !== "object" || row === null) return null;
  const fiscalYear = Number.isSafeInteger(row.fiscal_year) &&
      row.fiscal_year >= 2021 && row.fiscal_year <= 2100
    ? row.fiscal_year
    : null;
  const loaStatus = typeof row.loa_status === "string" &&
      LOA_STATUSES.has(row.loa_status)
    ? row.loa_status
    : null;
  const executionStatus = typeof row.execution_status === "string" &&
      EXECUTION_STATUSES.has(row.execution_status)
    ? row.execution_status
    : null;
  const amendmentCount = row.amendment_count === null
    ? null
    : count(row.amendment_count);
  const authorCount = row.author_count === null ? null : count(row.author_count);
  const authorizedAmount = row.authorized_amount === null
    ? null
    : decimal(row.authorized_amount);
  const matchedCount = row.matched_count === null ? null : count(row.matched_count);
  const ambiguousCount = row.ambiguous_count === null
    ? null
    : count(row.ambiguous_count);
  const notFoundCount = row.not_found_count === null
    ? null
    : count(row.not_found_count);
  const unavailableScopeCount = row.unavailable_scope_count === null
    ? null
    : count(row.unavailable_scope_count);
  const committedAmount = row.committed_amount === null
    ? null
    : decimal(row.committed_amount);
  const liquidatedAmount = row.liquidated_amount === null
    ? null
    : decimal(row.liquidated_amount);
  const paidAmount = row.paid_amount === null ? null : decimal(row.paid_amount);
  const lastAttemptedAt = typeof row.last_attempted_at === "string" &&
      !Number.isNaN(Date.parse(row.last_attempted_at))
    ? row.last_attempted_at
    : null;
  const sourceUrl = typeof row.source_url === "string" &&
      row.source_url.startsWith("https://")
    ? row.source_url
    : null;
  if (
    fiscalYear === null || !loaStatus || !executionStatus || !sourceUrl ||
    typeof row.methodology_version !== "string" ||
    !METHODS.has(row.methodology_version)
  ) return null;

  const loaObserved = loaStatus === "observed";
  const loaEmpty = loaStatus === "empty";
  if (
    (loaObserved && (
      amendmentCount === null || amendmentCount < 1 || authorCount === null ||
      authorCount < 1 || authorizedAmount === null
    )) ||
    (loaEmpty && (
      amendmentCount !== 0 || authorCount !== 0 || authorizedAmount !== null
    )) ||
    (!loaObserved && !loaEmpty && (
      amendmentCount !== null || authorCount !== null || authorizedAmount !== null
    ))
  ) return null;

  const executionCounts = [
    matchedCount,
    ambiguousCount,
    notFoundCount,
    unavailableScopeCount,
  ];
  const financialAmounts = [committedAmount, liquidatedAmount, paidAmount];
  if (
    executionStatus === "blocked_missing_official_key" && (
      !loaObserved || executionCounts.some((value) => value !== null) ||
      financialAmounts.some((value) => value !== null)
    )
  ) return null;
  if (
    executionStatus === "loa_unavailable" && (
      loaObserved || executionCounts.some((value) => value !== null) ||
      financialAmounts.some((value) => value !== null)
    )
  ) return null;
  if (
    executionStatus === "scope_not_indexed" && (
      !loaObserved || matchedCount !== 0 || ambiguousCount !== 0 ||
      notFoundCount !== 0 || unavailableScopeCount !== amendmentCount ||
      financialAmounts.some((value) => value !== null)
    )
  ) return null;
  if (executionStatus === "observed" || executionStatus === "partial") {
    if (!loaObserved || executionCounts.some((value) => value === null)) return null;
    if ((matchedCount ?? 0) > 0 && financialAmounts.some((value) => value === null)) {
      return null;
    }
    if ((matchedCount ?? 0) === 0 && financialAmounts.some((value) => value !== null)) {
      return null;
    }
    if (executionStatus === "observed" && (
      matchedCount !== amendmentCount || ambiguousCount !== 0 ||
      notFoundCount !== 0 || unavailableScopeCount !== 0
    )) return null;
    if (executionStatus === "partial" && (
      (ambiguousCount ?? 0) + (notFoundCount ?? 0) +
      (unavailableScopeCount ?? 0) < 1
    )) return null;
  }
  if (executionStatus === "unclassified" && (
    executionCounts.some((value) => value !== null) ||
    financialAmounts.some((value) => value !== null)
  )) return null;

  return {
    fiscalYear,
    loaStatus,
    amendmentCount,
    authorCount,
    authorizedAmount,
    executionStatus,
    matchedCount,
    ambiguousCount,
    notFoundCount,
    unavailableScopeCount,
    committedAmount,
    liquidatedAmount,
    paidAmount,
    lastAttemptedAt,
    sourceUrl,
    methodologyVersion: row.methodology_version,
  };
}

export function parseStateAmendmentSourceCoverageRows(rows) {
  if (!Array.isArray(rows)) return null;
  const parsed = rows.map(parseRow);
  if (parsed.some((row) => row === null)) return null;
  const years = new Set();
  for (const row of parsed) {
    if (years.has(row.fiscalYear)) return null;
    years.add(row.fiscalYear);
  }
  return parsed.sort((left, right) => right.fiscalYear - left.fiscalYear);
}
