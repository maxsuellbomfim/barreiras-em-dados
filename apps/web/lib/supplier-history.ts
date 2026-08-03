export type PublicSupplierHistoryRow = Readonly<{
  supplierKey: string;
  supplierName: string;
  supplierType: string;
  controlNumber: string;
  objectDescription: string;
  publicationDate: string | null;
  resultDate: string | null;
  itemCount: number;
  totalAwardedAmount: string;
  sourceUrl: string | null;
  methodologyVersion: "pncp-supplier-history/1.0.0";
}>;

export type SupplierHistoryResult =
  | Readonly<{ state: "available"; rows: readonly PublicSupplierHistoryRow[] }>
  | Readonly<{ state: "unavailable" }>;

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;
const DECIMAL = /^\d+(?:\.\d{1,2})?$/;

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

function parseRow(row: Record<string, unknown>): PublicSupplierHistoryRow | null {
  const supplierKey = text(row.supplier_key);
  const supplierNameValue = text(row.supplier_name);
  const supplierType = text(row.supplier_type);
  const controlNumber = text(row.control_number);
  const objectDescriptionValue = text(row.object_description);
  const totalAwardedAmount = text(row.total_awarded_amount);
  const publicationDate = text(row.publication_date);
  const resultDate = text(row.result_date);
  const itemCount = row.item_count;
  if (
    !supplierKey || !supplierNameValue || !supplierType || !controlNumber ||
    !objectDescriptionValue || !totalAwardedAmount || !DECIMAL.test(totalAwardedAmount) ||
    typeof itemCount !== "number" || !Number.isSafeInteger(itemCount) || itemCount < 0 ||
    (publicationDate !== null && !ISO_DATE.test(publicationDate)) ||
    (resultDate !== null && !ISO_DATE.test(resultDate)) ||
    row.methodology_version !== "pncp-supplier-history/1.0.0"
  ) return null;
  const sourceUrl = text(row.source_url);
  return {
    supplierKey,
    supplierName: repairMojibake(supplierNameValue),
    supplierType,
    controlNumber,
    objectDescription: repairMojibake(objectDescriptionValue),
    publicationDate,
    resultDate,
    itemCount: Number(itemCount),
    totalAwardedAmount,
    sourceUrl: sourceUrl?.startsWith("https://") ? sourceUrl : null,
    methodologyVersion: "pncp-supplier-history/1.0.0",
  };
}

export async function getPublicSupplierHistory(
  supplierKey: string,
): Promise<SupplierHistoryResult> {
  const supabaseUrl = process.env.PUBLIC_DATA_SUPABASE_URL?.trim();
  const publishableKey = process.env.PUBLIC_DATA_SUPABASE_PUBLISHABLE_KEY?.trim();
  if (!supabaseUrl?.startsWith("https://") || !publishableKey?.startsWith("sb_publishable_")) {
    return { state: "unavailable" };
  }
  try {
    const response = await fetch(`${supabaseUrl}/rest/v1/rpc/get_public_supplier_history`, {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Accept-Profile": "api",
        apikey: publishableKey,
        "Content-Profile": "api",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ supplier_key_filter: supplierKey, page_size: 200 }),
      next: { revalidate: 300 },
      signal: AbortSignal.timeout(5_000),
    });
    if (!response.ok) return { state: "unavailable" };
    const payload: unknown = await response.json();
    if (!Array.isArray(payload)) return { state: "unavailable" };
    const rows: PublicSupplierHistoryRow[] = [];
    for (const row of payload) {
      if (typeof row !== "object" || row === null) continue;
      const parsed = parseRow(row as Record<string, unknown>);
      if (parsed) rows.push(parsed);
    }
    return { state: "available", rows };
  } catch {
    return { state: "unavailable" };
  }
}
