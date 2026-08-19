import {
  parseSupplierSanctionRows,
  type SupplierSanction,
} from "./supplier-sanctions.mjs";

export type { SupplierSanction } from "./supplier-sanctions.mjs";
export {
  formatSanctionCnpj,
  sanctionRegistryLabel,
} from "./supplier-sanctions.mjs";

export type SupplierSanctionsResult =
  | Readonly<{
      state: "available";
      sanctions: readonly SupplierSanction[];
    }>
  | Readonly<{ state: "unavailable" }>;

export async function getPublicSupplierSanctions(): Promise<
  SupplierSanctionsResult
> {
  const supabaseUrl = process.env.PUBLIC_DATA_SUPABASE_URL?.trim();
  const publishableKey = process.env.PUBLIC_DATA_SUPABASE_PUBLISHABLE_KEY?.trim();
  if (
    !supabaseUrl?.startsWith("https://") ||
    !publishableKey?.startsWith("sb_publishable_")
  ) {
    return { state: "unavailable" };
  }
  try {
    const response = await fetch(
      `${supabaseUrl}/rest/v1/rpc/get_public_supplier_sanctions`,
      {
        method: "POST",
        headers: {
          Accept: "application/json",
          "Accept-Profile": "api",
          apikey: publishableKey,
          "Content-Profile": "api",
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ page_size: 200 }),
        next: { revalidate: 300 },
        signal: AbortSignal.timeout(5_000),
      },
    );
    if (!response.ok) return { state: "unavailable" };
    const sanctions = parseSupplierSanctionRows(await response.json());
    if (sanctions === null) return { state: "unavailable" };
    return { state: "available", sanctions };
  } catch {
    return { state: "unavailable" };
  }
}
