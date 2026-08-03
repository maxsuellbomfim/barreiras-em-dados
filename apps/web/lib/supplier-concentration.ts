export type PublicSupplierConcentration = Readonly<{
  supplierKey: string;
  supplierName: string;
  supplierType: string;
  publicRegistrationNumber: string | null;
  procurementCount: number;
  itemCount: number;
  totalAwardedAmount: string;
  awardedShare: string;
  firstResultDate: string | null;
  lastResultDate: string | null;
  attentionSignal: boolean;
  publicExplanation: string;
  sourceUrl: string | null;
  methodologyVersion: "pncp-supplier-concentration/1.0.0";
}>;

export type SupplierConcentrationResult =
  | Readonly<{ state: "available"; suppliers: readonly PublicSupplierConcentration[] }>
  | Readonly<{ state: "unavailable" }>;

const DECIMAL = /^\d+(?:\.\d{1,6})?$/;
const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;

function text(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function repairMojibake(value: string): string {
  if (!/[ÃƒÃ‚]/.test(value)) return value;
  try {
    const bytes = Uint8Array.from(Array.from(value), (character) => character.charCodeAt(0));
    return new TextDecoder("utf-8", { fatal: true }).decode(bytes);
  } catch {
    return value;
  }
}

function decimal(value: unknown): string | null {
  return typeof value === "string" && DECIMAL.test(value.trim()) ? value.trim() : null;
}

function integer(value: unknown): number | null {
  return typeof value === "number" && Number.isSafeInteger(value) && value >= 0 ? value : null;
}

function parseSupplier(row: Record<string, unknown>): PublicSupplierConcentration | null {
  const supplierKey = text(row.supplier_key);
  const supplierNameValue = text(row.supplier_name);
  const supplierType = text(row.supplier_type);
  const totalAwardedAmount = decimal(row.total_awarded_amount);
  const awardedShare = decimal(row.awarded_share);
  const publicExplanationValue = text(row.public_explanation);
  const methodologyVersion = row.methodology_version;
  const procurementCount = integer(row.procurement_count);
  const itemCount = integer(row.item_count);
  const sourceUrl = text(row.source_url);
  const firstResultDate = text(row.first_result_date);
  const lastResultDate = text(row.last_result_date);
  if (
    !supplierKey || !supplierNameValue || !supplierType || !totalAwardedAmount ||
    !awardedShare || !publicExplanationValue || methodologyVersion !== "pncp-supplier-concentration/1.0.0" ||
    procurementCount === null || itemCount === null || typeof row.attention_signal !== "boolean" ||
    (firstResultDate !== null && !ISO_DATE.test(firstResultDate)) ||
    (lastResultDate !== null && !ISO_DATE.test(lastResultDate))
  ) return null;
  return {
    supplierKey,
    supplierName: repairMojibake(supplierNameValue),
    supplierType,
    publicRegistrationNumber: text(row.public_registration_number),
    procurementCount,
    itemCount,
    totalAwardedAmount,
    awardedShare,
    firstResultDate,
    lastResultDate,
    attentionSignal: row.attention_signal,
    publicExplanation: repairMojibake(publicExplanationValue),
    sourceUrl: sourceUrl?.startsWith("https://") ? sourceUrl : null,
    methodologyVersion: "pncp-supplier-concentration/1.0.0",
  };
}

export async function getPublicSupplierConcentration(): Promise<SupplierConcentrationResult> {
  const supabaseUrl = process.env.PUBLIC_DATA_SUPABASE_URL?.trim();
  const publishableKey = process.env.PUBLIC_DATA_SUPABASE_PUBLISHABLE_KEY?.trim();
  if (!supabaseUrl?.startsWith("https://") || !publishableKey?.startsWith("sb_publishable_")) {
    return { state: "unavailable" };
  }
  try {
    const response = await fetch(`${supabaseUrl}/rest/v1/rpc/get_public_supplier_concentration`, {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Accept-Profile": "api",
        apikey: publishableKey,
        "Content-Profile": "api",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ page_size: 30 }),
      next: { revalidate: 300 },
      signal: AbortSignal.timeout(5_000),
    });
    if (!response.ok) return { state: "unavailable" };
    const payload: unknown = await response.json();
    if (!Array.isArray(payload)) return { state: "unavailable" };
    const suppliers: PublicSupplierConcentration[] = [];
    for (const row of payload) {
      if (typeof row !== "object" || row === null) continue;
      const supplier = parseSupplier(row as Record<string, unknown>);
      if (supplier) suppliers.push(supplier);
    }
    return { state: "available", suppliers };
  } catch {
    return { state: "unavailable" };
  }
}
