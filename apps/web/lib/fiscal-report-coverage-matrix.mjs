const SHA256 = /^[0-9a-f]{64}$/;
const ISO_DATE = /^(\d{4})-(\d{2})-(\d{2})$/;
const KEYS = new Set([
  "resource",
  "fiscalYear",
  "referenceMonth",
  "documentUrl",
  "documentPreserved",
  "artifactSha256",
  "collectedAt",
]);
const PERIODS = [
  { resource: "rreo", referenceMonth: 2, shortLabel: "1º bim." },
  { resource: "rreo", referenceMonth: 4, shortLabel: "2º bim." },
  { resource: "rreo", referenceMonth: 6, shortLabel: "3º bim." },
  { resource: "rreo", referenceMonth: 8, shortLabel: "4º bim." },
  { resource: "rreo", referenceMonth: 10, shortLabel: "5º bim." },
  { resource: "rreo", referenceMonth: 12, shortLabel: "6º bim." },
  { resource: "rgf", referenceMonth: 4, shortLabel: "1º quad." },
  { resource: "rgf", referenceMonth: 8, shortLabel: "2º quad." },
  { resource: "rgf", referenceMonth: 12, shortLabel: "3º quad." },
];

function parseToday(value) {
  const match = typeof value === "string" ? ISO_DATE.exec(value) : null;
  if (!match) return null;
  const timestamp = Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3]));
  const parsed = new Date(timestamp);
  return parsed.getUTCFullYear() === Number(match[1]) &&
    parsed.getUTCMonth() === Number(match[2]) - 1 &&
    parsed.getUTCDate() === Number(match[3])
    ? timestamp
    : null;
}

function parseEntry(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const keys = Object.keys(value);
  if (keys.length !== KEYS.size || keys.some((key) => !KEYS.has(key))) return null;
  if (
    (value.resource !== "rreo" && value.resource !== "rgf") ||
    !Number.isSafeInteger(value.fiscalYear) ||
    value.fiscalYear < 2021 ||
    value.fiscalYear > 2200 ||
    !Number.isSafeInteger(value.referenceMonth) ||
    !PERIODS.some((period) =>
      period.resource === value.resource && period.referenceMonth === value.referenceMonth) ||
    typeof value.documentUrl !== "string" ||
    !value.documentUrl.startsWith("https://") ||
    typeof value.documentPreserved !== "boolean" ||
    (value.artifactSha256 !== null &&
      (typeof value.artifactSha256 !== "string" || !SHA256.test(value.artifactSha256))) ||
    (value.documentPreserved && value.artifactSha256 === null) ||
    typeof value.collectedAt !== "string" ||
    Number.isNaN(Date.parse(value.collectedAt))
  ) return null;
  return value;
}

export function toFiscalCoverageEntry(document) {
  if (!document || typeof document !== "object" || Array.isArray(document)) return null;
  const referenceMonth = resolveReferenceMonth(document);
  return parseEntry({
    resource: document.sourceResource,
    fiscalYear: document.fiscalYear,
    referenceMonth,
    documentUrl: document.documentUrl,
    documentPreserved: document.documentPreserved,
    artifactSha256: document.documentArtifactSha256,
    collectedAt: document.collectedAt,
  });
}

function titleReferenceMonth(resource, title, description) {
  const combined = [title, description]
    .filter((value) => typeof value === "string")
    .join(" ");
  const match = /\b([1-6])\s*(?:º|°|o)?\s*(bimestre|quadrimestre)\b/i.exec(combined);
  if (!match) return null;
  const ordinal = Number(match[1]);
  const namedResource = match[2].toLowerCase() === "bimestre" ? "rreo" : "rgf";
  if (namedResource !== resource) return Number.NaN;
  const month = namedResource === "rreo" ? ordinal * 2 : ordinal * 4;
  return month <= 12 ? month : Number.NaN;
}

