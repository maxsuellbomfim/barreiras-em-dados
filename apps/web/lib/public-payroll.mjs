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
  "payroll-report-aggregate/1.4.0",
]);
const PAYROLL_CYCLES = new Set([
  "regular",
  "thirteenth_advance",
  "thirteenth_final",
]);
const PAYROLL_COVERAGE_STATUSES = new Set([
  "published",
  "document_not_found",
  "source_conflict",
  "processing_pending",
]);
const PAYROLL_COVERAGE_VERSION = "payroll-coverage/1.0.0";
const NONPAYROLL_WORKFORCE_CATEGORIES = new Map([
  ["interns", "Estagiários"],
  ["outsourced_workers", "Terceirizados"],
]);
const NONPAYROLL_WORKFORCE_STATUSES = new Set([
  "document_preserved",
  "catalogued",
  "not_listed",
]);
const NONPAYROLL_WORKFORCE_VERSION =
  "nonpayroll-workforce-coverage/1.0.0";
const NONPAYROLL_WORKFORCE_FIELDS = [
  "artifact_sha256",
  "catalog_checked_at",
  "catalog_document_count",
  "category_label",
  "coverage_note",
  "coverage_status",
  "methodology_version",
  "preserved_document_count",
  "reference_month",
  "source_url",
  "workforce_category",
];
const PAYROLL_REGIME_VERSION = "payroll-regime-monthly/1.0.0";
const PAYROLL_REGIME_LABELS = new Map([
  ["statutory", "Estatutários"],
  ["commissioned", "Cargos em comissão"],
  ["selection_process", "Processo seletivo"],
  ["ceded", "Cedidos"],
  ["political_agent", "Agentes políticos"],
  ["guardianship_council", "Conselho tutelar"],
  ["pensioner", "Pensionistas"],
  ["temporary_worker", "Trabalhadores temporários"],
]);
const PAYROLL_REGIME_FIELDS = [
  "deduction_amount",
  "employee_count",
  "gross_amount",
  "methodology_version",
  "net_amount",
  "reference_month",
  "regime_code",
  "regime_label",
  "source_document_count",
];
const PAYROLL_COMPENSATION_VERSION = "payroll-compensation-monthly/1.0.0";
const PAYROLL_COMPENSATION_LABELS = new Map([
  ["up_to_1500", "Até R$ 1.500"],
  ["from_1500_01_to_3000", "De R$ 1.500,01 a R$ 3 mil"],
  ["from_3000_01_to_5000", "De R$ 3.000,01 a R$ 5 mil"],
  ["from_5000_01_to_10000", "De R$ 5.000,01 a R$ 10 mil"],
  ["from_10000_01_to_20000", "De R$ 10.000,01 a R$ 20 mil"],
  ["above_20000", "Acima de R$ 20 mil"],
]);
const PAYROLL_COMPENSATION_FIELDS = [
  "average_gross_amount",
  "band_code",
  "band_label",
  "employee_count",
  "gross_amount",
  "maximum_gross_amount",
  "methodology_version",
  "reference_month",
];

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

function decimalFromCents(value) {
  const whole = value / 100n;
  const fraction = (value % 100n).toString().padStart(2, "0");
  return `${whole}.${fraction}`;
}

