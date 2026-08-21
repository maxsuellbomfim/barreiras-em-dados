const PAYMENT_METHOD = "bahia-special-transfer-payments/1.0.0";
const RANKING_METHOD = "bahia-special-transfer-ranking/1.0.0";
const ANNUAL_COVERAGE_METHOD =
  "bahia-special-transfer-annual-coverage/1.0.0";
const DECIMAL = /^\d+(?:\.\d{1,2})?$/;
const DATE = /^\d{4}-\d{2}-\d{2}$/;
const HASH = /^[0-9a-f]{64}$/;
const AUTHOR_KINDS = new Set(["federal", "state"]);
const ASSOCIATIONS = new Set([
  "approved_official_author_code_crosswalk",
  "not_linked",
]);
const FEDERAL_LINKS = new Set([
  "matched_cgu_unique",
  "not_found_in_cgu",
  "conflict_non_unique_cgu",
]);
const PAYMENT_KEYS = new Set([
  "fiscal_year", "amendment_number", "amendment_year",
  "official_amendment_code", "source_author_name", "author_key",
  "official_author_name", "representative_source_kind",
  "representative_external_id", "representative_profile_url",
  "association_status", "agency_name", "budget_unit_name", "action_name",
  "payment_id", "payment_number", "payment_date", "payment_amount",
  "payment_status", "object_text", "payment_url", "financial_stage",
  "territorial_scope", "federal_link_status", "aggregation_policy",
  "evidence_text", "evidence_sha256", "source_url",
  "source_artifact_sha256", "source_collected_at", "methodology_version",
]);
const RANKING_KEYS = new Set([
  "rank_position", "author_key", "official_author_name",
  "representative_source_kind", "representative_external_id",
  "representative_profile_url", "payment_count", "amendment_count",
  "paid_amount", "first_payment_date", "last_payment_date",
  "ranking_amount_stage", "territorial_scope", "aggregation_policy",
  "methodology_version",
]);
const ANNUAL_COVERAGE_KEYS = new Set([
  "fiscal_year", "source_payment_count", "territorial_payment_count",
  "territorial_status", "source_snapshot_status", "territorial_scope",
  "source_url", "source_artifact_sha256", "source_collected_at",
  "methodology_version",
]);

function exactKeys(row, allowed) {
  return Object.keys(row).every((key) => allowed.has(key));
}

function text(value, min = 1, max = 4000) {
  return typeof value === "string" && value.trim().length >= min &&
      value.trim().length <= max
    ? value.trim()
    : null;
}

function nullableText(value, max = 4000) {
  return value === null ? null : text(value, 1, max);
}

function integer(value, min, max) {
  return Number.isSafeInteger(value) && value >= min && value <= max
    ? value
    : null;
}

function decimal(value) {
  if (typeof value === "string" && DECIMAL.test(value)) return value;
  if (typeof value !== "number" || !Number.isFinite(value)) return null;
  const cents = Math.round(value * 100);
  if (!Number.isSafeInteger(cents) || cents < 0) return null;
  const normalized = cents / 100;
  const tolerance = Number.EPSILON * Math.max(1, Math.abs(value)) * 4;
  return Math.abs(value - normalized) <= tolerance
    ? normalized.toFixed(2)
    : null;
}

function date(value) {
  if (typeof value !== "string" || !DATE.test(value)) return null;
  const parsed = Date.parse(`${value}T12:00:00Z`);
  return Number.isNaN(parsed) ? null : value;
}

function httpsUrl(value) {
  if (typeof value !== "string") return null;
  try {
    const parsed = new URL(value);
    return parsed.protocol === "https:" ? value : null;
  } catch {
    return null;
  }
}

function nullableHttpsUrl(value) {
  return value === null ? null : httpsUrl(value);
}

function timestamp(value) {
  return typeof value === "string" && !Number.isNaN(Date.parse(value))
    ? value
    : null;
}

