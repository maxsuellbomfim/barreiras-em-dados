import {
  groupPaymentsByCommitment,
  parseCommitmentPaymentRows,
  type CommitmentPayment,
} from "./commitment-payments.mjs";

export type { CommitmentPayment } from "./commitment-payments.mjs";

export type CommitmentPaymentsResult =
  | Readonly<{
      state: "available";
      byCommitment: ReadonlyMap<string, readonly CommitmentPayment[]>;
    }>
  | Readonly<{ state: "unavailable" }>;

export async function getPaymentsForCommitments(
  commitmentKeys: readonly string[],
): Promise<CommitmentPaymentsResult> {
  const keys = [...new Set(commitmentKeys.filter((key) => /^O-\d+$/.test(key)))];
  if (keys.length === 0) return { state: "available", byCommitment: new Map() };
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
      `${supabaseUrl}/rest/v1/rpc/get_public_commitment_payments`,
      {
        method: "POST",
        headers: {
          Accept: "application/json",
          "Accept-Profile": "api",
          apikey: publishableKey,
          "Content-Profile": "api",
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ commitment_keys: keys.slice(0, 500) }),
        next: { revalidate: 300 },
        signal: AbortSignal.timeout(5_000),
      },
    );
    if (!response.ok) return { state: "unavailable" };
    const payments = parseCommitmentPaymentRows(await response.json());
    if (payments === null) return { state: "unavailable" };
    return { state: "available", byCommitment: groupPaymentsByCommitment(payments) };
  } catch {
    return { state: "unavailable" };
  }
}
