const DECIMAL = /^-?\d+(?:\.\d{1,2})?$/;
const SHA256 = /^[0-9a-f]{64}$/;
const STATUSES = new Set([
  "execution_confirmed",
  "ambiguous_official_key",
  "not_found_in_execution_source",
  "official_link_key_unavailable",
  "scope_not_available",
]);

function requiredText(value) {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function optionalText(value) {
  return value === null || value === undefined ? null : requiredText(value);
}

function integer(value, minimum = 0) {
  return Number.isInteger(value) && value >= minimum ? value : null;
}

function decimal(value) {
  if (typeof value === "number" && Number.isFinite(value)) value = String(value);
  return typeof value === "string" && DECIMAL.test(value) ? value : null;
}

function parseExecutionRow(row) {
  if (typeof row !== "object" || row === null) return null;
  const fiscalYear = integer(row.fiscal_year, 2022);
  const amendmentNumber = requiredText(row.amendment_number);
  const authorKey = requiredText(row.author_key);
  const authorName = requiredText(row.author_name);
  const authorizedAmount = decimal(row.authorized_amount);
  const officialDescription = requiredText(row.official_description);
  const pageNumber = integer(row.page_number, 1);
  const loaEvidenceText = requiredText(row.loa_evidence_text);
  const loaSourceUrl = requiredText(row.loa_source_url);
  const loaSourceArtifactSha256 = requiredText(row.loa_source_artifact_sha256);
  const loaEvidenceSha256 = requiredText(row.loa_evidence_sha256);
  const executionStatus = requiredText(row.execution_status);
  const loaScopeOccurrences = integer(row.loa_scope_occurrences);
  const executionOccurrences = integer(row.execution_occurrences);
  if (
    fiscalYear === null || !amendmentNumber || !authorKey || !authorName ||
    !authorizedAmount || !officialDescription || pageNumber === null ||
    !loaEvidenceText || !loaSourceUrl?.startsWith("https://") ||
    !loaSourceArtifactSha256 || !SHA256.test(loaSourceArtifactSha256) ||
    !loaEvidenceSha256 || !SHA256.test(loaEvidenceSha256) ||
    !executionStatus || !STATUSES.has(executionStatus) ||
    loaScopeOccurrences === null || executionOccurrences === null ||
    row.methodology_version !== "bahia-state-loa-public-execution/1.1.0"
  ) return null;

  const committedAmount = row.committed_amount === null
    ? null
    : decimal(row.committed_amount);
  const liquidatedAmount = row.liquidated_amount === null
    ? null
    : decimal(row.liquidated_amount);
  const paidAmount = row.paid_amount === null ? null : decimal(row.paid_amount);
  const executionSourceUrl = optionalText(row.execution_source_url);
  const executionSourceArtifactSha256 = optionalText(
    row.execution_source_artifact_sha256,
  );
  const executionEvidenceSha256 = optionalText(row.execution_evidence_sha256);
  const executionSourceCollectedAt = optionalText(
    row.execution_source_collected_at,
  );
  const isConfirmed = executionStatus === "execution_confirmed";
  const completeExecution = committedAmount !== null && liquidatedAmount !== null &&
    paidAmount !== null && executionSourceUrl?.startsWith("https://") &&
    executionSourceArtifactSha256 !== null &&
    SHA256.test(executionSourceArtifactSha256) &&
    executionEvidenceSha256 !== null && SHA256.test(executionEvidenceSha256) &&
    executionSourceCollectedAt !== null &&
    Number.isFinite(Date.parse(executionSourceCollectedAt));
  const blockedExecutionIsEmpty = committedAmount === null &&
    liquidatedAmount === null && paidAmount === null &&
    executionSourceUrl === null && executionSourceArtifactSha256 === null &&
    executionEvidenceSha256 === null && executionSourceCollectedAt === null;
  if ((isConfirmed && !completeExecution) || (!isConfirmed && !blockedExecutionIsEmpty)) {
    return null;
  }

  return {
    fiscalYear,
    amendmentNumber,
    authorExternalCode: optionalText(row.author_external_code),
    authorKey,
    authorName,
    authorizedAmount,
    officialDescription,
    pageNumber,
    loaEvidenceText,
    loaSourceUrl,
    loaSourceArtifactSha256,
    loaEvidenceSha256,
    executionStatus,
    loaScopeOccurrences,
    executionOccurrences,
    committedAmount,
    liquidatedAmount,
    paidAmount,
    executionSourceUrl,
    executionSourceArtifactSha256,
    executionEvidenceSha256,
    executionSourceCollectedAt,
    methodologyVersion: "bahia-state-loa-public-execution/1.1.0",
  };
}

export function parseStateLoaExecutionRows(rows) {
  if (!Array.isArray(rows)) return null;
  const parsed = rows.map(parseExecutionRow);
  return parsed.some((row) => row === null) ? null : parsed;
}

export function parseStateLoaExecutionSummary(rows) {
  if (!Array.isArray(rows) || rows.length !== 1) return null;
  const row = rows[0];
  if (typeof row !== "object" || row === null) return null;
  const fiscalYear = integer(row.fiscal_year, 2022);
  const totalAmendmentCount = integer(row.total_amendment_count);
  const matchedAmendmentCount = integer(row.matched_amendment_count);
  const ambiguousAmendmentCount = integer(row.ambiguous_amendment_count);
  const notFoundAmendmentCount = integer(row.not_found_amendment_count);
  const unavailableScopeCount = integer(row.unavailable_scope_count);
  const authorizedTotal = decimal(row.authorized_total);
  const matchedAuthorizedTotal = row.matched_authorized_total === null
    ? null
    : decimal(row.matched_authorized_total);
  const committedTotal = row.committed_total === null
    ? null
    : decimal(row.committed_total);
  const liquidatedTotal = row.liquidated_total === null
    ? null
    : decimal(row.liquidated_total);
  const paidTotal = row.paid_total === null ? null : decimal(row.paid_total);
  if (
    fiscalYear === null || totalAmendmentCount === null ||
    matchedAmendmentCount === null || ambiguousAmendmentCount === null ||
    notFoundAmendmentCount === null || unavailableScopeCount === null ||
    !authorizedTotal ||
    matchedAmendmentCount + ambiguousAmendmentCount + notFoundAmendmentCount +
      unavailableScopeCount !== totalAmendmentCount ||
    (matchedAmendmentCount > 0 && (
      matchedAuthorizedTotal === null || committedTotal === null ||
      liquidatedTotal === null || paidTotal === null
    )) ||
    (matchedAmendmentCount === 0 && (
      matchedAuthorizedTotal !== null || committedTotal !== null ||
      liquidatedTotal !== null || paidTotal !== null
    )) ||
    row.methodology_version !==
      "bahia-state-loa-public-execution-summary/1.0.0"
  ) return null;
  return {
    fiscalYear,
    totalAmendmentCount,
    matchedAmendmentCount,
    ambiguousAmendmentCount,
    notFoundAmendmentCount,
    unavailableScopeCount,
    authorizedTotal,
    matchedAuthorizedTotal,
    committedTotal,
    liquidatedTotal,
    paidTotal,
    methodologyVersion: "bahia-state-loa-public-execution-summary/1.0.0",
  };
}
