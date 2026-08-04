export type Councillor = Readonly<{
  councillorId: string;
  displayName: string;
  party: string | null;
  mandates: string | null;
  biography: string | null;
  photoUrl: string | null;
  sourceUrl: string;
  collectedAt: string;
  methodologyVersion: string;
}>;

export type CouncillorsResult =
  | Readonly<{ state: "available"; councillors: readonly Councillor[] }>
  | Readonly<{ state: "unavailable" }>;

function optionalString(value: unknown): string | null {
  return typeof value === "string" && value.trim().length > 0 ? value : null;
}

function parseCouncillor(row: Record<string, unknown>): Councillor | null {
  const councillorId = optionalString(row.councillor_id);
  const displayName = optionalString(row.display_name);
  const collectedAt = optionalString(row.collected_at);
  const sourceUrl = optionalString(row.source_url);
  const photoUrl = optionalString(row.photo_url);
  if (
    councillorId === null ||
    displayName === null ||
    collectedAt === null ||
    Number.isNaN(Date.parse(collectedAt)) ||
    sourceUrl === null ||
    !sourceUrl.startsWith("https://") ||
    (photoUrl !== null && !photoUrl.startsWith("https://")) ||
    row.methodology_version !== "municipal-councillors/1.0.0"
  ) {
    return null;
  }
  return {
    councillorId,
    displayName,
    party: optionalString(row.party),
    mandates: optionalString(row.mandates),
    biography: optionalString(row.biography),
    photoUrl,
    sourceUrl,
    collectedAt,
    methodologyVersion: "municipal-councillors/1.0.0",
  };
}

export async function getMunicipalCouncillors(): Promise<CouncillorsResult> {
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
      `${supabaseUrl}/rest/v1/rpc/get_municipal_councillors`,
      {
        method: "POST",
        headers: {
          Accept: "application/json",
          "Accept-Profile": "api",
          apikey: publishableKey,
          "Content-Profile": "api",
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ page_size: 60 }),
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
    const councillors: Councillor[] = [];
    for (const row of payload) {
      const councillor = parseCouncillor(row as Record<string, unknown>);
      if (councillor === null) {
        return { state: "unavailable" };
      }
      councillors.push(councillor);
    }
    return { state: "available", councillors };
  } catch {
    return { state: "unavailable" };
  }
}
