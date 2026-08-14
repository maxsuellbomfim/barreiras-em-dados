import {
  parseParliamentaryContributionProfileRows,
  type ParliamentaryContributionProfile,
  type ParliamentaryContributionSphere,
} from "./parliamentary-contribution-profile.mjs";

export const PARLIAMENTARY_CONTRIBUTION_PAGE_SIZE = 25;

export type ParliamentaryContributionProfileResult =
  | Readonly<{ state: "available"; profile: ParliamentaryContributionProfile }>
  | Readonly<{ state: "not_found" }>
  | Readonly<{ state: "unavailable" }>;

type Query = Readonly<{
  sphere: ParliamentaryContributionSphere;
  legislatureNumber: number;
  authorKey: string;
  page: number;
}>;

type RpcRequest = Readonly<{
  headers: Readonly<Record<string, string>>;
  body: string;
}>;

async function fetchRpc(url: string, request: RpcRequest, bypassCache = false) {
  return fetch(url, {
    method: "POST",
    headers: request.headers,
    body: request.body,
    ...(bypassCache
      ? { cache: "no-store" as const }
      : { next: { revalidate: 300 } }),
    signal: AbortSignal.timeout(5_000),
  });
}

export async function getPublicParliamentaryContributionProfile({
  sphere,
  legislatureNumber,
  authorKey,
  page,
}: Query): Promise<ParliamentaryContributionProfileResult> {
  const normalizedAuthorKey = authorKey.trim();
  if (
    !["federal", "state"].includes(sphere) ||
    !Number.isSafeInteger(legislatureNumber) || legislatureNumber < 1 ||
    !normalizedAuthorKey || normalizedAuthorKey.length > 200 ||
    /[\u0000-\u001f\u007f]/u.test(normalizedAuthorKey) ||
    !Number.isSafeInteger(page) || page < 1 || page > 401
  ) return { state: "not_found" };

  const supabaseUrl = process.env.PUBLIC_DATA_SUPABASE_URL?.trim();
  const publishableKey =
    process.env.PUBLIC_DATA_SUPABASE_PUBLISHABLE_KEY?.trim();
  if (
    !supabaseUrl?.startsWith("https://") ||
    !publishableKey?.startsWith("sb_publishable_")
  ) return { state: "unavailable" };

  try {
    const url = `${supabaseUrl}/rest/v1/rpc/get_public_parliamentary_legislature_contributions`;
    const request = {
      headers: {
        Accept: "application/json",
        "Accept-Profile": "api",
        apikey: publishableKey,
        "Content-Profile": "api",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        sphere_filter: sphere,
        legislature_number_filter: legislatureNumber,
        author_key_filter: normalizedAuthorKey,
        page_size: PARLIAMENTARY_CONTRIBUTION_PAGE_SIZE,
        page_offset: (page - 1) * PARLIAMENTARY_CONTRIBUTION_PAGE_SIZE,
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
    const payload: unknown = await response.json();
    if (!Array.isArray(payload)) return { state: "unavailable" };
    if (payload.length === 0) return { state: "not_found" };
    const profile = parseParliamentaryContributionProfileRows(payload);
    return profile === null
      ? { state: "unavailable" }
      : { state: "available", profile };
  } catch {
    return { state: "unavailable" };
  }
}