export function summarizePublicPayrollYears(months) {
  if (!Array.isArray(months) || months.length === 0) return [];

  const latestReferenceMonth = months.reduce(
    (latest, month) =>
      month.referenceMonth > latest ? month.referenceMonth : latest,
    months[0].referenceMonth,
  );
  const latestYear = Number(latestReferenceMonth.slice(0, 4));
  const latestMonthNumber = Number(latestReferenceMonth.slice(5, 7));
  const years = new Map();

  for (const month of months) {
    const year = Number(month.referenceMonth.slice(0, 4));
    const current = years.get(year) ?? {
      publishedMonthCount: 0,
      grossCents: 0n,
      deductionCents: 0n,
      netCents: 0n,
    };
    current.publishedMonthCount += 1;
    current.grossCents += cents(month.grossAmount);
    current.deductionCents += cents(month.deductionAmount);
    current.netCents += cents(month.netAmount);
    years.set(year, current);
  }

  return [...years.entries()]
    .sort(([left], [right]) => right - left)
    .map(([year, totals]) => {
      const expectedMonthCount = year === latestYear ? latestMonthNumber : 12;
      return {
        year,
        publishedMonthCount: totals.publishedMonthCount,
        expectedMonthCount,
        isComplete: totals.publishedMonthCount === expectedMonthCount,
        grossAmount: decimalFromCents(totals.grossCents),
        deductionAmount: decimalFromCents(totals.deductionCents),
        netAmount: decimalFromCents(totals.netCents),
      };
    });
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

export function parsePublicPayrollCoverageRow(row) {
  if (typeof row !== "object" || row === null) return null;
  const referenceMonth = text(row.reference_month);
  const coverageStatus = text(row.coverage_status);
  const coverageNote = text(row.coverage_note);
  const catalogDocumentCount = integer(row.catalog_document_count);
  const preservedDocumentCount = integer(row.preserved_document_count);
  const sourceUrl = text(row.source_url);
  const artifactSha256 = text(row.artifact_sha256);
  const catalogCheckedAt = text(row.catalog_checked_at);
  const methodologyVersion = text(row.methodology_version);
  if (
    referenceMonth === null ||
    !ISO_DATE.test(referenceMonth) ||
    coverageStatus === null ||
    !PAYROLL_COVERAGE_STATUSES.has(coverageStatus) ||
    coverageNote === null ||
    catalogDocumentCount === null ||
    preservedDocumentCount === null ||
    preservedDocumentCount > catalogDocumentCount ||
    sourceUrl === null ||
    !sourceUrl.startsWith("https://") ||
    (artifactSha256 !== null && !SHA256.test(artifactSha256)) ||
    catalogCheckedAt === null ||
    Number.isNaN(Date.parse(catalogCheckedAt)) ||
    methodologyVersion !== PAYROLL_COVERAGE_VERSION
  ) {
    return null;
  }
  if (
    (coverageStatus === "document_not_found" &&
      (catalogDocumentCount !== 0 || preservedDocumentCount !== 0)) ||
    (coverageStatus !== "document_not_found" && catalogDocumentCount < 1) ||
    (artifactSha256 !== null && preservedDocumentCount < 1)
  ) {
    return null;
  }
  return {
    referenceMonth,
    coverageStatus,
    coverageNote,
    catalogDocumentCount,
    preservedDocumentCount,
    sourceUrl,
    artifactSha256,
    catalogCheckedAt,
    methodologyVersion,
  };
}

export function parsePublicNonpayrollWorkforceCoverageRow(row) {
  if (typeof row !== "object" || row === null) return null;
  const keys = Object.keys(row).sort();
  if (
    keys.length !== NONPAYROLL_WORKFORCE_FIELDS.length ||
    keys.some((key, index) => key !== NONPAYROLL_WORKFORCE_FIELDS[index])
  ) {
    return null;
  }
  const referenceMonth = text(row.reference_month);
  const workforceCategory = text(row.workforce_category);
  const categoryLabel = text(row.category_label);
  const coverageStatus = text(row.coverage_status);
  const coverageNote = text(row.coverage_note);
  const catalogDocumentCount = integer(row.catalog_document_count);
  const preservedDocumentCount = integer(row.preserved_document_count);
  const sourceUrl = text(row.source_url);
  const artifactSha256 = text(row.artifact_sha256);
  const catalogCheckedAt = text(row.catalog_checked_at);
  const methodologyVersion = text(row.methodology_version);
  if (
    referenceMonth === null ||
    !ISO_DATE.test(referenceMonth) ||
    workforceCategory === null ||
    NONPAYROLL_WORKFORCE_CATEGORIES.get(workforceCategory) !== categoryLabel ||
    coverageStatus === null ||
    !NONPAYROLL_WORKFORCE_STATUSES.has(coverageStatus) ||
    coverageNote === null ||
    catalogDocumentCount === null ||
    preservedDocumentCount === null ||
    preservedDocumentCount > catalogDocumentCount ||
    sourceUrl === null ||
    !sourceUrl.startsWith("https://") ||
    (artifactSha256 !== null && !SHA256.test(artifactSha256)) ||
    catalogCheckedAt === null ||
    Number.isNaN(Date.parse(catalogCheckedAt)) ||
    methodologyVersion !== NONPAYROLL_WORKFORCE_VERSION
  ) {
    return null;
  }
  const validState =
    (coverageStatus === "not_listed" &&
      catalogDocumentCount === 0 &&
      preservedDocumentCount === 0 &&
      artifactSha256 === null) ||
    (coverageStatus === "catalogued" &&
      catalogDocumentCount > 0 &&
      preservedDocumentCount === 0 &&
      artifactSha256 === null) ||
    (coverageStatus === "document_preserved" &&
      catalogDocumentCount > 0 &&
      preservedDocumentCount > 0 &&
      artifactSha256 !== null);
  if (!validState) return null;
  return {
    referenceMonth,
    workforceCategory,
    categoryLabel,
    coverageStatus,
    coverageNote,
    catalogDocumentCount,
    preservedDocumentCount,
    sourceUrl,
    artifactSha256,
    catalogCheckedAt,
    methodologyVersion,
  };
}

export function parsePublicPayrollRegimeRow(row) {
  if (typeof row !== "object" || row === null) return null;
  const keys = Object.keys(row).sort();
  if (
    keys.length !== PAYROLL_REGIME_FIELDS.length ||
    keys.some((key, index) => key !== PAYROLL_REGIME_FIELDS[index])
  ) {
    return null;
  }
  const referenceMonth = text(row.reference_month);
  const regimeCode = text(row.regime_code);
  const regimeLabel = text(row.regime_label);
  const employeeCount = integer(row.employee_count);
  const grossAmount = decimal(row.gross_amount);
  const deductionAmount = decimal(row.deduction_amount);
  const netAmount = decimal(row.net_amount);
  const sourceDocumentCount = integer(row.source_document_count, 1);
  const methodologyVersion = text(row.methodology_version);
  if (
    referenceMonth === null ||
    !ISO_DATE.test(referenceMonth) ||
    regimeCode === null ||
    PAYROLL_REGIME_LABELS.get(regimeCode) !== regimeLabel ||
    employeeCount === null ||
    grossAmount === null ||
    deductionAmount === null ||
    netAmount === null ||
    cents(grossAmount) - cents(deductionAmount) !== cents(netAmount) ||
    sourceDocumentCount === null ||
    methodologyVersion !== PAYROLL_REGIME_VERSION
  ) {
    return null;
  }
  return {
    referenceMonth,
    regimeCode,
    regimeLabel,
    employeeCount,
    grossAmount,
    deductionAmount,
    netAmount,
    sourceDocumentCount,
    methodologyVersion,
  };
}

export function payrollRegimeBreakdownMatchesMonth(rows, month) {
  if (!Array.isArray(rows) || rows.length < 1 || month === null) return false;
  if (
    rows.some((row) => row.referenceMonth !== month.referenceMonth) ||
    new Set(rows.map((row) => row.regimeCode)).size !== rows.length ||
    new Set(rows.map((row) => row.sourceDocumentCount)).size !== 1 ||
    rows[0].sourceDocumentCount !== month.documentCount
  ) {
    return false;
  }
  const total = (field) =>
    rows.reduce((sum, row) => sum + cents(row[field]), 0n);
  return (
    rows.reduce((sum, row) => sum + row.employeeCount, 0) ===
      month.employeeCount &&
    total("grossAmount") === cents(month.grossAmount) &&
    total("deductionAmount") === cents(month.deductionAmount) &&
    total("netAmount") === cents(month.netAmount)
  );
}

export function parsePublicPayrollCompensationRow(row) {
  if (typeof row !== "object" || row === null) return null;
  if (
    Object.keys(row).sort().join("|") !==
    PAYROLL_COMPENSATION_FIELDS.join("|")
  ) {
    return null;
  }
  const referenceMonth = text(row.reference_month);
  const bandCode = text(row.band_code);
  const bandLabel = text(row.band_label);
  const employeeCount = integer(row.employee_count, 1);
  const grossAmount = decimal(row.gross_amount);
  const averageGrossAmount = decimal(row.average_gross_amount);
  const maximumGrossAmount = decimal(row.maximum_gross_amount);
  const methodologyVersion = text(row.methodology_version);
  if (
    referenceMonth === null ||
    !ISO_DATE.test(referenceMonth) ||
    bandCode === null ||
    bandLabel === null ||
    PAYROLL_COMPENSATION_LABELS.get(bandCode) !== bandLabel ||
    employeeCount === null ||
    grossAmount === null ||
    averageGrossAmount === null ||
    maximumGrossAmount === null ||
    cents(maximumGrossAmount) < cents(averageGrossAmount) ||
    methodologyVersion !== PAYROLL_COMPENSATION_VERSION
  ) {
    return null;
  }
  return {
    referenceMonth,
    bandCode,
    bandLabel,
    employeeCount,
    grossAmount,
    averageGrossAmount,
    maximumGrossAmount,
    methodologyVersion,
  };
}

export function payrollCompensationMatchesMonth(rows, month) {
  if (!Array.isArray(rows) || rows.length < 1 || month === null) return false;
  return (
    rows.every((row) => row.referenceMonth === month.referenceMonth) &&
    new Set(rows.map((row) => row.bandCode)).size === rows.length &&
    new Set(rows.map((row) => row.averageGrossAmount)).size === 1 &&
    new Set(rows.map((row) => row.maximumGrossAmount)).size === 1 &&
    rows.reduce((sum, row) => sum + row.employeeCount, 0) ===
      month.employeeCount
  );
}

export async function getPublicPayrollMonths(maxMonths = 24) {
  const supabaseUrl = process.env.PUBLIC_DATA_SUPABASE_URL?.trim();
  const publishableKey =
    process.env.PUBLIC_DATA_SUPABASE_PUBLISHABLE_KEY?.trim();
  if (
    !Number.isSafeInteger(maxMonths) ||
    maxMonths < 1 ||
    maxMonths > 120 ||
    !supabaseUrl?.startsWith("https://") ||
    !publishableKey?.startsWith("sb_publishable_")
  ) {
    return { state: "unavailable" };
  }
  try {
    const months = [];
    const visitedMonths = new Set();
    let beforeMonth = null;
    while (visitedMonths.size < maxMonths) {
      const requestedPageSize = Math.min(24, maxMonths - visitedMonths.size);
      const response = await fetch(
        `${supabaseUrl}/rest/v1/rpc/get_public_payroll_months_page`,
        {
          method: "POST",
          headers: {
            Accept: "application/json",
            "Accept-Profile": "api",
            apikey: publishableKey,
            "Content-Profile": "api",
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            page_size: requestedPageSize,
            before_month: beforeMonth,
          }),
          next: { revalidate: 300 },
          signal: AbortSignal.timeout(5_000),
        },
      );
      if (!response.ok) return { state: "unavailable" };
      const payload = await response.json();
      if (!Array.isArray(payload)) return { state: "unavailable" };
      if (payload.length === 0) break;
      const pageMonths = new Set();
      for (const row of payload) {
        const parsed = parsePublicPayrollRow(row);
        if (
          parsed === null ||
          (beforeMonth !== null && parsed.referenceMonth >= beforeMonth)
        ) {
          return { state: "unavailable" };
        }
        pageMonths.add(parsed.referenceMonth);
        visitedMonths.add(parsed.referenceMonth);
        months.push(parsed);
      }
      if (pageMonths.size === 0) return { state: "unavailable" };
      beforeMonth = [...pageMonths].sort().at(0);
      if (pageMonths.size < requestedPageSize) break;
    }
    return { state: "available", months };
  } catch {
    return { state: "unavailable" };
  }
}

