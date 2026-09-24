import {
  groupLinksByContract,
  parseCommitmentLinkRows,
  type CommitmentLink,
} from "./commitment-links.mjs";

export type { CommitmentLink } from "./commitment-links.mjs";

export type CommitmentLinksResult =
  | Readonly<{
      state: "available";
      byContract: ReadonlyMap<string, readonly CommitmentLink[]>;
    }>
  | Readonly<{ state: "unavailable" }>;

export async function getCommitmentLinksForContracts(
  contractIds: readonly string[],
): Promise<CommitmentLinksResult> {
  const ids = [...new Set(contractIds.filter((id) => /^\d{1,10}$/.test(id)))];
  if (ids.length === 0) return { state: "available", byContract: new Map() };
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
      `${supabaseUrl}/rest/v1/rpc/get_public_commitment_contract_links`,
      {
        method: "POST",
        headers: {
          Accept: "application/json",
          "Accept-Profile": "api",
          apikey: publishableKey,
          "Content-Profile": "api",
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ contract_ids: ids.slice(0, 200) }),
        next: { revalidate: 300 },
        signal: AbortSignal.timeout(5_000),
      },
    );
    if (!response.ok) return { state: "unavailable" };
    const links = parseCommitmentLinkRows(await response.json());
    if (links === null) return { state: "unavailable" };
    return { state: "available", byContract: groupLinksByContract(links) };
  } catch {
    return { state: "unavailable" };
  }
}
