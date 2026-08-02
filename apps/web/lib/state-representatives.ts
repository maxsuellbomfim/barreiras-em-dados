export type StateRepresentative = Readonly<{
  externalId: string;
  displayName: string;
  profileUrl: string;
  collectedAt: string;
  methodologyVersion: string;
}>;

export type StateRepresentativesResult =
  | Readonly<{
      state: "available";
      representatives: readonly StateRepresentative[];
    }>
  | Readonly<{ state: "unavailable" }>;

function optionalString(value: unknown): string | null {
  return typeof value === "string" && value.trim().length > 0 ? value : null;
}

function parseRepresentative(
  row: Record<string, unknown>,
): StateRepresentative | null {
  const externalId = optionalString(row.external_id);
  const displayName = optionalString(row.display_name);
  const profileUrl = optionalString(row.profile_url);
  const collectedAt = optionalString(row.collected_at);
  if (
    externalId === null ||
    !/^\d+$/.test(externalId) ||
    displayName === null ||
    profileUrl === null ||
    !/^https:\/\/www\.al\.ba\.gov\.br\/deputados\/deputado-estadual\/\d+$/.test(
      profileUrl,
    ) ||
    collectedAt === null ||
    Number.isNaN(Date.parse(collectedAt)) ||
    row.methodology_version !== "state-representatives/alba/1.0.0"
  ) {
    return null;
  }
  return {
    externalId,
    displayName,
    profileUrl,
    collectedAt,
    methodologyVersion: "state-representatives/alba/1.0.0",
  };
}

export async function getStateRepresentatives(): Promise<StateRepresentativesResult> {
  const supabaseUrl = process.env.PUBLIC_DATA_SUPABASE_URL?.trim();
  const publishableKey =
    process.env.PUBLIC_DATA_SUPABASE_PUBLISHABLE_KEY?.trim();
  if (
    !supabaseUrl ||
    !publishableKey ||
    !supabaseUrl.startsWith("https://") ||
    !publishableKey.startsWith("sb_publishable_")
  ) {
    return { state: "unavailable" };
  }

  try {
    const response = await fetch(
      `${supabaseUrl}/rest/v1/rpc/get_state_representatives`,
      {
        method: "POST",
        headers: {
          Accept: "application/json",
          "Accept-Profile": "api",
          apikey: publishableKey,
          "Content-Profile": "api",
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ page_size: 100 }),
        next: { revalidate: 300 },
        signal: AbortSignal.timeout(5_000),
      },
    );
    if (!response.ok) {
      return { state: "unavailable" };
    }
    const payload = await response.json();
    if (!Array.isArray(payload)) {
      return { state: "unavailable" };
    }
    const representatives: StateRepresentative[] = [];
    for (const row of payload) {
      const representative = parseRepresentative(
        row as Record<string, unknown>,
      );
      if (representative === null) {
        return { state: "unavailable" };
      }
      representatives.push(representative);
    }
    return { state: "available", representatives };
  } catch {
    return { state: "unavailable" };
  }
}
