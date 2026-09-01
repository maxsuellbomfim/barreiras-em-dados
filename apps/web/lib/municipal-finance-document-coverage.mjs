const SHA256 = /^[0-9a-f]{64}$/;
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const ISO_DATE = /^(\d{4})-(\d{2})-(\d{2})$/;
const ENTRY_KEYS = new Set([
  "documentId",
  "resource",
  "fiscalYear",
  "referenceMonth",
  "documentUrl",
  "documentPreserved",
  "artifactSha256",
  "collectedAt",
]);

export const MUNICIPAL_FINANCE_DOCUMENT_FAMILIES = [
  { resource: "balancetes", shortLabel: "Balancete" },
  { resource: "pdc-resumo-execucao-da-receita", shortLabel: "Receita" },
  { resource: "pdc-resumo-execucao-da-despesa", shortLabel: "Despesa" },
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
  if (keys.length !== ENTRY_KEYS.size || keys.some((key) => !ENTRY_KEYS.has(key))) return null;
  if (
    typeof value.documentId !== "string" ||
    !UUID.test(value.documentId) ||
    !MUNICIPAL_FINANCE_DOCUMENT_FAMILIES.some(({ resource }) => resource === value.resource) ||
    !Number.isSafeInteger(value.fiscalYear) ||
    value.fiscalYear < 2021 ||
    value.fiscalYear > 2200 ||
    !Number.isSafeInteger(value.referenceMonth) ||
    value.referenceMonth < 1 ||
    value.referenceMonth > 12 ||
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

export function toMunicipalFinanceDocumentCoverageEntry(document) {
  if (!document || typeof document !== "object" || Array.isArray(document)) return null;
  return parseEntry({
    documentId: document.documentId,
    resource: document.sourceResource,
    fiscalYear: document.fiscalYear,
    referenceMonth: document.referenceMonth,
    documentUrl: document.documentUrl,
    documentPreserved: document.documentPreserved,
    artifactSha256: document.documentArtifactSha256,
    collectedAt: document.collectedAt,
  });
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
    const collected = right.collectedAt.localeCompare(left.collectedAt);
    return collected !== 0 ? collected : right.documentId.localeCompare(left.documentId);
  })[0];
}

export function municipalFinanceDocumentCoverageStatusLabel(status) {
  if (status === "preserved") return "PDF preservado";
  if (status === "catalogued") return "Encontrado; PDF pendente";
  if (status === "not_listed") return "Não localizado no catálogo consultado";
  return "Prazo ainda não encerrado";
}

export function buildMunicipalFinanceDocumentCoverage(entries, options = {}) {
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
    const months = Array.from({ length: 12 }, (_, monthIndex) => {
      const referenceMonth = monthIndex + 1;
      const families = MUNICIPAL_FINANCE_DOCUMENT_FAMILIES.map((family) => {
        const key = `${family.resource}:${year}:${referenceMonth}`;
        const evidence = byPeriod.get(key) ?? [];
        const entry = evidence.length > 0 ? chooseEvidence(evidence) : null;
        const status = entry
          ? entry.documentPreserved ? "preserved" : "catalogued"
          : todayTimestamp > dueTimestamp(year, referenceMonth)
            ? "not_listed"
            : "not_due";
        return { ...family, status, entry, evidenceCount: evidence.length };
      });
      return { referenceMonth, families };
    });
    return { year, months };
  });
  return { families: MUNICIPAL_FINANCE_DOCUMENT_FAMILIES, years };
}

export function parseMunicipalFinanceDocumentCoverageApiPayload(payload) {
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) return null;
  if (payload.state === "unavailable") {
    return Object.keys(payload).length === 1 ? { state: "unavailable" } : null;
  }
  if (
    payload.state !== "available" ||
    Object.keys(payload).length !== 2 ||
    !Array.isArray(payload.entries) ||
    buildMunicipalFinanceDocumentCoverage(payload.entries) === null
  ) return null;
  return { state: "available", entries: payload.entries };
}
