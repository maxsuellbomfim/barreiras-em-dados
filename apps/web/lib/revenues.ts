export type PublicRevenue = Readonly<{
  revenueId: string;
  externalId: string | null;
  fiscalYear: number;
  revenueDate: string | null;
  revenueCode: string | null;
  description: string;
  collectedAmount: string;
  currency: "BRL";
  publicBodyName: string;
  sourceUrl: string | null;
  artifactSha256: string;
  collectedAt: string;
  methodologyVersion: "public-revenues/1.0.0";
}>;

export type RevenuesResult =
  | Readonly<{ state: "available"; revenues: readonly PublicRevenue[] }>
  | Readonly<{ state: "unavailable" }>;

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;
const SHA256 = /^[0-9a-f]{64}$/;
const DECIMAL = /^\d+(?:\.\d{1,2})?$/;

function optionalString(value: unknown): string | null {
  return typeof value === "string" && value.trim().length > 0 ? value : null;
}

function parseRevenue(row: Record<string, unknown>): PublicRevenue | null {
  const revenueId = optionalString(row.revenue_id);
  const description = optionalString(row.description);
  const publicBodyName = optionalString(row.public_body_name);
  const collectedAmount = optionalString(row.collected_amount);
  const sourceUrl = optionalString(row.source_url);
  const artifactSha256 = optionalString(row.artifact_sha256);
  const collectedAt = optionalString(row.collected_at);
  const revenueDate = optionalString(row.revenue_date);
  if (
    revenueId === null ||
    description === null ||
    publicBodyName === null ||
    collectedAmount === null ||
    !DECIMAL.test(collectedAmount) ||
    row.currency !== "BRL" ||
    artifactSha256 === null ||
    !SHA256.test(artifactSha256) ||
    collectedAt === null ||
    Number.isNaN(Date.parse(collectedAt)) ||
    (revenueDate !== null && !ISO_DATE.test(revenueDate)) ||
    !Number.isSafeInteger(row.fiscal_year) ||
    row.methodology_version !== "public-revenues/1.0.0" ||
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
    currency: "BRL",
    publicBodyName,
    sourceUrl,
    artifactSha256,
    collectedAt,
    methodologyVersion: "public-revenues/1.0.0",
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
  const grouped = integerPart.replace(/\B(?=(\d{3})+(?!\d))/g, ".");
  return `R$ ${grouped},${decimalPart.padEnd(2, "0")}`;
}

