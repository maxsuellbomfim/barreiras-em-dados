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
  // PostgREST serializa numeric(20,2) como número JSON; a string mais curta
  // que o representa preserva os centavos nesta ordem de grandeza.
  if (typeof value === "number" && Number.isFinite(value)) value = String(value);
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

const LEGISLATURE_RANKING_METHODOLOGY =
  "cgu-federal-amendment-legislature-ranking/2.0.0";

function parseLegislatureRankingRow(row) {
  if (typeof row !== "object" || row === null) return null;
  const legislatureNumber = integer(row.legislature_number, 1);
  const legislatureLabel = requiredText(row.legislature_label);
  const fullFiscalYearFrom = integer(row.full_fiscal_year_from, 2000);
  const fullFiscalYearTo = integer(row.full_fiscal_year_to, 2000);
  const authorScope = requiredText(row.author_scope);
  const rankPosition = integer(row.rank_position, 1);
  const authorKind = requiredText(row.author_kind);
  const authorKey = requiredText(row.author_key);
  const authorName = requiredText(row.author_name);
  const authorCode = requiredText(row.author_code);
  const representativeSourceKind = requiredText(
    row.representative_source_kind,
  );
  const representativeExternalId = requiredText(
    row.representative_external_id,
  );
  const representativeProfileUrl = requiredText(
    row.representative_profile_url,
  );
  const associationStatus = requiredText(row.association_status);
  const amendmentCount = integer(row.amendment_count, 1);
  const committedAmount = decimal(row.committed_amount);
  const effectivePaidAmount = decimal(row.effective_paid_amount);
  const firstYear = integer(row.first_year, 2000);
  const lastYear = integer(row.last_year, 2000);
  const scopeMatchesKind = authorScope === "person"
    ? authorKind === "person"
    : authorScope === "collective" && (
      authorKind === "commission" || authorKind === "bench" ||
      authorKind === "collective"
    );
  if (
    legislatureNumber === null || !legislatureLabel ||
    fullFiscalYearFrom === null || fullFiscalYearTo === null ||
    fullFiscalYearFrom > fullFiscalYearTo || !authorScope ||
    rankPosition === null || !authorKind || !scopeMatchesKind ||
    !authorKey || !authorName || !authorCode || amendmentCount === null ||
    !committedAmount || !effectivePaidAmount ||
    firstYear === null || lastYear === null || firstYear > lastYear ||
    firstYear < fullFiscalYearFrom || lastYear > fullFiscalYearTo ||
    row.ranking_amount_stage !== "committed" ||
    row.methodology_version !== LEGISLATURE_RANKING_METHODOLOGY
  ) return null;
  const approvedAssociation =
    associationStatus === "approved_official_author_code_crosswalk" &&
    authorScope === "person" && representativeSourceKind === "federal" &&
    Boolean(representativeExternalId) &&
    representativeProfileUrl?.startsWith("https://");
  const absentAssociation = associationStatus === "not_linked" &&
    representativeSourceKind === null && representativeExternalId === null &&
    representativeProfileUrl === null;
  if (!approvedAssociation && !absentAssociation) return null;
  return {
    legislatureNumber,
    legislatureLabel,
    fullFiscalYearFrom,
    fullFiscalYearTo,
    authorScope,
    rankPosition,
    authorKind,
    authorKey,
    authorName,
    authorCode,
    representativeSourceKind,
    representativeExternalId,
    representativeProfileUrl,
    associationStatus,
    amendmentCount,
    committedAmount,
    effectivePaidAmount,
    firstYear,
    lastYear,
    rankingAmountStage: "committed",
    methodologyVersion: LEGISLATURE_RANKING_METHODOLOGY,
  };
}

export function parseCguLegislatureRankingRows(rows) {
  if (!Array.isArray(rows)) return null;
  const parsed = rows.map(parseLegislatureRankingRow);
  if (parsed.some((row) => row === null)) return null;
  const positions = new Map();
  for (const row of parsed) {
    const partition = `${row.legislatureNumber}:${row.authorScope}`;
    const expected = (positions.get(partition) ?? 0) + 1;
    if (row.rankPosition !== expected) return null;
    positions.set(partition, expected);
  }
  return parsed;
}

export function groupCguLegislatureRankings(rows) {
  const groups = new Map();
  for (const row of rows) {
    const group = groups.get(row.legislatureNumber) ?? {
      legislatureNumber: row.legislatureNumber,
      legislatureLabel: row.legislatureLabel,
      fullFiscalYearFrom: row.fullFiscalYearFrom,
      fullFiscalYearTo: row.fullFiscalYearTo,
      people: [],
      collectives: [],
    };
    if (row.authorScope === "person") group.people.push(row);
    else group.collectives.push(row);
    groups.set(row.legislatureNumber, group);
  }
  return [...groups.values()];
}