export async function getPublicPayrollCoverage(maxMonths = 120) {
  const supabaseUrl = process.env.PUBLIC_DATA_SUPABASE_URL?.trim();
  const publishableKey =
    process.env.PUBLIC_DATA_SUPABASE_PUBLISHABLE_KEY?.trim();
  if (
    !Number.isSafeInteger(maxMonths) ||
    maxMonths < 1 ||
    maxMonths > 120 ||
    !supabaseUrl?.startsWith("https://") ||
    !publishableKey?.startsWith("sb_publishable_")
  ) {
    return { state: "unavailable" };
  }
  try {
    const response = await fetch(
      `${supabaseUrl}/rest/v1/rpc/get_public_payroll_coverage`,
      {
        method: "POST",
        headers: {
          Accept: "application/json",
          "Accept-Profile": "api",
          apikey: publishableKey,
          "Content-Profile": "api",
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ month_limit: maxMonths }),
        next: { revalidate: 300 },
        signal: AbortSignal.timeout(5_000),
      },
    );
    if (!response.ok) return { state: "unavailable" };
    const payload = await response.json();
    if (!Array.isArray(payload)) return { state: "unavailable" };
    const rows = payload.map(parsePublicPayrollCoverageRow);
    if (
      rows.some((row) => row === null) ||
      new Set(rows.map((row) => row.referenceMonth)).size !== rows.length
    ) {
      return { state: "unavailable" };
    }
    return { state: "available", rows };
  } catch {
    return { state: "unavailable" };
  }
}

