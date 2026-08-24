import {
  parseSiconfiMonthlyReconciliation,
  type ParsedSiconfiReconciliationYear,
} from "./siconfi-monthly-reconciliation-parser.mjs";

export type PublicSiconfiReconciliationYear = ParsedSiconfiReconciliationYear;

export type SiconfiMonthlyReconciliationResult =
  | Readonly<{
      state: "available";
      years: readonly PublicSiconfiReconciliationYear[];
    }>
  | Readonly<{ state: "unavailable" }>;

export async function getPublicSiconfiMonthlyReconciliation(): Promise<SiconfiMonthlyReconciliationResult> {
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
      `${supabaseUrl}/rest/v1/rpc/get_public_siconfi_monthly_reconciliation`,
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
          fiscal_year_from: 2021,
          fiscal_year_to: null,
        }),
        next: { revalidate: 300 },
        signal: AbortSignal.timeout(5_000),
      },
    );
    if (!response.ok) return { state: "unavailable" };
    const years = parseSiconfiMonthlyReconciliation(await response.json());
    if (!years) return { state: "unavailable" };
    return { state: "available", years };
  } catch {
    return { state: "unavailable" };
  }
}
