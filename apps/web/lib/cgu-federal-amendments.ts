import {
  parseCguFederalAmendmentRankingRows,
  parseCguFederalAmendmentRows,
  type CguFederalAmendment,
  type CguFederalAmendmentRanking,
} from "./cgu-federal-amendments.mjs";

export type {
  CguFederalAmendment,
  CguFederalAmendmentRanking,
} from "./cgu-federal-amendments.mjs";

export type CguFederalAmendmentsResult =
  | Readonly<{
      state: "available";
      amendments: readonly CguFederalAmendment[];
      people: readonly CguFederalAmendmentRanking[];
      collectives: readonly CguFederalAmendmentRanking[];
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

async function callRpc(
  supabaseUrl: string,
  publishableKey: string,
  functionName: string,
  args: Record<string, unknown>,
): Promise<unknown> {
  const url = `${supabaseUrl}/rest/v1/rpc/${functionName}`;
  const request = {
    headers: {
      Accept: "application/json",
      "Accept-Profile": "api",
      apikey: publishableKey,
      "Content-Profile": "api",
      "Content-Type": "application/json",
    },
    body: JSON.stringify(args),
  };
  const cachedResponse = await fetchRpc(url, request);
  const response = !cachedResponse.ok && (
    [404, 408, 425, 429].includes(cachedResponse.status) ||
    cachedResponse.status >= 500
  )
    ? await fetchRpc(url, request, true)
    : cachedResponse;
  if (!response.ok) return null;
  return response.json();
}

export async function getPublicCguFederalAmendments(): Promise<
  CguFederalAmendmentsResult
> {
  const supabaseUrl = process.env.PUBLIC_DATA_SUPABASE_URL?.trim();
  const publishableKey = process.env.PUBLIC_DATA_SUPABASE_PUBLISHABLE_KEY?.trim();
  if (!supabaseUrl?.startsWith("https://") || !publishableKey?.startsWith("sb_publishable_")) {
    return { state: "unavailable" };
  }
  try {
    const [executionRows, peopleRows, collectiveRows] = await Promise.all([
      callRpc(supabaseUrl, publishableKey, "get_public_cgu_federal_amendment_executions", {
        fiscal_year_filter: null,
        author_key_filter: null,
        page_size: 200,
      }),
      callRpc(supabaseUrl, publishableKey, "get_public_cgu_federal_amendment_ranking", {
        author_scope: "person",
        fiscal_year_filter: null,
        page_size: 50,
      }),
      callRpc(supabaseUrl, publishableKey, "get_public_cgu_federal_amendment_ranking", {
        author_scope: "collective",
        fiscal_year_filter: null,
        page_size: 50,
      }),
    ]);
    const amendments = parseCguFederalAmendmentRows(executionRows);
    const people = parseCguFederalAmendmentRankingRows(peopleRows, "person");
    const collectives = parseCguFederalAmendmentRankingRows(
      collectiveRows,
      "collective",
    );
    if (amendments === null || people === null || collectives === null) {
      return { state: "unavailable" };
    }
    return { state: "available", amendments, people, collectives };
  } catch {
    return { state: "unavailable" };
  }
}
