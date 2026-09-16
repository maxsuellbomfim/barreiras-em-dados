export type PncpQueryStatus = Readonly<{
  state: "unknown" | "pending" | "query_complete" | "empty_confirmed" | "inconclusive" | "partial" | "interrupted" | "unavailable";
  checkedAt: string | null;
  sourceUrl: string | null;
}>;

const states = new Set(["unknown", "pending", "query_complete", "empty_confirmed", "inconclusive", "partial", "interrupted"]);
const controlPattern = /^13654405000195-1-([0-9]{1,12})\/([0-9]{4})$/;

export async function fetchPncpQueryStatuses(
  baseUrl: string, publishableKey: string, controls: readonly string[], fetcher: typeof fetch = fetch,
): Promise<ReadonlyMap<string, PncpQueryStatus>> {
  const unique = [...new Set(controls)];
  if (unique.length > 60) return new Map();
  // The status RPC currently covers only the Prefeitura's CNPJ. Other owners
  // must not invalidate eligible cards or receive invented query observations.
  const keys = unique.filter(key => controlPattern.exec(key)?.[0] === key);
  if (keys.length === 0) return new Map();
  try {
    const response = await fetcher(`${baseUrl}/rest/v1/rpc/get_pncp_contract_query_status`, {
      method: "POST",
      headers: { apikey: publishableKey, "Content-Type": "application/json", "Accept-Profile": "api", "Content-Profile": "api" },
      body: JSON.stringify({ control_numbers: keys }),
      cache: "no-store",
      signal: AbortSignal.timeout(3_000),
    });
    if (!response.ok) return new Map();
    const payload: unknown = await response.json();
    if (!Array.isArray(payload) || payload.length !== keys.length) return new Map();
    const result = new Map<string, PncpQueryStatus>();
    for (const item of payload) {
      if (typeof item !== "object" || item === null) return new Map();
      const row = item as Record<string, unknown>;
      if (typeof row.control_number !== "string" || !keys.includes(row.control_number) || result.has(row.control_number)) return new Map();
      const match = controlPattern.exec(row.control_number)!;
      const officialUrl = `https://pncp.gov.br/app/editais/13654405000195/${match[2]}/${Number(match[1])}`;
      if (typeof row.state !== "string" || !states.has(row.state) || row.source_url !== officialUrl) return new Map();
      const pending = row.state === "unknown" || row.state === "pending";
      if (pending ? row.checked_at !== null : (
        typeof row.checked_at !== "string" || !/^\d{4}-\d{2}-\d{2}T/.test(row.checked_at) || !Number.isFinite(Date.parse(row.checked_at))
      )) return new Map();
      result.set(row.control_number, {
        state: row.state as PncpQueryStatus["state"], checkedAt: row.checked_at as string | null, sourceUrl: officialUrl,
      });
    }
    return result;
  } catch {
    // Coverage unavailability must not hide the already validated procurements.
    return new Map();
  }
}
