import {
  parseParliamentaryLegislatureCoverageRows,
  type ParliamentaryLegislatureCoverageRow,
} from "./parliamentary-legislature-coverage.mjs";

export type ParliamentaryLegislatureCoverageResult =
  | Readonly<{
      state: "available";
      rows: readonly ParliamentaryLegislatureCoverageRow[];
    }>
  | Readonly<{ state: "unavailable" }>;

type RpcRequest = Readonly<{
  headers: Readonly<Record<string, string>>;
  body: string;
}>;

async function fetchRpc(url: string, request: RpcRequest, bypassCache = false) {
  return fetch(url, {
    method: "POST",
    headers: request.headers,
    body: request.body,
    ...(bypassCache ? { cache: "no-store" as const } : { next: { revalidate: 300 } }),
    signal: AbortSignal.timeout(5_000),
  });
}

export async function getPublicParliamentaryLegislatureCoverage(): Promise<
  ParliamentaryLegislatureCoverageResult
> {
  const supabaseUrl = process.env.PUBLIC_DATA_SUPABASE_URL?.trim();
  const publishableKey = process.env.PUBLIC_DATA_SUPABASE_PUBLISHABLE_KEY?.trim();
  if (!supabaseUrl?.startsWith("https://") || !publishableKey?.startsWith("sb_publishable_")) {
    return { state: "unavailable" };
  }
  try {
    const url = `${supabaseUrl}/rest/v1/rpc/get_public_parliamentary_legislature_coverage`;
    const request = {
      headers: {
        Accept: "application/json",
        "Accept-Profile": "api",
        apikey: publishableKey,
        "Content-Profile": "api",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        sphere_filter: null,
        legislature_number_filter: null,
      }),
    };
    const cachedResponse = await fetchRpc(url, request);
    const response = !cachedResponse.ok && (
      [404, 408, 425, 429].includes(cachedResponse.status) ||
      cachedResponse.status >= 500
    )
      ? await fetchRpc(url, request, true)
      : cachedResponse;
    if (!response.ok) return { state: "unavailable" };
    const parsed = parseParliamentaryLegislatureCoverageRows(await response.json());
    if (parsed === null || parsed.length === 0) return { state: "unavailable" };
    return { state: "available", rows: parsed };
  } catch {
    return { state: "unavailable" };
  }
}
