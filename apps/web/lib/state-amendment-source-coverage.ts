import {
  parseStateAmendmentSourceCoverageRows,
  type StateAmendmentSourceCoverage,
} from "./state-amendment-source-coverage.mjs";

export type StateAmendmentSourceCoverageResult =
  | Readonly<{
      state: "available";
      rows: readonly StateAmendmentSourceCoverage[];
    }>
  | Readonly<{ state: "unavailable" }>;

async function fetchCoverageRpc(
  url: string,
  headers: Readonly<Record<string, string>>,
  bypassCache = false,
) {
  return fetch(url, {
    method: "POST",
    headers,
    body: "{}",
    ...(bypassCache
      ? { cache: "no-store" as const }
      : { next: { revalidate: 300 } }),
    signal: AbortSignal.timeout(5_000),
  });
}

export async function getPublicStateAmendmentSourceCoverage(): Promise<
  StateAmendmentSourceCoverageResult
> {
  const supabaseUrl = process.env.PUBLIC_DATA_SUPABASE_URL?.trim();
  const publishableKey = process.env.PUBLIC_DATA_SUPABASE_PUBLISHABLE_KEY?.trim();
  if (
    !supabaseUrl?.startsWith("https://") ||
    !publishableKey?.startsWith("sb_publishable_")
  ) return { state: "unavailable" };

  const url = `${supabaseUrl}/rest/v1/rpc/get_public_state_amendment_source_coverage`;
  const headers = {
    Accept: "application/json",
    "Accept-Profile": "api",
    apikey: publishableKey,
    "Content-Profile": "api",
    "Content-Type": "application/json",
  };
  try {
    const cachedResponse = await fetchCoverageRpc(url, headers);
    const response = !cachedResponse.ok && (
      [404, 408, 425, 429].includes(cachedResponse.status) ||
      cachedResponse.status >= 500
    )
      ? await fetchCoverageRpc(url, headers, true)
      : cachedResponse;
    if (!response.ok) return { state: "unavailable" };
    const rows = parseStateAmendmentSourceCoverageRows(await response.json());
    if (rows === null || rows.length === 0) return { state: "unavailable" };
    return { state: "available", rows };
  } catch {
    return { state: "unavailable" };
  }
}
