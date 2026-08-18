const DECIMAL = /^-?\d+(?:\.\d{1,2})?$/;
const SHA256 = /^[0-9a-f]{64}$/;
const OFFICIAL_CODE = /^\d{12}$/;
const AUTHOR_KINDS = new Set([
  "person",
  "commission",
  "bench",
  "collective",
  "other",
]);
const LINK_STATUSES = new Set([
  "code_unavailable",
  "not_found_in_transferegov",
  "matched_transferegov_unique",
  "conflict_non_unique_transferegov",
]);
const EXECUTION_METHODOLOGY = "cgu-federal-amendment-executions/1.0.0";
const RANKING_METHODOLOGY = "cgu-federal-amendment-ranking/1.0.0";

function requiredText(value) {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function integer(value, minimum) {
  return Number.isInteger(value) && value >= minimum ? value : null;
}

function decimal(value) {
  return typeof value === "string" && DECIMAL.test(value) ? value : null;
}

function decimalCents(value) {
  const negative = value.startsWith("-");
  const [units, fraction = ""] = (negative ? value.slice(1) : value).split(".");
  const cents = BigInt(units) * 100n + BigInt(fraction.padEnd(2, "0"));
  return negative ? -cents : cents;
}

function parseExecutionRow(row) {
  if (typeof row !== "object" || row === null) return null;
  const fiscalYear = integer(row.fiscal_year, 2000);
  const amendmentCode = requiredText(row.amendment_code);
  const amendmentNumber = requiredText(row.amendment_number);
  const amendmentType = requiredText(row.amendment_type);
  const authorKind = requiredText(row.author_kind);
  const authorCode = requiredText(row.author_code);
  const authorKey = requiredText(row.author_key);
  const authorName = requiredText(row.author_name);
  const locality = requiredText(row.locality);
  const functionName = requiredText(row.function_name);
  const programName = requiredText(row.program_name);
  const actionName = requiredText(row.action_name);
  const committedAmount = decimal(row.committed_amount);
  const liquidatedAmount = decimal(row.liquidated_amount);
  const paidAmount = decimal(row.paid_amount);
  const outstandingRegisteredAmount = decimal(
    row.outstanding_registered_amount,
  );
  const outstandingCancelledAmount = decimal(row.outstanding_cancelled_amount);
  const outstandingPaidAmount = decimal(row.outstanding_paid_amount);
  const effectivePaidAmount = decimal(row.effective_paid_amount);
  const linkStatus = requiredText(row.transferegov_link_status);
  const reconciliationKey = row.transferegov_reconciliation_key ?? null;
  const sourceRowNumber = integer(row.source_row_number, 1);
  const sourceUrl = requiredText(row.source_url);
  const artifactSha256 = requiredText(row.artifact_sha256);
  const collectedAt = requiredText(row.collected_at);
  if (
    fiscalYear === null || !amendmentCode || !amendmentNumber ||
    !amendmentType || !authorKind || !AUTHOR_KINDS.has(authorKind) ||
    !authorCode || !authorKey || !authorName || !locality || !functionName ||
    !programName || !actionName || !committedAmount || !liquidatedAmount ||
    !paidAmount || !outstandingRegisteredAmount ||
    !outstandingCancelledAmount || !outstandingPaidAmount ||
    !effectivePaidAmount ||
    typeof row.has_official_code !== "boolean" ||
    row.has_official_code !== OFFICIAL_CODE.test(amendmentCode) ||
    typeof row.author_identified !== "boolean" ||
    !linkStatus || !LINK_STATUSES.has(linkStatus) ||
    (linkStatus === "code_unavailable") === row.has_official_code ||
    (linkStatus === "matched_transferegov_unique"
      ? requiredText(reconciliationKey) === null
      : reconciliationKey !== null) ||
    sourceRowNumber === null || !sourceUrl?.startsWith("https://") ||
    !artifactSha256 || !SHA256.test(artifactSha256) ||
    !collectedAt || !Number.isFinite(Date.parse(collectedAt)) ||
    row.methodology_version !== EXECUTION_METHODOLOGY
  ) return null;
  if (
    decimalCents(effectivePaidAmount) !==
      decimalCents(paidAmount) + decimalCents(outstandingPaidAmount)
  ) {
    return null;
  }
  return {
    fiscalYear,
    amendmentCode,
    hasOfficialCode: row.has_official_code,
    amendmentNumber,
    amendmentType,
    authorKind,
    authorCode,
    authorKey,
    authorName,
    authorIdentified: row.author_identified,
    locality,
    functionName,
    programName,
    actionName,
    budgetPlanName: requiredText(row.budget_plan_name),
    committedAmount,
    liquidatedAmount,
    paidAmount,
    outstandingRegisteredAmount,
    outstandingCancelledAmount,
    outstandingPaidAmount,
    effectivePaidAmount,
    transferegovLinkStatus: linkStatus,
    transferegovReconciliationKey: requiredText(reconciliationKey),
    sourceRowNumber,
    sourceUrl,
    artifactSha256,
    collectedAt,
    methodologyVersion: EXECUTION_METHODOLOGY,
  };
}

export function parseCguFederalAmendmentRows(rows) {
  if (!Array.isArray(rows)) return null;
  const parsed = rows.map(parseExecutionRow);
  return parsed.some((row) => row === null) ? null : parsed;
}

function parseRankingRow(row, scope, expectedPosition) {
  if (typeof row !== "object" || row === null) return null;
  const authorKind = requiredText(row.author_kind);
  const authorKey = requiredText(row.author_key);
  const authorName = requiredText(row.author_name);
  const authorCode = requiredText(row.author_code);
  const amendmentCount = integer(row.amendment_count, 1);
  const committedAmount = decimal(row.committed_amount);
  const effectivePaidAmount = decimal(row.effective_paid_amount);
  const firstYear = integer(row.first_year, 2000);
  const lastYear = integer(row.last_year, 2000);
  const scopeMatchesKind = scope === "person"
    ? authorKind === "person"
    : authorKind === "commission" || authorKind === "bench" ||
      authorKind === "collective";
  if (
    row.rank_position !== expectedPosition || !authorKind || !authorKey ||
    !authorName || !authorCode || !scopeMatchesKind ||
    amendmentCount === null || !committedAmount || !effectivePaidAmount ||
    firstYear === null || lastYear === null || firstYear > lastYear ||
    row.ranking_amount_stage !== "committed" ||
    row.methodology_version !== RANKING_METHODOLOGY
  ) return null;
  return {
    rankPosition: expectedPosition,
    authorKind,
    authorKey,
    authorName,
    authorCode,
    amendmentCount,
    committedAmount,
    effectivePaidAmount,
    firstYear,
    lastYear,
    rankingAmountStage: "committed",
    methodologyVersion: RANKING_METHODOLOGY,
  };
}

export function parseCguFederalAmendmentRankingRows(rows, scope) {
  if (!Array.isArray(rows)) return null;
  if (scope !== "person" && scope !== "collective") return null;
  const parsed = rows.map((row, index) => parseRankingRow(row, scope, index + 1));
  return parsed.some((row) => row === null) ? null : parsed;
}
