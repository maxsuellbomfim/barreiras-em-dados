const DECIMAL = /^-?\d+(?:\.\d{1,2})?$/;
const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;
const SHA256 = /^[0-9a-f]{64}$/;
const SPHERES = new Set(["federal", "state"]);
const ASSOCIATION_STATUSES = new Set([
  "approved_official_crosswalk",
  "not_linked",
]);
const FEDERAL_STATUSES = new Set(["matched_exact", "current_only", "historical_only"]);
const STATE_STATUSES = new Set([
  "execution_confirmed",
  "ambiguous_official_key",
  "not_found_in_execution_source",
  "official_link_key_unavailable",
  "scope_not_available",
]);
const METHODOLOGY_VERSION =
  "parliamentary-legislature-contributions/1.0.0";

function text(value) {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function optionalText(value) {
  return value === null ? null : text(value);
}

function integer(value, minimum = 0) {
  return Number.isSafeInteger(value) && value >= minimum ? value : null;
}

function decimal(value) {
  if (typeof value === "number" && Number.isFinite(value)) value = String(value);
  return typeof value === "string" && DECIMAL.test(value.trim())
    ? value.trim()
    : null;
}

function optionalDecimal(value) {
  return value === null ? null : decimal(value);
}

function date(value) {
  if (typeof value !== "string" || !ISO_DATE.test(value)) return null;
  const parsed = new Date(`${value}T00:00:00Z`);
  return Number.isNaN(parsed.valueOf()) || parsed.toISOString().slice(0, 10) !== value
    ? null
    : value;
}

function years(value) {
  if (!Array.isArray(value)) return null;
  const parsed = value.map((year) => integer(year, 1900));
  if (parsed.some((year) => year === null)) return null;
  const unique = [...new Set(parsed)];
  return unique.length === parsed.length ? unique.toSorted() : null;
}

function profileLinkMatches(sourceKind, url) {
  return sourceKind === "federal"
    ? url.startsWith("https://www.camara.leg.br/")
    : url.startsWith("https://www.al.ba.gov.br/");
}

function sourcePair(urlValue, shaValue, required) {
  if (urlValue === null && shaValue === null && !required) return [null, null];
  const url = text(urlValue);
  const sha256 = text(shaValue);
  return url?.startsWith("https://") && sha256 && SHA256.test(sha256)
    ? [url, sha256]
    : null;
}

function parseRow(row) {
  if (typeof row !== "object" || row === null) return null;
  const sphere = text(row.sphere);
  const legislatureNumber = integer(row.legislature_number, 1);
  const legislatureLabel = text(row.legislature_label);
  const beginsOn = date(row.begins_on);
  const endsOn = date(row.ends_on);
  const fullFiscalYearFrom = integer(row.full_fiscal_year_from, 1900);
  const fullFiscalYearTo = integer(row.full_fiscal_year_to, 1900);
  const officialSourceUrl = text(row.official_source_url);
  const officialSourceNote = text(row.official_source_note);
  const excludedTransitionYears = years(row.excluded_transition_years);
  const rankingAmountStage = text(row.ranking_amount_stage);
  const authorKey = text(row.author_key);
  const authorName = text(row.author_name);
  const associationStatus = text(row.association_status);
  const representativeSourceKind = optionalText(row.representative_source_kind);
  const representativeExternalId = optionalText(row.representative_external_id);
  const representativeProfileUrl = optionalText(row.representative_profile_url);
  const totalAmendmentCount = integer(row.total_amendment_count, 1);
  const totalRankingAmount = decimal(row.total_ranking_amount);
  const totalCommittedAmount = optionalDecimal(row.total_committed_amount);
  const totalLiquidatedAmount = optionalDecimal(row.total_liquidated_amount);
  const totalPaidAmount = optionalDecimal(row.total_paid_amount);
  const rowPosition = integer(row.row_position, 1);
  const contributionKey = text(row.contribution_key);
  const fiscalYear = integer(row.fiscal_year, 1900);
  const amendmentNumber = optionalText(row.amendment_number);
  const beneficiaryName = optionalText(row.beneficiary_name);
  const objectDescription = optionalText(row.object_description);
  const rankingAmount = decimal(row.ranking_amount);
  const committedAmount = optionalDecimal(row.committed_amount);
  const liquidatedAmount = optionalDecimal(row.liquidated_amount);
  const paidAmount = optionalDecimal(row.paid_amount);
  const executionStatus = text(row.execution_status);
  const primarySource = sourcePair(
    row.primary_source_url,
    row.primary_artifact_sha256,
    true,
  );
  const secondarySource = sourcePair(
    row.secondary_source_url,
    row.secondary_artifact_sha256,
    false,
  );
  const evidenceExcerpt = optionalText(row.evidence_excerpt);
  const pageNumber = row.page_number === null ? null : integer(row.page_number, 1);

  if (
    !sphere || !SPHERES.has(sphere) || legislatureNumber === null ||
    !legislatureLabel || !beginsOn || !endsOn || beginsOn >= endsOn ||
    fullFiscalYearFrom === null || fullFiscalYearTo === null ||
    fullFiscalYearFrom > fullFiscalYearTo ||
    !officialSourceUrl?.startsWith("https://") || !officialSourceNote ||
    excludedTransitionYears === null || !authorKey || !authorName ||
    !associationStatus || !ASSOCIATION_STATUSES.has(associationStatus) ||
    totalAmendmentCount === null || !totalRankingAmount || rowPosition === null ||
    rowPosition > totalAmendmentCount || !contributionKey || fiscalYear === null ||
    fiscalYear < fullFiscalYearFrom || fiscalYear > fullFiscalYearTo ||
    !rankingAmount || !executionStatus || !primarySource || !secondarySource ||
    (row.total_committed_amount !== null && totalCommittedAmount === null) ||
    (row.total_liquidated_amount !== null && totalLiquidatedAmount === null) ||
    (row.total_paid_amount !== null && totalPaidAmount === null) ||
    (row.committed_amount !== null && committedAmount === null) ||
    (row.liquidated_amount !== null && liquidatedAmount === null) ||
    (row.paid_amount !== null && paidAmount === null) ||
    (row.page_number !== null && pageNumber === null) ||
    row.methodology_version !== METHODOLOGY_VERSION
  ) return null;

  if (
    (sphere === "federal" && (
      rankingAmountStage !== "destination" || liquidatedAmount !== null ||
      totalLiquidatedAmount !== null || !FEDERAL_STATUSES.has(executionStatus)
    )) ||
    (sphere === "state" && (
      rankingAmountStage !== "authorized" || !STATE_STATUSES.has(executionStatus)
    ))
  ) return null;

  if (associationStatus === "approved_official_crosswalk") {
    if (
      !["federal", "state"].includes(representativeSourceKind ?? "") ||
      !representativeExternalId || !representativeProfileUrl ||
      !profileLinkMatches(representativeSourceKind, representativeProfileUrl)
    ) return null;
  } else if (
    representativeSourceKind !== null || representativeExternalId !== null ||
    representativeProfileUrl !== null
  ) return null;

  return {
    sphere,
    legislatureNumber,
    legislatureLabel,
    beginsOn,
    endsOn,
    fullFiscalYearFrom,
    fullFiscalYearTo,
    officialSourceUrl,
    officialSourceNote,
    excludedTransitionYears,
    rankingAmountStage,
    authorKey,
    authorName,
    representativeSourceKind,
    representativeExternalId,
    representativeProfileUrl,
    associationStatus,
    totalAmendmentCount,
    totalRankingAmount,
    totalCommittedAmount,
    totalLiquidatedAmount,
    totalPaidAmount,
    rowPosition,
    contributionKey,
    fiscalYear,
    amendmentNumber,
    beneficiaryName,
    objectDescription,
    rankingAmount,
    committedAmount,
    liquidatedAmount,
    paidAmount,
    executionStatus,
    primarySourceUrl: primarySource[0],
    primaryArtifactSha256: primarySource[1],
    secondarySourceUrl: secondarySource[0],
    secondaryArtifactSha256: secondarySource[1],
    evidenceExcerpt,
    pageNumber,
    methodologyVersion: METHODOLOGY_VERSION,
  };
}

export function parseParliamentaryContributionProfileRows(rows) {
  if (!Array.isArray(rows) || rows.length === 0) return null;
  const parsed = rows.map(parseRow);
  if (parsed.some((row) => row === null)) return null;
  const first = parsed[0];
  const metadata = JSON.stringify([
    first.sphere,
    first.legislatureNumber,
    first.legislatureLabel,
    first.beginsOn,
    first.endsOn,
    first.fullFiscalYearFrom,
    first.fullFiscalYearTo,
    first.officialSourceUrl,
    first.officialSourceNote,
    first.excludedTransitionYears,
    first.rankingAmountStage,
    first.authorKey,
    first.authorName,
    first.representativeSourceKind,
    first.representativeExternalId,
    first.representativeProfileUrl,
    first.associationStatus,
    first.totalAmendmentCount,
    first.totalRankingAmount,
    first.totalCommittedAmount,
    first.totalLiquidatedAmount,
    first.totalPaidAmount,
  ]);
  const positions = new Set();
  const keys = new Set();
  for (const row of parsed) {
    const rowMetadata = JSON.stringify([
      row.sphere,
      row.legislatureNumber,
      row.legislatureLabel,
      row.beginsOn,
      row.endsOn,
      row.fullFiscalYearFrom,
      row.fullFiscalYearTo,
      row.officialSourceUrl,
      row.officialSourceNote,
      row.excludedTransitionYears,
      row.rankingAmountStage,
      row.authorKey,
      row.authorName,
      row.representativeSourceKind,
      row.representativeExternalId,
      row.representativeProfileUrl,
      row.associationStatus,
      row.totalAmendmentCount,
      row.totalRankingAmount,
      row.totalCommittedAmount,
      row.totalLiquidatedAmount,
      row.totalPaidAmount,
    ]);
    if (
      rowMetadata !== metadata || positions.has(row.rowPosition) ||
      keys.has(row.contributionKey)
    ) return null;
    positions.add(row.rowPosition);
    keys.add(row.contributionKey);
  }
  return {
    sphere: first.sphere,
    legislatureNumber: first.legislatureNumber,
    legislatureLabel: first.legislatureLabel,
    beginsOn: first.beginsOn,
    endsOn: first.endsOn,
    fullFiscalYearFrom: first.fullFiscalYearFrom,
    fullFiscalYearTo: first.fullFiscalYearTo,
    officialSourceUrl: first.officialSourceUrl,
    officialSourceNote: first.officialSourceNote,
    excludedTransitionYears: first.excludedTransitionYears,
    rankingAmountStage: first.rankingAmountStage,
    authorKey: first.authorKey,
    authorName: first.authorName,
    representativeSourceKind: first.representativeSourceKind,
    representativeExternalId: first.representativeExternalId,
    representativeProfileUrl: first.representativeProfileUrl,
    associationStatus: first.associationStatus,
    totalAmendmentCount: first.totalAmendmentCount,
    totalRankingAmount: first.totalRankingAmount,
    totalCommittedAmount: first.totalCommittedAmount,
    totalLiquidatedAmount: first.totalLiquidatedAmount,
    totalPaidAmount: first.totalPaidAmount,
    contributions: parsed.toSorted((left, right) =>
      left.rowPosition - right.rowPosition
    ),
    methodologyVersion: METHODOLOGY_VERSION,
  };
}