export async function getPublicNonpayrollWorkforceCoverage(maxMonths = 120) {
  const supabaseUrl = process.env.PUBLIC_DATA_SUPABASE_URL?.trim();
  const publishableKey =
    process.env.PUBLIC_DATA_SUPABASE_PUBLISHABLE_KEY?.trim();
  if (
    !Number.isSafeInteger(maxMonths) ||
    maxMonths < 1 ||
    maxMonths > 120 ||
    !supabaseUrl?.startsWith("https://") ||
    !publishableKey?.startsWith("sb_publishable_")
  ) {
    return { state: "unavailable" };
  }
  try {
    const response = await fetch(
      `${supabaseUrl}/rest/v1/rpc/get_public_nonpayroll_workforce_coverage`,
      {
        method: "POST",
        headers: {
          Accept: "application/json",
          "Accept-Profile": "api",
          apikey: publishableKey,
          "Content-Profile": "api",
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ month_limit: maxMonths }),
        next: { revalidate: 300 },
        signal: AbortSignal.timeout(5_000),
      },
    );
    if (!response.ok) return { state: "unavailable" };
    const payload = await response.json();
    if (!Array.isArray(payload)) return { state: "unavailable" };
    const rows = payload.map(parsePublicNonpayrollWorkforceCoverageRow);
    const rowKeys = rows.map(
      (row) => `${row?.referenceMonth ?? ""}:${row?.workforceCategory ?? ""}`,
    );
    if (
      rows.some((row) => row === null) ||
      new Set(rowKeys).size !== rows.length
    ) {
      return { state: "unavailable" };
    }
    return { state: "available", rows };
  } catch {
    return { state: "unavailable" };
  }
}

