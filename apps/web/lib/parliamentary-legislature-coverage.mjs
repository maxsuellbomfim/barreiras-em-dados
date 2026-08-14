const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;
const SPHERES = new Set(["federal", "state"]);
const FIELD_STATUSES = new Set([
  "published_by_source",
  "not_published_in_source",
]);
const METHOD = "parliamentary-legislature-coverage/1.0.0";

function text(value) {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function integer(value, minimum = 0) {
  return Number.isSafeInteger(value) && value >= minimum ? value : null;
}

function date(value) {
  if (typeof value !== "string" || !ISO_DATE.test(value)) return null;
  const parsed = new Date(`${value}T00:00:00Z`);
  return !Number.isNaN(parsed.valueOf()) && parsed.toISOString().slice(0, 10) === value
    ? value
    : null;
}

function transitionYears(value) {
  if (!Array.isArray(value)) return null;
  const years = value.map((year) => integer(year, 1900));
  if (years.some((year) => year === null)) return null;
  return new Set(years).size === years.length ? years.toSorted() : null;
}

function nullableCount(value, status) {
  if (!FIELD_STATUSES.has(status)) return undefined;
  if (status === "not_published_in_source") return value === null ? null : undefined;
  return integer(value);
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
  const excludedTransitionYears = transitionYears(row.excluded_transition_years);
  const rankingAmountStage = text(row.ranking_amount_stage);
  const counts = {
    contributionCount: integer(row.contribution_count),
    authorCount: integer(row.author_count),
    linkedAuthorCount: integer(row.linked_author_count),
    unlinkedAuthorCount: integer(row.unlinked_author_count),
    withObjectCount: integer(row.with_object_count),
    withCommittedCount: integer(row.with_committed_count),
    withPaidCount: integer(row.with_paid_count),
    executionConfirmedCount: integer(row.execution_confirmed_count),
    executionUnresolvedCount: integer(row.execution_unresolved_count),
    primaryEvidenceCount: integer(row.primary_evidence_count),
  };
  const objectFieldStatus = text(row.object_field_status);
  const beneficiaryFieldStatus = text(row.beneficiary_field_status);
  const liquidatedFieldStatus = text(row.liquidated_field_status);
  const withBeneficiaryCount = nullableCount(
    row.with_beneficiary_count,
    beneficiaryFieldStatus,
  );
  const withLiquidatedCount = nullableCount(
    row.with_liquidated_count,
    liquidatedFieldStatus,
  );
  if (
    !sphere || !SPHERES.has(sphere) || legislatureNumber === null ||
    !legislatureLabel || !beginsOn || !endsOn || beginsOn >= endsOn ||
    fullFiscalYearFrom === null || fullFiscalYearTo === null ||
    fullFiscalYearFrom > fullFiscalYearTo ||
    !officialSourceUrl?.startsWith("https://") || !officialSourceNote ||
    excludedTransitionYears === null ||
    excludedTransitionYears.some((year) =>
      year >= fullFiscalYearFrom && year <= fullFiscalYearTo
    ) ||
    (sphere === "federal" && rankingAmountStage !== "destination") ||
    (sphere === "state" && rankingAmountStage !== "authorized") ||
    Object.values(counts).some((value) => value === null) ||
    objectFieldStatus !== "published_by_source" ||
    withBeneficiaryCount === undefined || withLiquidatedCount === undefined ||
    row.methodology_version !== METHOD
  ) return null;
  if (
    (sphere === "federal" && (
      beneficiaryFieldStatus !== "published_by_source" ||
      liquidatedFieldStatus !== "not_published_in_source"
    )) ||
    (sphere === "state" && (
      beneficiaryFieldStatus !== "not_published_in_source" ||
      liquidatedFieldStatus !== "published_by_source"
    ))
  ) return null;

  const contributionCounts = [
    counts.withObjectCount,
    counts.withCommittedCount,
    counts.withPaidCount,
    counts.executionConfirmedCount,
    counts.executionUnresolvedCount,
    counts.primaryEvidenceCount,
    withBeneficiaryCount,
    withLiquidatedCount,
  ].filter((value) => value !== null);
  if (
    counts.linkedAuthorCount + counts.unlinkedAuthorCount !== counts.authorCount ||
    counts.authorCount > counts.contributionCount ||
    counts.executionConfirmedCount + counts.executionUnresolvedCount !==
      counts.contributionCount ||
    contributionCounts.some((value) => value > counts.contributionCount)
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
    ...counts,
    objectFieldStatus,
    withBeneficiaryCount,
    beneficiaryFieldStatus,
    withLiquidatedCount,
    liquidatedFieldStatus,
    methodologyVersion: METHOD,
  };
}

export function parseParliamentaryLegislatureCoverageRows(rows) {
  if (!Array.isArray(rows)) return null;
  const parsed = rows.map(parseRow);
  if (parsed.some((row) => row === null)) return null;
  const keys = new Set();
  for (const row of parsed) {
    const key = `${row.sphere}:${row.legislatureNumber}`;
    if (keys.has(key)) return null;
    keys.add(key);
  }
  return parsed;
}
