const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;
const SHA256 = /^[0-9a-f]{64}$/;
const DECIMAL = /^\d+(?:\.\d{1,2})?$/;
const LEGACY_PARSER_VERSION = "payroll-report-aggregate/1.0.0";
const MONTHLY_PROJECTION_VERSION = "payroll-monthly-total/1.0.0";
const COMPONENT_PARSER_VERSIONS = new Set([
  LEGACY_PARSER_VERSION,
  "payroll-report-aggregate/1.1.0",
  "payroll-report-aggregate/1.2.0",
  "payroll-report-aggregate/1.3.0",
]);
const PAYROLL_CYCLES = new Set([
  "regular",
  "thirteenth_advance",
  "thirteenth_final",
]);

function text(value) {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function integer(value, minimum = 0) {
  return Number.isSafeInteger(value) && value >= minimum ? value : null;
}

function decimal(value) {
  if (typeof value === "string" && DECIMAL.test(value.trim())) {
    const [whole, fraction = ""] = value.trim().split(".");
    return `${whole}.${fraction.padEnd(2, "0")}`;
  }
  if (typeof value !== "number" || !Number.isFinite(value) || value < 0) {
    return null;
  }
  const roundedCents = Math.round(value * 100);
  if (!Number.isSafeInteger(roundedCents)) return null;
  const normalized = roundedCents / 100;
  const tolerance = Number.EPSILON * Math.max(1, Math.abs(value)) * 4;
  return Math.abs(value - normalized) <= tolerance
    ? normalized.toFixed(2)
    : null;
}

function cents(value) {
  const [whole, fraction] = value.split(".");
  return BigInt(whole) * 100n + BigInt(fraction);
}

function sourceDocument(value) {
  if (typeof value !== "object" || value === null) return null;
  const payrollCycle = text(value.payroll_cycle);
  const sourceUrl = text(value.source_url);
  const artifactSha256 = text(value.artifact_sha256);
  const sourceRetrievedAt = text(value.source_retrieved_at);
  const parserVersion = text(value.parser_version);
  if (
    payrollCycle === null ||
    !PAYROLL_CYCLES.has(payrollCycle) ||
    sourceUrl === null ||
    !sourceUrl.startsWith("https://") ||
    artifactSha256 === null ||
    !SHA256.test(artifactSha256) ||
    sourceRetrievedAt === null ||
    Number.isNaN(Date.parse(sourceRetrievedAt)) ||
    parserVersion === null ||
    !COMPONENT_PARSER_VERSIONS.has(parserVersion)
  ) {
    return null;
  }
  return {
    payrollCycle,
    sourceUrl,
    artifactSha256,
    sourceRetrievedAt,
    parserVersion,
  };
}

export function parsePublicPayrollRow(row) {
  if (typeof row !== "object" || row === null) return null;
  const referenceMonth = text(row.reference_month);
  const publicBodyName = text(row.public_body_name);
  const employeeCount = integer(row.employee_count, 1);
  const grossAmount = decimal(row.gross_amount);
  const deductionAmount = decimal(row.deduction_amount);
  const netAmount = decimal(row.net_amount);
  const subtotalCount = integer(row.subtotal_count, 1);
  const sourceUrl = text(row.source_url);
  const artifactSha256 = text(row.artifact_sha256);
  const sourceRetrievedAt = text(row.source_retrieved_at);
  const parserVersion = text(row.parser_version);
  if (
    referenceMonth === null ||
    !ISO_DATE.test(referenceMonth) ||
    publicBodyName === null ||
    employeeCount === null ||
    grossAmount === null ||
    deductionAmount === null ||
    netAmount === null ||
    subtotalCount === null ||
    sourceUrl === null ||
    !sourceUrl.startsWith("https://") ||
    artifactSha256 === null ||
    !SHA256.test(artifactSha256) ||
    sourceRetrievedAt === null ||
    Number.isNaN(Date.parse(sourceRetrievedAt)) ||
    cents(grossAmount) - cents(deductionAmount) !== cents(netAmount)
  ) {
    return null;
  }
  let documentCount;
  let sourceDocuments;
  if (parserVersion === LEGACY_PARSER_VERSION) {
    documentCount = 1;
    sourceDocuments = [
      {
        payrollCycle: "regular",
        sourceUrl,
        artifactSha256,
        sourceRetrievedAt,
        parserVersion,
      },
    ];
  } else if (parserVersion === MONTHLY_PROJECTION_VERSION) {
    documentCount = integer(row.document_count, 1);
    if (!Array.isArray(row.source_documents) || documentCount === null) {
      return null;
    }
    sourceDocuments = row.source_documents.map(sourceDocument);
    if (
      sourceDocuments.some((document) => document === null) ||
      sourceDocuments.length !== documentCount ||
      new Set(sourceDocuments.map((document) => document.payrollCycle)).size !==
        documentCount ||
      sourceDocuments.filter(
        (document) => document.payrollCycle === "regular",
      ).length !== 1
    ) {
      return null;
    }
    const regularDocument = sourceDocuments.find(
      (document) => document.payrollCycle === "regular",
    );
    if (
      regularDocument.sourceUrl !== sourceUrl ||
      regularDocument.artifactSha256 !== artifactSha256
    ) {
      return null;
    }
  } else {
    return null;
  }
  return {
    referenceMonth,
    publicBodyName,
    employeeCount,
    grossAmount,
    deductionAmount,
    netAmount,
    subtotalCount,
    sourceUrl,
    artifactSha256,
    sourceRetrievedAt,
    parserVersion,
    documentCount,
    sourceDocuments,
  };
}

export async function getPublicPayrollMonths(pageSize = 24) {
  const supabaseUrl = process.env.PUBLIC_DATA_SUPABASE_URL?.trim();
  const publishableKey =
    process.env.PUBLIC_DATA_SUPABASE_PUBLISHABLE_KEY?.trim();
  if (
    !Number.isSafeInteger(pageSize) ||
    pageSize < 1 ||
    pageSize > 60 ||
    !supabaseUrl?.startsWith("https://") ||
    !publishableKey?.startsWith("sb_publishable_")
  ) {
    return { state: "unavailable" };
  }
  try {
    const response = await fetch(
      `${supabaseUrl}/rest/v1/rpc/get_public_payroll_months`,
      {
        method: "POST",
        headers: {
          Accept: "application/json",
          "Accept-Profile": "api",
          apikey: publishableKey,
          "Content-Profile": "api",
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ page_size: pageSize }),
        next: { revalidate: 300 },
        signal: AbortSignal.timeout(5_000),
      },
    );
    if (!response.ok) return { state: "unavailable" };
    const payload = await response.json();
    if (!Array.isArray(payload)) return { state: "unavailable" };
    const months = [];
    for (const row of payload) {
      const parsed = parsePublicPayrollRow(row);
      if (parsed === null) return { state: "unavailable" };
      months.push(parsed);
    }
    return { state: "available", months };
  } catch {
    return { state: "unavailable" };
  }
}