export async function getPublicPayrollRegimeBreakdown(referenceMonth) {
  const supabaseUrl = process.env.PUBLIC_DATA_SUPABASE_URL?.trim();
  const publishableKey =
    process.env.PUBLIC_DATA_SUPABASE_PUBLISHABLE_KEY?.trim();
  if (
    typeof referenceMonth !== "string" ||
    !ISO_DATE.test(referenceMonth) ||
    !supabaseUrl?.startsWith("https://") ||
    !publishableKey?.startsWith("sb_publishable_")
  ) {
    return { state: "unavailable" };
  }
  try {
    const response = await fetch(
      `${supabaseUrl}/rest/v1/rpc/get_public_payroll_regime_breakdown`,
      {
        method: "POST",
        headers: {
          Accept: "application/json",
          "Accept-Profile": "api",
          apikey: publishableKey,
          "Content-Profile": "api",
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ target_reference_month: referenceMonth }),
        next: { revalidate: 300 },
        signal: AbortSignal.timeout(5_000),
      },
    );
    if (!response.ok) return { state: "unavailable" };
    const payload = await response.json();
    if (!Array.isArray(payload)) return { state: "unavailable" };
    const rows = payload.map(parsePublicPayrollRegimeRow);
    if (
      rows.some((row) => row === null) ||
      rows.some((row) => row.referenceMonth !== referenceMonth) ||
      new Set(rows.map((row) => row.regimeCode)).size !== rows.length
    ) {
      return { state: "unavailable" };
    }
    return { state: "available", rows };
  } catch {
    return { state: "unavailable" };
  }
}

export async function getPublicPayrollCompensationDistribution(referenceMonth) {
  const supabaseUrl = process.env.PUBLIC_DATA_SUPABASE_URL?.trim();
  const publishableKey =
    process.env.PUBLIC_DATA_SUPABASE_PUBLISHABLE_KEY?.trim();
  if (
    typeof referenceMonth !== "string" ||
    !ISO_DATE.test(referenceMonth) ||
    !supabaseUrl?.startsWith("https://") ||
    !publishableKey?.startsWith("sb_publishable_")
  ) {
    return { state: "unavailable" };
  }
  try {
    const response = await fetch(
      `${supabaseUrl}/rest/v1/rpc/get_public_payroll_compensation_distribution`,
      {
        method: "POST",
        headers: {
          Accept: "application/json",
          "Accept-Profile": "api",
          apikey: publishableKey,
          "Content-Profile": "api",
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ target_reference_month: referenceMonth }),
        next: { revalidate: 300 },
        signal: AbortSignal.timeout(5_000),
      },
    );
    if (!response.ok) return { state: "unavailable" };
    const payload = await response.json();
    if (!Array.isArray(payload)) return { state: "unavailable" };
    const rows = payload.map(parsePublicPayrollCompensationRow);
    if (
      rows.some((row) => row === null) ||
      rows.some((row) => row.referenceMonth !== referenceMonth) ||
      new Set(rows.map((row) => row.bandCode)).size !== rows.length
    ) {
      return { state: "unavailable" };
    }
    return { state: "available", rows };
  } catch {
    return { state: "unavailable" };
  }
}
