const DECIMAL = /^-?\d+(?:\.\d{1,2})?$/;
const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;
const SPHERES = new Set(["federal", "state"]);
const SOURCE_KINDS = new Set(["federal", "state"]);
const ASSOCIATION_STATUSES = new Set([
  "approved_official_crosswalk",
  "not_linked",
]);
const METHODOLOGY_VERSION =
  "parliamentary-legislature-transfer-ranking/1.0.0";

function text(value) {
  return typeof value === "string" && value.trim() ? value.trim() : null;
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

function date(value) {
  if (typeof value !== "string" || !ISO_DATE.test(value)) return null;
  const parsed = new Date(`${value}T00:00:00Z`);
  return Number.isNaN(parsed.valueOf()) || parsed.toISOString().slice(0, 10) !== value
    ? null
    : value;
}

function transitionYears(value) {
  if (!Array.isArray(value)) return null;
  const years = value.map((year) => integer(year, 1900));
  if (years.some((year) => year === null)) return null;
  const unique = [...new Set(years)];
  return unique.length === years.length ? unique.toSorted() : null;
}

function profileLinkMatches(sourceKind, url) {
  if (sourceKind === "federal") {
    return url.startsWith("https://www.camara.leg.br/");
  }
  return url.startsWith("https://www.al.ba.gov.br/");
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
    row.methodology_version !== METHODOLOGY_VERSION
  ) return null;

  const rankPosition = row.rank_position === null
    ? null
    : integer(row.rank_position, 1);
  if (rankPosition === null) {
    const nullableRankingFields = [
      "author_key",
      "author_name",
      "representative_source_kind",
      "representative_external_id",
      "representative_profile_url",
      "association_status",
      "amendment_count",
      "ranking_amount",
      "committed_amount",
      "liquidated_amount",
      "paid_amount",
      "first_year",
      "last_year",
    ];
    if (nullableRankingFields.some((field) => row[field] !== null)) return null;
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
      rankPosition: null,
      authorKey: null,
      authorName: null,
      representativeSourceKind: null,
      representativeExternalId: null,
      representativeProfileUrl: null,
      associationStatus: null,
      amendmentCount: null,
      rankingAmount: null,
      committedAmount: null,
      liquidatedAmount: null,
      paidAmount: null,
      firstYear: null,
      lastYear: null,
      methodologyVersion: METHODOLOGY_VERSION,
    };
  }

  const authorKey = text(row.author_key);
  const authorName = text(row.author_name);
  const representativeSourceKind = row.representative_source_kind === null
    ? null
    : text(row.representative_source_kind);
  const representativeExternalId = row.representative_external_id === null
    ? null
    : text(row.representative_external_id);
  const representativeProfileUrl = row.representative_profile_url === null
    ? null
    : text(row.representative_profile_url);
  const associationStatus = text(row.association_status);
  const amendmentCount = integer(row.amendment_count, 1);
  const rankingAmount = decimal(row.ranking_amount);
  const committedAmount = row.committed_amount === null
    ? null
    : decimal(row.committed_amount);
  const liquidatedAmount = row.liquidated_amount === null
    ? null
    : decimal(row.liquidated_amount);
  const paidAmount = row.paid_amount === null ? null : decimal(row.paid_amount);
  const firstYear = integer(row.first_year, 1900);
  const lastYear = integer(row.last_year, 1900);
  if (
    rankPosition > 10 || !authorKey || !authorName || amendmentCount === null ||
    !rankingAmount || firstYear === null || lastYear === null ||
    firstYear < fullFiscalYearFrom || lastYear > fullFiscalYearTo ||
    firstYear > lastYear || !associationStatus ||
    !ASSOCIATION_STATUSES.has(associationStatus) ||
    (row.committed_amount !== null && committedAmount === null) ||
    (row.liquidated_amount !== null && liquidatedAmount === null) ||
    (row.paid_amount !== null && paidAmount === null)
  ) return null;
  if (associationStatus === "approved_official_crosswalk") {
    if (
      !representativeSourceKind || !SOURCE_KINDS.has(representativeSourceKind) ||
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
    rankPosition,
    authorKey,
    authorName,
    representativeSourceKind,
    representativeExternalId,
    representativeProfileUrl,
    associationStatus,
    amendmentCount,
    rankingAmount,
    committedAmount,
    liquidatedAmount,
    paidAmount,
    firstYear,
    lastYear,
    methodologyVersion: METHODOLOGY_VERSION,
  };
}

export function parseParliamentaryLegislatureRankingRows(rows) {
  if (!Array.isArray(rows)) return null;
  const parsed = rows.map(parseRow);
  if (parsed.some((row) => row === null)) return null;
  const termMetadata = new Map();
  const ranks = new Set();
  for (const row of parsed) {
    const termKey = `${row.sphere}:${row.legislatureNumber}`;
    const metadata = JSON.stringify([
      row.legislatureLabel,
      row.beginsOn,
      row.endsOn,
      row.fullFiscalYearFrom,
      row.fullFiscalYearTo,
      row.officialSourceUrl,
      row.officialSourceNote,
      row.excludedTransitionYears,
      row.rankingAmountStage,
    ]);
    if (termMetadata.has(termKey) && termMetadata.get(termKey) !== metadata) return null;
    termMetadata.set(termKey, metadata);
    if (row.rankPosition !== null) {
      const rankKey = `${termKey}:${row.rankPosition}`;
      if (ranks.has(rankKey)) return null;
      ranks.add(rankKey);
    }
  }
  return parsed;
}

export function groupParliamentaryLegislatureRankings(rows) {
  const groups = new Map();
  for (const row of rows) {
    const key = `${row.sphere}:${row.legislatureNumber}`;
    if (!groups.has(key)) {
      groups.set(key, {
        sphere: row.sphere,
        legislatureNumber: row.legislatureNumber,
        legislatureLabel: row.legislatureLabel,
        beginsOn: row.beginsOn,
        endsOn: row.endsOn,
        fullFiscalYearFrom: row.fullFiscalYearFrom,
        fullFiscalYearTo: row.fullFiscalYearTo,
        officialSourceUrl: row.officialSourceUrl,
        officialSourceNote: row.officialSourceNote,
        excludedTransitionYears: row.excludedTransitionYears,
        rankingAmountStage: row.rankingAmountStage,
        rankings: [],
      });
    }
    if (row.rankPosition !== null) groups.get(key).rankings.push(row);
  }
  const sphereOrder = { state: 0, federal: 1 };
  return [...groups.values()]
    .map((group) => ({
      ...group,
      rankings: group.rankings.toSorted((left, right) =>
        left.rankPosition - right.rankPosition
      ),
    }))
    .toSorted((left, right) =>
      sphereOrder[left.sphere] - sphereOrder[right.sphere] ||
      right.legislatureNumber - left.legislatureNumber
    );
}
