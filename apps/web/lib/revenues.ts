export type PublicRevenue = Readonly<{
  revenueId: string;
  externalId: string | null;
  fiscalYear: number;
  revenueDate: string | null;
  revenueCode: string | null;
  description: string;
  collectedAmount: string;
  accumulatedAmount: string;
  reportTotalPeriodAmount: string;
  collectionDirection: "credit" | "deduction";
  currency: "BRL";
  publicBodyName: string;
  sourceUrl: string | null;
  documentSourceUrl: string;
  artifactSha256: string;
  documentArtifactSha256: string;
  collectedAt: string;
  methodologyVersion: "public-revenues/1.1.0";
  validationStatus: "validated";
}>;

export type RevenuesResult =
  | Readonly<{ state: "available"; revenues: readonly PublicRevenue[] }>
  | Readonly<{ state: "unavailable" }>;

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;
const SHA256 = /^[0-9a-f]{64}$/;
const DECIMAL = /^-?\d+(?:\.\d{1,2})?$/;

function optionalString(value: unknown): string | null {
  return typeof value === "string" && value.trim().length > 0 ? value : null;
}

/**
 * PostgreSQL numeric values can arrive from PostgREST as JSON numbers. Convert
 * only finite, safe values to their decimal representation; no arithmetic or
 * locale parsing is performed here.
 */
function optionalDecimal(value: unknown): string | null {
  if (typeof value === "string") return value.trim().length > 0 ? value : null;
  if (
    typeof value === "number" &&
    Number.isFinite(value) &&
    Math.abs(value) <= Number.MAX_SAFE_INTEGER
  ) {
    return String(value);
  }
  return null;
}

function parseRevenue(row: Record<string, unknown>): PublicRevenue | null {
  const revenueId = optionalString(row.revenue_id);
  const description = optionalString(row.description);
  const publicBodyName = optionalString(row.public_body_name);
  const collectedAmount = optionalDecimal(row.collected_amount);
  const accumulatedAmount = optionalDecimal(row.accumulated_amount);
  const reportTotalPeriodAmount = optionalDecimal(row.report_total_period_amount);
  const collectionDirection = row.collection_direction;
  const sourceUrl = optionalString(row.source_url);
  const documentSourceUrl = optionalString(row.document_source_url);
  const artifactSha256 = optionalString(row.artifact_sha256);
  const documentArtifactSha256 = optionalString(row.document_artifact_sha256);
  const collectedAt = optionalString(row.collected_at);
  const revenueDate = optionalString(row.revenue_date);
  if (
    revenueId === null ||
    description === null ||
    publicBodyName === null ||
    collectedAmount === null ||
    !DECIMAL.test(collectedAmount) ||
    accumulatedAmount === null ||
    !DECIMAL.test(accumulatedAmount) ||
    reportTotalPeriodAmount === null ||
    !DECIMAL.test(reportTotalPeriodAmount) ||
    (collectionDirection !== "credit" && collectionDirection !== "deduction") ||
    row.currency !== "BRL" ||
    artifactSha256 === null ||
    !SHA256.test(artifactSha256) ||
    documentSourceUrl === null ||
    !documentSourceUrl.startsWith("https://") ||
    documentArtifactSha256 === null ||
    !SHA256.test(documentArtifactSha256) ||
    collectedAt === null ||
    Number.isNaN(Date.parse(collectedAt)) ||
    (revenueDate !== null && !ISO_DATE.test(revenueDate)) ||
    !Number.isSafeInteger(row.fiscal_year) ||
    row.methodology_version !== "public-revenues/1.1.0" ||
    row.validation_status !== "validated" ||
    (sourceUrl !== null && !sourceUrl.startsWith("https://"))
  ) {
    return null;
  }
  return {
    revenueId,
    externalId: optionalString(row.external_id),
    fiscalYear: Number(row.fiscal_year),
    revenueDate,
    revenueCode: optionalString(row.revenue_code),
    description,
    collectedAmount,
    accumulatedAmount,
    reportTotalPeriodAmount,
    collectionDirection,
    currency: "BRL",
    publicBodyName,
    sourceUrl,
    documentSourceUrl,
    artifactSha256,
    documentArtifactSha256,
    collectedAt,
    methodologyVersion: "public-revenues/1.1.0",
    validationStatus: "validated",
  };
}

export async function getPublicRevenues(
  fiscalYear?: number,
): Promise<RevenuesResult> {
  const supabaseUrl = process.env.PUBLIC_DATA_SUPABASE_URL?.trim();
  const publishableKey =
    process.env.PUBLIC_DATA_SUPABASE_PUBLISHABLE_KEY?.trim();
  if (
    !supabaseUrl ||
    !publishableKey ||
    !supabaseUrl.startsWith("https://") ||
    !publishableKey.startsWith("sb_publishable_")
  ) {
    return { state: "unavailable" };
  }

  try {
    const response = await fetch(
      `${supabaseUrl}/rest/v1/rpc/get_public_revenues`,
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
          page_size: 100,
          fiscal_year_filter: fiscalYear ?? null,
        }),
        next: { revalidate: 300 },
        signal: AbortSignal.timeout(5_000),
      },
    );
    if (!response.ok) return { state: "unavailable" };
    const payload = await response.json();
    if (!Array.isArray(payload)) return { state: "unavailable" };
    const revenues: PublicRevenue[] = [];
    for (const row of payload) {
      if (typeof row !== "object" || row === null) {
        return { state: "unavailable" };
      }
      const revenue = parseRevenue(row as Record<string, unknown>);
      if (revenue === null) return { state: "unavailable" };
      revenues.push(revenue);
    }
    return { state: "available", revenues };
  } catch {
    return { state: "unavailable" };
  }
}

export function formatBrlDecimal(value: string): string {
  const [integerPart, decimalPart = "00"] = value.split(".");
  const sign = integerPart.startsWith("-") ? "-" : "";
  const unsignedInteger = sign ? integerPart.slice(1) : integerPart;
  const grouped = unsignedInteger.replace(/\B(?=(\d{3})+(?!\d))/g, ".");
  return `R$ ${sign}${grouped},${decimalPart.padEnd(2, "0")}`;
}