function dateReferenceMonth(resource, fiscalYear, referenceDate) {
  const match = typeof referenceDate === "string" ? ISO_DATE.exec(referenceDate) : null;
  if (!match || !Number.isSafeInteger(fiscalYear)) return null;
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  if (year === fiscalYear + 1 && month >= 1 && month <= (resource === "rreo" ? 2 : 3)) {
    return 12;
  }
  if (year !== fiscalYear) return null;
  if (resource === "rgf") {
    if (month === 5 || month === 6) return 4;
    if (month === 9 || month === 10) return 8;
    if (month === 12) return 12;
    return null;
  }
  if (month === 2 || month === 3) return 2;
  if (month === 4) return day <= 15 ? 2 : 4;
  if (month === 5) return 4;
  if (month === 6) return day <= 15 ? 4 : 6;
  if (month === 7 || month === 8) return 6;
  if (month === 9 || month === 10) return 8;
  if (month === 11) return 10;
  if (month === 12) return day <= 15 ? 10 : 12;
  return null;
}

function resolveReferenceMonth(document) {
  const explicit = Number.isSafeInteger(document.referenceMonth)
    ? document.referenceMonth
    : null;
  const fromTitle = titleReferenceMonth(
    document.sourceResource,
    document.title,
    document.description,
  );
  const fromDate = dateReferenceMonth(
    document.sourceResource,
    document.fiscalYear,
    document.referenceDate,
  );
  const candidates = [explicit, fromTitle, fromDate].filter((value) => value !== null);
  if (candidates.some((value) => !Number.isSafeInteger(value))) return null;
  return new Set(candidates).size === 1 ? candidates[0] : null;
}

function dueTimestamp(year, referenceMonth) {
  const periodEnd = Date.UTC(year, referenceMonth, 0);
  return periodEnd + 30 * 24 * 60 * 60 * 1_000;
}

function chooseEvidence(entries) {
  return [...entries].sort((left, right) => {
    if (left.documentPreserved !== right.documentPreserved) {
      return left.documentPreserved ? -1 : 1;
    }
    return right.collectedAt.localeCompare(left.collectedAt);
  })[0];
}

export function fiscalReportCoverageStatusLabel(status) {
  if (status === "preserved") return "PDF preservado";
  if (status === "catalogued") return "Encontrado; PDF pendente";
  if (status === "not_found") return "Não localizado após o prazo";
  return "Prazo ainda não encerrado";
}

export function buildFiscalReportCoverageMatrix(entries, options = {}) {
  const startYear = options.startYear ?? 2021;
  const today = options.today ?? new Date().toISOString().slice(0, 10);
  const todayTimestamp = parseToday(today);
  if (
    !Array.isArray(entries) ||
    !Number.isSafeInteger(startYear) ||
    startYear < 2021 ||
    startYear > 2200 ||
    todayTimestamp === null
  ) return null;
  const currentYear = Number(today.slice(0, 4));
  if (startYear > currentYear) return null;

  const byPeriod = new Map();
  for (const value of entries) {
    const parsed = parseEntry(value);
    if (!parsed) return null;
    const key = `${parsed.resource}:${parsed.fiscalYear}:${parsed.referenceMonth}`;
    const group = byPeriod.get(key) ?? [];
    group.push(parsed);
    byPeriod.set(key, group);
  }

  const years = Array.from({ length: currentYear - startYear + 1 }, (_, index) => {
    const year = currentYear - index;
    return {
      year,
      periods: PERIODS.map((column) => {
        const key = `${column.resource}:${year}:${column.referenceMonth}`;
        const evidence = byPeriod.get(key) ?? [];
        const entry = evidence.length > 0 ? chooseEvidence(evidence) : null;
        const status = entry
          ? entry.documentPreserved ? "preserved" : "catalogued"
          : todayTimestamp > dueTimestamp(year, column.referenceMonth)
            ? "not_found"
            : "not_due";
        return { ...column, status, entry, evidenceCount: evidence.length };
      }),
    };
  });

  return { columns: PERIODS, years };
}

export function parseFiscalReportCoverageApiPayload(payload) {
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) return null;
  if (payload.state === "unavailable") {
    return Object.keys(payload).length === 1 ? { state: "unavailable" } : null;
  }
  if (
    payload.state !== "available" ||
    Object.keys(payload).length !== 2 ||
    !Array.isArray(payload.entries) ||
    buildFiscalReportCoverageMatrix(payload.entries) === null
  ) return null;
  return { state: "available", entries: payload.entries };
}
