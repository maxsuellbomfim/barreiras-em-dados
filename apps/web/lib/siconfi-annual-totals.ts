import {
  parseSiconfiAnnualRows,
  type ParsedSiconfiAnnualYear,
} from "./siconfi-annual-totals-parser.mjs";

export type PublicSiconfiAnnualYear = ParsedSiconfiAnnualYear;

export type SiconfiAnnualTotalsResult =
  | Readonly<{ state: "available"; years: readonly PublicSiconfiAnnualYear[] }>
  | Readonly<{ state: "unavailable" }>;

export async function getPublicSiconfiAnnualTotals(): Promise<SiconfiAnnualTotalsResult> {
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
      `${supabaseUrl}/rest/v1/rpc/get_public_siconfi_annual_totals`,
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
          page_size: 70,
          fiscal_year_from: 2021,
          fiscal_year_to: null,
        }),
        next: { revalidate: 300 },
        signal: AbortSignal.timeout(5_000),
      },
    );
    if (!response.ok) return { state: "unavailable" };
    const years = parseSiconfiAnnualRows(await response.json());
    if (!years) return { state: "unavailable" };
    return { state: "available", years };
  } catch {
    return { state: "unavailable" };
  }
}
