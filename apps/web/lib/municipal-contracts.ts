import {
  parseMunicipalContractRows,
  type MunicipalContract,
} from "./municipal-contracts.mjs";

export type { MunicipalContract } from "./municipal-contracts.mjs";
export { municipalSupplierLabel } from "./municipal-contracts.mjs";

export type MunicipalContractsResult =
  | Readonly<{
      state: "available";
      contracts: readonly MunicipalContract[];
    }>
  | Readonly<{ state: "unavailable" }>;

export async function getPublicMunicipalContracts(): Promise<
  MunicipalContractsResult
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
      `${supabaseUrl}/rest/v1/rpc/get_public_municipal_contracts`,
      {
        method: "POST",
        headers: {
          Accept: "application/json",
          "Accept-Profile": "api",
          apikey: publishableKey,
          "Content-Profile": "api",
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ page_size: 100 }),
        next: { revalidate: 300 },
        signal: AbortSignal.timeout(5_000),
      },
    );
    if (!response.ok) return { state: "unavailable" };
    const contracts = parseMunicipalContractRows(await response.json());
    if (contracts === null) return { state: "unavailable" };
    return { state: "available", contracts };
  } catch {
    return { state: "unavailable" };
  }
}
