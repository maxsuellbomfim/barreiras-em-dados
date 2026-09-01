const STATUSES = new Set([
  "published",
  "section_absent",
  "section_incomplete",
  "source_conflict",
  "document_not_found",
  "document_not_confirmed",
]);
const PERIOD_START = /^(\d{4})-(\d{2})-01$/;
const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;
const SHA256 = /^[0-9a-f]{64}$/;
const ROW_KEYS = new Set([
  "coverageId",
  "fiscalYear",
  "periodStart",
  "periodEnd",
  "coverageStatus",
  "sourceUrl",
  "documentArtifactSha256",
  "searchEvidenceSha256",
  "evidenceArtifactCount",
  "conflictPreviousPeriodAmount",
  "conflictReportedPriorAmount",
  "conflictDifferenceAmount",
  "checkedAt",
  "methodologyVersion",
]);

export function obligationCoverageStatusLabel(status) {
  if (status === "published") return "Valor publicado";
  if (status === "section_absent") return "Seção ausente";
  if (status === "section_incomplete") return "Seção incompleta";
  if (status === "source_conflict") return "Divergência oficial";
  if (status === "document_not_found") return "Documento não localizado";
  if (status === "document_not_confirmed") return "Documento não confirmado";
  if (status === "unclassified") return "Não classificado";
  return "Fora do período acompanhado";
}

function optionalText(value) {
  return value === null || (typeof value === "string" && value.trim()) ? value : undefined;
}

function parsePeriod(row, startYear) {
  if (!row || typeof row !== "object" || Array.isArray(row)) return null;
  const keys = Object.keys(row);
  if (keys.length !== ROW_KEYS.size || keys.some((key) => !ROW_KEYS.has(key))) return null;
  const match = typeof row.periodStart === "string" ? PERIOD_START.exec(row.periodStart) : null;
  const sourceUrl = optionalText(row.sourceUrl);
  const documentHash = optionalText(row.documentArtifactSha256);
  const searchHash = optionalText(row.searchEvidenceSha256);
  const checkedAt = optionalText(row.checkedAt);
  if (
    !match ||
    typeof row.coverageId !== "string" ||
    !row.coverageId.trim() ||
    !Number.isSafeInteger(row.fiscalYear) ||
    typeof row.periodEnd !== "string" ||
    !ISO_DATE.test(row.periodEnd) ||
    !STATUSES.has(row.coverageStatus) ||
    sourceUrl === undefined ||
    (sourceUrl !== null && !sourceUrl.startsWith("https://")) ||
    documentHash === undefined ||
    (documentHash !== null && !SHA256.test(documentHash)) ||
    searchHash === undefined ||
    (searchHash !== null && !SHA256.test(searchHash)) ||
    checkedAt === undefined ||
    (checkedAt !== null && Number.isNaN(Date.parse(checkedAt))) ||
    row.methodologyVersion !== "public-obligation-coverage/1.2.0"
  ) return null;

  const year = Number(match[1]);
  const month = Number(match[2]);
  if (year < startYear || month < 1 || month > 12 || row.fiscalYear !== year) return null;
  if (
    row.evidenceArtifactCount !== null &&
    (!Number.isSafeInteger(row.evidenceArtifactCount) || row.evidenceArtifactCount < 1)
  ) return null;
  if (
    !["document_not_found", "document_not_confirmed"].includes(row.coverageStatus) &&
    (sourceUrl === null || documentHash === null || checkedAt === null)
  ) return null;
  if (
    row.coverageStatus === "document_not_found" &&
    (sourceUrl === null || documentHash !== null || searchHash === null ||
      row.evidenceArtifactCount === null || checkedAt === null)
  ) return null;
  const conflictAmounts = [
    row.conflictPreviousPeriodAmount,
    row.conflictReportedPriorAmount,
    row.conflictDifferenceAmount,
  ];
  if (
    row.coverageStatus === "source_conflict"
      ? conflictAmounts.some((value) => typeof value !== "string" || !value.trim())
      : conflictAmounts.some((value) => value !== null)
  ) return null;
  return { year, month, key: `${year}-${String(month).padStart(2, "0")}` };
}

export function buildObligationCoverageMatrix(rows, startYear = 2021) {
  if (!Array.isArray(rows) || !Number.isInteger(startYear) || startYear < 1900 || startYear > 2200) {
    return null;
  }
  if (rows.length === 0) return { latestPeriod: null, years: [] };
  const byPeriod = new Map();
  let latestPeriod = null;
  for (const row of rows) {
    const period = parsePeriod(row, startYear);
    if (!period || byPeriod.has(period.key)) return null;
    byPeriod.set(period.key, row);
    if (latestPeriod === null || period.key > latestPeriod) latestPeriod = period.key;
  }
  const latestYear = Number(latestPeriod.slice(0, 4));
  const latestMonth = Number(latestPeriod.slice(5, 7));
  return {
    latestPeriod,
    years: Array.from({ length: latestYear - startYear + 1 }, (_, yearIndex) => {
      const year = latestYear - yearIndex;
      return {
        year,
        months: Array.from({ length: 12 }, (_, monthIndex) => {
          const month = monthIndex + 1;
          const key = `${year}-${String(month).padStart(2, "0")}`;
          const row = byPeriod.get(key) ?? null;
          return {
            month,
            status: year === latestYear && month > latestMonth
              ? "not_due"
              : row?.coverageStatus ?? "unclassified",
            row,
          };
        }),
      };
    }),
  };
}

export function parseObligationCoverageApiPayload(payload) {
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) return null;
  if (payload.state === "unavailable") {
    return Object.keys(payload).length === 1 ? { state: "unavailable" } : null;
  }
  if (
    payload.state !== "available" ||
    Object.keys(payload).length !== 2 ||
    !Array.isArray(payload.rows) ||
    buildObligationCoverageMatrix(payload.rows) === null
  ) return null;
  return { state: "available", rows: payload.rows };
}
