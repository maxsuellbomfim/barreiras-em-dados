const DECIMAL = /^-?\d+(?:\.\d{1,2})?$/;
const SHA256 = /^[0-9a-f]{64}$/;
const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;
const AUTHOR_KINDS = new Set(["person", "commission", "bench", "other"]);
const EXPENSE_STAGES = new Set(["commitment", "liquidation", "payment"]);
const DOCUMENT_METHODOLOGY = "cgu-federal-amendment-documents/1.0.0";
const RANKING_METHODOLOGY =
  "cgu-federal-amendment-document-ranking/1.0.0";
const STUDY_METHODOLOGY =
  "cgu-federal-amendment-document-study/1.0.0";
const AGGREGATION_POLICY = "single_document_source_no_cross_source_sum";

function requiredText(value) {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function optionalText(value) {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function integer(value, minimum) {
  return Number.isInteger(value) && value >= minimum ? value : null;
}

function decimal(value) {
  if (typeof value === "number" && Number.isFinite(value)) value = String(value);
  return typeof value === "string" && DECIMAL.test(value) ? value : null;
}

function isoDate(value) {
  if (typeof value !== "string" || !ISO_DATE.test(value)) return null;
  const parsed = new Date(`${value}T00:00:00Z`);
  return Number.isFinite(parsed.getTime()) &&
      parsed.toISOString().slice(0, 10) === value
    ? value
    : null;
}

function parseDocumentRow(row) {
  if (typeof row !== "object" || row === null) return null;
  const archiveYear = integer(row.archive_year, 2021);
  const amendmentYear = integer(row.amendment_year, 2000);
  const amendmentCode = requiredText(row.amendment_code);
  const amendmentNumber = requiredText(row.amendment_number);
  const amendmentType = requiredText(row.amendment_type);
  const authorKind = requiredText(row.author_kind);
  const authorKey = requiredText(row.author_key);
  const authorName = requiredText(row.author_name);
  const documentDate = isoDate(row.document_date);
  const documentCode = requiredText(row.document_code);
  const expenseStage = requiredText(row.expense_stage);
  const expenseStageSource = requiredText(row.expense_stage_source);
  const committedAmount = decimal(row.committed_amount);
  const paidAmount = decimal(row.paid_amount);
  const beneficiaryName = requiredText(row.beneficiary_name);
  const locality = requiredText(row.locality);
  const agencyName = requiredText(row.agency_name);
  const actionName = requiredText(row.action_name);
  const sourceRowNumber = integer(row.source_row_number, 1);
  const sourceUrl = requiredText(row.source_url);
  const artifactSha256 = requiredText(row.artifact_sha256);
  const collectedAt = requiredText(row.collected_at);
  if (
    archiveYear === null || amendmentYear === null ||
    amendmentYear > archiveYear || !amendmentCode || !amendmentNumber ||
    !amendmentType || !authorKind || !AUTHOR_KINDS.has(authorKind) ||
    !authorKey || !authorName || !documentDate ||
    Number(documentDate.slice(0, 4)) !== archiveYear || !documentCode ||
    !expenseStage || !EXPENSE_STAGES.has(expenseStage) ||
    !expenseStageSource || committedAmount === null || paidAmount === null ||
    !beneficiaryName || !locality || !agencyName || !actionName ||
    sourceRowNumber === null || !sourceUrl?.startsWith("https://") ||
    !artifactSha256 || !SHA256.test(artifactSha256) || !collectedAt ||
    !Number.isFinite(Date.parse(collectedAt)) ||
    row.methodology_version !== DOCUMENT_METHODOLOGY
  ) return null;
  return {
    archiveYear,
    amendmentYear,
    amendmentCode,
    amendmentNumber,
    amendmentType,
    authorKind,
    authorKey,
    authorName,
    documentDate,
    documentCode,
    expenseStage,
    expenseStageSource,
    committedAmount,
    paidAmount,
    beneficiaryName,
    beneficiaryType: optionalText(row.beneficiary_type),
    beneficiaryMunicipality: optionalText(row.beneficiary_municipality),
    locality,
    agencyName,
    superiorAgencyName: optionalText(row.superior_agency_name),
    functionName: optionalText(row.function_name),
    subfunctionName: optionalText(row.subfunction_name),
    programName: optionalText(row.program_name),
    actionName,
    citizenLanguage: optionalText(row.citizen_language),
    sourceRowNumber,
    sourceUrl,
    artifactSha256,
    collectedAt,
    methodologyVersion: DOCUMENT_METHODOLOGY,
  };
}

export function parseCguFederalAmendmentDocumentRows(rows) {
  if (!Array.isArray(rows)) return null;
  const parsed = rows.map(parseDocumentRow);
  return parsed.some((row) => row === null) ? null : parsed;
}

function parseRankingRow(row, expectedPosition) {
  if (typeof row !== "object" || row === null) return null;
  const authorKind = requiredText(row.author_kind);
  const authorKey = requiredText(row.author_key);
  const authorName = requiredText(row.author_name);
  const amendmentCount = integer(row.amendment_count, 1);
  const documentCount = integer(row.document_count, 1);
  const committedAmount = decimal(row.committed_amount);
  const paidAmount = decimal(row.paid_amount);
  const firstDocumentDate = isoDate(row.first_document_date);
  const lastDocumentDate = isoDate(row.last_document_date);
  if (
    row.rank_position !== expectedPosition || !authorKind ||
    !AUTHOR_KINDS.has(authorKind) || !authorKey || !authorName ||
    amendmentCount === null || documentCount === null ||
    committedAmount === null || paidAmount === null || !firstDocumentDate ||
    !lastDocumentDate || firstDocumentDate > lastDocumentDate ||
    row.aggregation_policy !== AGGREGATION_POLICY ||
    row.methodology_version !== RANKING_METHODOLOGY
  ) return null;
  return {
    rankPosition: expectedPosition,
    authorKind,
    authorKey,
    authorName,
    amendmentCount,
    documentCount,
    committedAmount,
    paidAmount,
    firstDocumentDate,
    lastDocumentDate,
    aggregationPolicy: AGGREGATION_POLICY,
    methodologyVersion: RANKING_METHODOLOGY,
  };
}

export function parseCguFederalAmendmentDocumentRankingRows(rows) {
  if (!Array.isArray(rows)) return null;
  const parsed = rows.map((row, index) => parseRankingRow(row, index + 1));
  return parsed.some((row) => row === null) ? null : parsed;
}

export function parseCguFederalAmendmentDocumentStudyRows(rows) {
  if (!Array.isArray(rows) || rows.length !== 1) return null;
  const row = rows[0];
  if (typeof row !== "object" || row === null) return null;
  const documents = parseCguFederalAmendmentDocumentRows(row.items);
  const totalCount = integer(row.total_count, 0);
  const catalogCount = integer(row.catalog_count, 0);
  if (
    documents === null || totalCount === null || catalogCount === null ||
    totalCount > catalogCount || documents.length > totalCount ||
    row.methodology_version !== STUDY_METHODOLOGY ||
    !Array.isArray(row.available_years) ||
    !row.available_years.every((year) => integer(year, 2021) !== null) ||
    !Array.isArray(row.available_stages) ||
    !row.available_stages.every((stage) => EXPENSE_STAGES.has(stage)) ||
    !Array.isArray(row.available_authors)
  ) return null;
  const availableAuthors = row.available_authors.map((author) => {
    if (typeof author !== "object" || author === null) return null;
    const authorKey = requiredText(author.author_key);
    const authorName = requiredText(author.author_name);
    return authorKey && authorName ? { authorKey, authorName } : null;
  });
  if (availableAuthors.some((author) => author === null)) return null;
  return {
    documents,
    totalCount,
    catalogCount,
    availableYears: row.available_years,
    availableAuthors,
    availableStages: row.available_stages,
    methodologyVersion: STUDY_METHODOLOGY,
  };
}