function parsePayment(row) {
  if (typeof row !== "object" || row === null || !exactKeys(row, PAYMENT_KEYS)) {
    return null;
  }
  const fiscalYear = integer(row.fiscal_year, 2000, 2100);
  const amendmentYear = integer(row.amendment_year, 2000, 2100);
  const amendmentNumber = text(row.amendment_number, 8, 8);
  const officialAmendmentCode = text(row.official_amendment_code, 12, 12);
  const sourceAuthorName = text(row.source_author_name, 2, 200);
  const authorKey = nullableText(row.author_key, 200);
  const officialAuthorName = text(row.official_author_name, 2, 200);
  const representativeSourceKind = row.representative_source_kind === null
    ? null
    : AUTHOR_KINDS.has(row.representative_source_kind)
      ? row.representative_source_kind
      : null;
  const representativeExternalId = nullableText(
    row.representative_external_id,
    100,
  );
  const representativeProfileUrl = nullableHttpsUrl(
    row.representative_profile_url,
  );
  const agencyName = text(row.agency_name, 2, 500);
  const budgetUnitName = text(row.budget_unit_name, 2, 500);
  const actionName = text(row.action_name, 2, 1000);
  const paymentId = text(row.payment_id, 18, 19);
  const paymentNumber = text(row.payment_number, 1, 100);
  const paymentDate = date(row.payment_date);
  const paymentAmount = decimal(row.payment_amount);
  const paymentStatus = text(row.payment_status, 2, 40);
  const objectText = text(row.object_text, 2, 8000);
  const paymentUrl = httpsUrl(row.payment_url);
  const evidenceText = text(row.evidence_text, 2, 8000);
  const sourceUrl = httpsUrl(row.source_url);
  const sourceCollectedAt = timestamp(row.source_collected_at);
  if (
    fiscalYear === null || amendmentYear === null ||
    !amendmentNumber || !/^\d{8}$/.test(amendmentNumber) ||
    !officialAmendmentCode || !/^\d{12}$/.test(officialAmendmentCode) ||
    !sourceAuthorName || !officialAuthorName || !agencyName ||
    !budgetUnitName || !actionName || !paymentId || !/^\d{18,19}$/.test(paymentId) ||
    !paymentNumber || !paymentDate || paymentAmount === null || !paymentStatus ||
    !objectText || !paymentUrl || !evidenceText || !sourceUrl ||
    !sourceCollectedAt || !HASH.test(row.evidence_sha256) ||
    !HASH.test(row.source_artifact_sha256) ||
    !ASSOCIATIONS.has(row.association_status) ||
    !FEDERAL_LINKS.has(row.federal_link_status) ||
    row.financial_stage !== "paid_by_bahia_state" ||
    row.territorial_scope !== "payment_object_literal_barreiras" ||
    row.aggregation_policy !== "single_source_no_cross_source_sum" ||
    row.methodology_version !== PAYMENT_METHOD
  ) return null;
  if (
    row.association_status === "approved_official_author_code_crosswalk" &&
    (!authorKey || !representativeSourceKind || !representativeExternalId ||
      !representativeProfileUrl)
  ) return null;
  if (
    row.association_status === "not_linked" &&
    (authorKey !== null || representativeSourceKind !== null ||
      representativeExternalId !== null || representativeProfileUrl !== null)
  ) return null;

  return {
    fiscalYear, amendmentNumber, amendmentYear, officialAmendmentCode,
    sourceAuthorName, authorKey, officialAuthorName, representativeSourceKind,
    representativeExternalId, representativeProfileUrl,
    associationStatus: row.association_status, agencyName, budgetUnitName,
    actionName, paymentId, paymentNumber, paymentDate, paymentAmount,
    paymentStatus, objectText, paymentUrl,
    financialStage: "paid_by_bahia_state",
    territorialScope: "payment_object_literal_barreiras",
    federalLinkStatus: row.federal_link_status,
    aggregationPolicy: "single_source_no_cross_source_sum",
    evidenceText, evidenceSha256: row.evidence_sha256, sourceUrl,
    sourceArtifactSha256: row.source_artifact_sha256, sourceCollectedAt,
    methodologyVersion: PAYMENT_METHOD,
  };
}

