const DECIMAL = /^-?\d+(?:\.\d{1,2})?$/;
const SHA256 = /^[0-9a-f]{64}$/;
const METHODOLOGY_VERSION = "bahia-state-loa-execution-group/1.0.0";

function requiredText(value) {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function integer(value, minimum = 0) {
  return Number.isInteger(value) && value >= minimum ? value : null;
}

function decimal(value) {
  if (typeof value === "number" && Number.isFinite(value)) value = String(value);
  return typeof value === "string" && DECIMAL.test(value) ? value : null;
}

function parseGroup(row) {
  if (typeof row !== "object" || row === null) return null;
  const fiscalYear = integer(row.fiscal_year, 2022);
  const authorExternalCode = requiredText(row.author_external_code);
  const authorKey = requiredText(row.author_key);
  const authorName = requiredText(row.author_name);
  const agencyCode = requiredText(row.agency_code);
  const budgetUnitCode = requiredText(row.budget_unit_code);
  const actionCode = requiredText(row.action_code);
  const amendmentCount = integer(row.amendment_count, 2);
  const amendmentNumbers = Array.isArray(row.amendment_numbers)
    ? row.amendment_numbers.map(requiredText)
    : null;
  const authorizedTotal = decimal(row.authorized_total);
  const initialBudgetAmount = decimal(row.initial_budget_amount);
  const currentBudgetAmount = decimal(row.current_budget_amount);
  const committedAmount = decimal(row.committed_amount);
  const liquidatedAmount = decimal(row.liquidated_amount);
  const paidAmount = decimal(row.paid_amount);
  const executionCode = requiredText(row.execution_code);
  const executionSourceUrl = requiredText(row.execution_source_url);
  const executionSourceArtifactSha256 = requiredText(
    row.execution_source_artifact_sha256,
  );
  const executionEvidenceSha256 = requiredText(row.execution_evidence_sha256);
  const executionSourceCollectedAt = requiredText(
    row.execution_source_collected_at,
  );
  const distinctAmendmentNumbers = amendmentNumbers === null
    ? null
    : new Set(amendmentNumbers);

  if (
    fiscalYear === null || !authorExternalCode || !authorKey || !authorName ||
    !agencyCode || !budgetUnitCode || !actionCode || amendmentCount === null ||
    amendmentNumbers === null || amendmentNumbers.some((value) => value === null) ||
    amendmentNumbers.length !== amendmentCount ||
    distinctAmendmentNumbers?.size !== amendmentCount || !authorizedTotal ||
    !initialBudgetAmount || !currentBudgetAmount || !committedAmount ||
    !liquidatedAmount || !paidAmount || !executionCode ||
    !executionSourceUrl?.startsWith("https://") ||
    !executionSourceArtifactSha256 ||
    !SHA256.test(executionSourceArtifactSha256) || !executionEvidenceSha256 ||
    !SHA256.test(executionEvidenceSha256) || !executionSourceCollectedAt ||
    !Number.isFinite(Date.parse(executionSourceCollectedAt)) ||
    row.methodology_version !== METHODOLOGY_VERSION
  ) return null;

  return {
    fiscalYear,
    authorExternalCode,
    authorKey,
    authorName,
    agencyCode,
    budgetUnitCode,
    actionCode,
    amendmentCount,
    amendmentNumbers,
    authorizedTotal,
    initialBudgetAmount,
    currentBudgetAmount,
    committedAmount,
    liquidatedAmount,
    paidAmount,
    executionCode,
    executionSourceUrl,
    executionSourceArtifactSha256,
    executionEvidenceSha256,
    executionSourceCollectedAt,
    methodologyVersion: METHODOLOGY_VERSION,
  };
}

export function parseStateLoaExecutionGroups(rows) {
  if (!Array.isArray(rows)) return null;
  const parsed = rows.map(parseGroup);
  return parsed.some((row) => row === null) ? null : parsed;
}
