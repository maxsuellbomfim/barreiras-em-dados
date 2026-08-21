import {
  parseBahiaSpecialTransferPayments,
  parseBahiaSpecialTransferRanking,
  type BahiaSpecialTransferPayment,
  type BahiaSpecialTransferRanking,
} from "./bahia-special-transfers.mjs";

export type BahiaSpecialTransfersResult =
  | Readonly<{
      state: "available";
      payments: readonly BahiaSpecialTransferPayment[];
      ranking: readonly BahiaSpecialTransferRanking[];
    }>
  | Readonly<{ state: "unavailable" }>;

async function fetchRpc(
  url: string,
  headers: Readonly<Record<string, string>>,
  body: string,
  bypassCache = false,
) {
  return fetch(url, {
    method: "POST",
    headers,
    body,
    ...(bypassCache
      ? { cache: "no-store" as const }
      : { next: { revalidate: 300 } }),
    signal: AbortSignal.timeout(5_000),
  });
}

async function fetchWithRetry(
  url: string,
  headers: Readonly<Record<string, string>>,
  body: string,
) {
  const cached = await fetchRpc(url, headers, body);
  if (cached.ok || !(
    [404, 408, 425, 429].includes(cached.status) || cached.status >= 500
  )) return cached;
  return fetchRpc(url, headers, body, true);
}

export async function getPublicBahiaSpecialTransfers(
  fiscalYear?: number,
): Promise<BahiaSpecialTransfersResult> {
  const supabaseUrl = process.env.PUBLIC_DATA_SUPABASE_URL?.trim();
  const publishableKey = process.env.PUBLIC_DATA_SUPABASE_PUBLISHABLE_KEY?.trim();
  if (
    !supabaseUrl?.startsWith("https://") ||
    !publishableKey?.startsWith("sb_publishable_")
  ) return { state: "unavailable" };
  const headers = {
    Accept: "application/json",
    "Accept-Profile": "api",
    apikey: publishableKey,
    "Content-Profile": "api",
    "Content-Type": "application/json",
  };
  const year = Number.isSafeInteger(fiscalYear) &&
      (fiscalYear ?? 0) >= 2000 && (fiscalYear ?? 0) <= 2100
    ? fiscalYear
    : null;
  const paymentsBody = JSON.stringify({
    fiscal_year_filter: year,
    author_key_filter: null,
    page_size: 200,
  });
  const rankingBody = JSON.stringify({
    fiscal_year_filter: year,
    page_size: 10,
  });
  try {
    const [paymentsResponse, rankingResponse] = await Promise.all([
      fetchWithRetry(
        `${supabaseUrl}/rest/v1/rpc/get_public_bahia_special_transfer_payments`,
        headers,
        paymentsBody,
      ),
      fetchWithRetry(
        `${supabaseUrl}/rest/v1/rpc/get_public_bahia_special_transfer_ranking`,
        headers,
        rankingBody,
      ),
    ]);
    if (!paymentsResponse.ok || !rankingResponse.ok) {
      return { state: "unavailable" };
    }
    const payments = parseBahiaSpecialTransferPayments(
      await paymentsResponse.json(),
    );
    const ranking = parseBahiaSpecialTransferRanking(await rankingResponse.json());
    if (payments === null || ranking === null) return { state: "unavailable" };
    return { state: "available", payments, ranking };
  } catch {
    return { state: "unavailable" };
  }
}
