const STATUSES = new Set([
  "published",
  "document_not_found",
  "source_conflict",
  "processing_pending",
]);
const PERIOD = /^(\d{4})-(\d{2})-01$/;
const SHA256 = /^[0-9a-f]{64}$/;
const KEYS = new Set([
  "referenceMonth",
  "coverageStatus",
  "coverageNote",
  "catalogDocumentCount",
  "preservedDocumentCount",
  "sourceUrl",
  "artifactSha256",
  "catalogCheckedAt",
  "methodologyVersion",
]);

export function payrollCoverageStatusLabel(status) {
  if (status === "published") return "Publicado";
  if (status === "processing_pending") return "Em validação";
  if (status === "source_conflict") return "Conflito de ciclos";
  if (status === "document_not_found") return "Documento não localizado";
  if (status === "unclassified") return "Não classificado";
  return "Fora do período acompanhado";
}

function parsePeriod(row, startYear) {
  if (!row || typeof row !== "object" || Array.isArray(row)) return null;
  const keys = Object.keys(row);
  const match = typeof row.referenceMonth === "string" ? PERIOD.exec(row.referenceMonth) : null;
  if (
    keys.length !== KEYS.size ||
    keys.some((key) => !KEYS.has(key)) ||
    !match ||
    !STATUSES.has(row.coverageStatus) ||
    typeof row.coverageNote !== "string" ||
    !row.coverageNote.trim() ||
    !Number.isSafeInteger(row.catalogDocumentCount) ||
    row.catalogDocumentCount < 0 ||
    !Number.isSafeInteger(row.preservedDocumentCount) ||
    row.preservedDocumentCount < 0 ||
    row.preservedDocumentCount > row.catalogDocumentCount ||
    typeof row.sourceUrl !== "string" ||
    !row.sourceUrl.startsWith("https://") ||
    (row.artifactSha256 !== null &&
      (typeof row.artifactSha256 !== "string" || !SHA256.test(row.artifactSha256))) ||
    typeof row.catalogCheckedAt !== "string" ||
    Number.isNaN(Date.parse(row.catalogCheckedAt)) ||
    row.methodologyVersion !== "payroll-coverage/1.0.0"
  ) return null;
  if (
    (row.coverageStatus === "document_not_found" &&
      (row.catalogDocumentCount !== 0 || row.preservedDocumentCount !== 0 || row.artifactSha256 !== null)) ||
    (row.coverageStatus !== "document_not_found" && row.catalogDocumentCount < 1) ||
    (row.artifactSha256 !== null && row.preservedDocumentCount < 1)
  ) return null;
  const year = Number(match[1]);
  const month = Number(match[2]);
  return year >= startYear && month >= 1 && month <= 12
    ? { year, month, key: `${year}-${String(month).padStart(2, "0")}` }
    : null;
}

export function buildPayrollCoverageMatrix(rows, startYear = 2021) {
  if (!Array.isArray(rows) || !Number.isInteger(startYear) || startYear < 1900 || startYear > 2200) return null;
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

export function parsePayrollCoverageApiPayload(payload) {
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) return null;
  if (payload.state === "unavailable") {
    return Object.keys(payload).length === 1 ? { state: "unavailable" } : null;
  }
  if (
    payload.state !== "available" ||
    Object.keys(payload).length !== 2 ||
    !Array.isArray(payload.rows) ||
    buildPayrollCoverageMatrix(payload.rows) === null
  ) return null;
  return { state: "available", rows: payload.rows };
}
