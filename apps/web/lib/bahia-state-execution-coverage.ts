import {
  parseBahiaStateExecutionCoverageRows,
  type BahiaStateExecutionCoverage,
} from "./bahia-state-execution-coverage.mjs";

export type BahiaStateExecutionCoverageResult =
  | Readonly<{
      state: "available";
      rows: readonly BahiaStateExecutionCoverage[];
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

export async function getPublicBahiaStateExecutionCoverage(): Promise<
  BahiaStateExecutionCoverageResult
> {
  const supabaseUrl = process.env.PUBLIC_DATA_SUPABASE_URL?.trim();
  const publishableKey = process.env.PUBLIC_DATA_SUPABASE_PUBLISHABLE_KEY?.trim();
  if (
    !supabaseUrl?.startsWith("https://") ||
    !publishableKey?.startsWith("sb_publishable_")
  ) return { state: "unavailable" };

  const url = `${supabaseUrl}/rest/v1/rpc/get_public_bahia_state_execution_annual_coverage`;
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
    const rows = parseBahiaStateExecutionCoverageRows(await response.json());
    return rows === null
      ? { state: "unavailable" }
      : { state: "available", rows };
  } catch {
    return { state: "unavailable" };
  }
}