function parseRanking(row) {
  if (typeof row !== "object" || row === null || !exactKeys(row, RANKING_KEYS)) {
    return null;
  }
  const rankPosition = integer(row.rank_position, 1, 50);
  const authorKey = text(row.author_key, 2, 200);
  const officialAuthorName = text(row.official_author_name, 2, 200);
  const representativeSourceKind = AUTHOR_KINDS.has(row.representative_source_kind)
    ? row.representative_source_kind
    : null;
  const representativeExternalId = text(row.representative_external_id, 1, 100);
  const representativeProfileUrl = httpsUrl(row.representative_profile_url);
  const paymentCount = integer(row.payment_count, 1, 1_000_000);
  const amendmentCount = integer(row.amendment_count, 1, 1_000_000);
  const paidAmount = decimal(row.paid_amount);
  const firstPaymentDate = date(row.first_payment_date);
  const lastPaymentDate = date(row.last_payment_date);
  if (
    rankPosition === null || !authorKey || !officialAuthorName ||
    !representativeSourceKind || !representativeExternalId ||
    !representativeProfileUrl || paymentCount === null ||
    amendmentCount === null || paidAmount === null || !firstPaymentDate ||
    !lastPaymentDate || firstPaymentDate > lastPaymentDate ||
    row.ranking_amount_stage !== "paid_by_bahia_state" ||
    row.territorial_scope !== "payment_object_literal_barreiras" ||
    row.aggregation_policy !== "single_source_no_cross_source_sum" ||
    row.methodology_version !== RANKING_METHOD
  ) return null;
  return {
    rankPosition, authorKey, officialAuthorName, representativeSourceKind,
    representativeExternalId, representativeProfileUrl, paymentCount,
    amendmentCount, paidAmount, firstPaymentDate, lastPaymentDate,
    rankingAmountStage: "paid_by_bahia_state",
    territorialScope: "payment_object_literal_barreiras",
    aggregationPolicy: "single_source_no_cross_source_sum",
    methodologyVersion: RANKING_METHOD,
  };
}

function parseAnnualCoverage(row) {
  if (
    typeof row !== "object" || row === null ||
    !exactKeys(row, ANNUAL_COVERAGE_KEYS)
  ) return null;
  const fiscalYear = integer(row.fiscal_year, 2021, 2100);
  const sourcePaymentCount = integer(row.source_payment_count, 1, 999_999_999);
  const territorialPaymentCount = integer(
    row.territorial_payment_count,
    0,
    999_999_999,
  );
  const sourceUrl = httpsUrl(row.source_url);
  const sourceCollectedAt = timestamp(row.source_collected_at);
  const expectedTerritorialStatus = territorialPaymentCount === 0
    ? "collected_no_territorial_record"
    : "territorial_records_observed";
  if (
    fiscalYear === null || sourcePaymentCount === null ||
    territorialPaymentCount === null ||
    territorialPaymentCount > sourcePaymentCount || !sourceUrl ||
    !sourceCollectedAt || !HASH.test(row.source_artifact_sha256) ||
    row.territorial_status !== expectedTerritorialStatus ||
    row.source_snapshot_status !== "source_snapshot_processed" ||
    row.territorial_scope !== "payment_object_literal_barreiras" ||
    row.methodology_version !== ANNUAL_COVERAGE_METHOD
  ) return null;
  return {
    fiscalYear,
    sourcePaymentCount,
    territorialPaymentCount,
    territorialStatus: expectedTerritorialStatus,
    sourceSnapshotStatus: "source_snapshot_processed",
    territorialScope: "payment_object_literal_barreiras",
    sourceUrl,
    sourceArtifactSha256: row.source_artifact_sha256,
    sourceCollectedAt,
    methodologyVersion: ANNUAL_COVERAGE_METHOD,
  };
}

export function parseBahiaSpecialTransferPayments(rows) {
  if (!Array.isArray(rows)) return null;
  const parsed = rows.map(parsePayment);
  if (parsed.some((row) => row === null)) return null;
  const ids = new Set();
  for (const row of parsed) {
    if (ids.has(row.paymentId)) return null;
    ids.add(row.paymentId);
  }
  return parsed;
}

export function parseBahiaSpecialTransferRanking(rows) {
  if (!Array.isArray(rows)) return null;
  const parsed = rows.map(parseRanking);
  if (parsed.some((row) => row === null)) return null;
  const authors = new Set();
  const positions = new Set();
  for (const row of parsed) {
    if (authors.has(row.authorKey) || positions.has(row.rankPosition)) return null;
    authors.add(row.authorKey);
    positions.add(row.rankPosition);
  }
  return parsed.sort((left, right) => left.rankPosition - right.rankPosition);
}

export function parseBahiaSpecialTransferAnnualCoverage(rows) {
  if (!Array.isArray(rows)) return null;
  const parsed = rows.map(parseAnnualCoverage);
  if (parsed.some((row) => row === null)) return null;
  const years = new Set();
  for (const row of parsed) {
    if (years.has(row.fiscalYear)) return null;
    years.add(row.fiscalYear);
  }
  return parsed.sort((left, right) => right.fiscalYear - left.fiscalYear);
}
