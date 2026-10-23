import { parseAnnualFinanceSummaries } from "./annual-finance-summary.mjs";

export async function getPublicAnnualFinanceSummary() {
  const url = process.env.PUBLIC_DATA_SUPABASE_URL?.trim();
  const key = process.env.PUBLIC_DATA_SUPABASE_PUBLISHABLE_KEY?.trim();
  if (!url?.startsWith("https://") || !key?.startsWith("sb_publishable_")) {
    return { state: "unavailable" };
  }
  try {
    const response = await fetch(`${url}/rest/v1/rpc/get_public_annual_finance_summary`, {
      method: "POST",
      headers: {
        Accept: "application/json", "Accept-Profile": "api",
        "Content-Profile": "api", "Content-Type": "application/json", apikey: key,
      },
      body: JSON.stringify({}),
      next: { revalidate: 300 },
      signal: AbortSignal.timeout(5_000),
    });
    if (!response.ok) return { state: "unavailable" };
    const summaries = parseAnnualFinanceSummaries(await response.json());
    return summaries === null ? { state: "unavailable" } : { state: "available", summaries };
  } catch {
    return { state: "unavailable" };
  }
}
