const DECIMAL = /^-?\d+(?:\.\d{1,2})?$/;
const SOURCE_KINDS = new Set(["federal", "state"]);

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

function parseContribution(row) {
  if (typeof row !== "object" || row === null) return null;
  const representativeSourceKind = requiredText(row.representative_source_kind);
  const representativeExternalId = requiredText(row.representative_external_id);
  const representativeProfileUrl = requiredText(row.representative_profile_url);
  const authorKey = requiredText(row.author_key);
  const authorName = requiredText(row.author_name);
  const fiscalYear = integer(row.fiscal_year, 2022);
  const amendmentCount = integer(row.amendment_count, 1);
  const authorizedAmount = decimal(row.authorized_amount);
  const matchedAmendmentCount = integer(row.matched_amendment_count);
  const blockedAmendmentCount = integer(row.blocked_amendment_count);
  if (
    !representativeSourceKind || !SOURCE_KINDS.has(representativeSourceKind) ||
    !representativeExternalId || !representativeProfileUrl || !authorKey ||
    !authorName || fiscalYear === null || amendmentCount === null ||
    !authorizedAmount || matchedAmendmentCount === null ||
    blockedAmendmentCount === null ||
    matchedAmendmentCount + blockedAmendmentCount !== amendmentCount ||
    (representativeSourceKind === "state" &&
      !representativeProfileUrl.startsWith("https://www.al.ba.gov.br/")) ||
    (representativeSourceKind === "federal" &&
      !representativeProfileUrl.startsWith("https://www.camara.leg.br/")) ||
    row.methodology_version !==
      "bahia-state-loa-representative-contributions/1.0.0"
  ) return null;

  const matchedAuthorizedAmount = row.matched_authorized_amount === null
    ? null
    : decimal(row.matched_authorized_amount);
  const committedAmount = row.committed_amount === null
    ? null
    : decimal(row.committed_amount);
  const liquidatedAmount = row.liquidated_amount === null
    ? null
    : decimal(row.liquidated_amount);
  const paidAmount = row.paid_amount === null ? null : decimal(row.paid_amount);
  const executionAmounts = [
    matchedAuthorizedAmount,
    committedAmount,
    liquidatedAmount,
    paidAmount,
  ];
  if (
    (matchedAmendmentCount === 0 && executionAmounts.some((value) => value !== null)) ||
    (matchedAmendmentCount > 0 && executionAmounts.some((value) => value === null))
  ) return null;

  return {
    representativeSourceKind,
    representativeExternalId,
    representativeProfileUrl,
    authorKey,
    authorName,
    fiscalYear,
    amendmentCount,
    authorizedAmount,
    matchedAmendmentCount,
    matchedAuthorizedAmount,
    committedAmount,
    liquidatedAmount,
    paidAmount,
    blockedAmendmentCount,
    methodologyVersion:
      "bahia-state-loa-representative-contributions/1.0.0",
  };
}

export function parseStateLoaRepresentativeContributions(rows) {
  if (!Array.isArray(rows)) return null;
  const parsed = rows.map(parseContribution);
  return parsed.some((row) => row === null) ? null : parsed;
}

export function stateLoaContributionsForRepresentative(
  rows,
  sourceKind,
  representativeExternalId,
) {
  return rows
    .filter((row) =>
      row.representativeSourceKind === sourceKind &&
      row.representativeExternalId === representativeExternalId
    )
    .toSorted((left, right) => right.fiscalYear - left.fiscalYear);
}
