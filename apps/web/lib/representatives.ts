export type FederalRepresentative = Readonly<{
  externalId: string;
  displayName: string;
  civilName: string | null;
  party: string | null;
  stateCode: string | null;
  electoralStatus: string | null;
  mandateStatus: string | null;
  photoUrl: string | null;
  email: string | null;
  birthState: string | null;
  birthCity: string | null;
  education: string | null;
  legislature: number | null;
  territorialLink: string;
  collectedAt: string;
  methodologyVersion: string;
}>;

export type RepresentativesResult =
  | Readonly<{
      state: "available";
      representatives: readonly FederalRepresentative[];
    }>
  | Readonly<{ state: "unavailable" }>;

function optionalString(value: unknown): string | null {
  return typeof value === "string" && value.trim().length > 0 ? value : null;
}

function parseRepresentative(
  row: Record<string, unknown>,
): FederalRepresentative | null {
  const externalId = optionalString(row.external_id);
  const displayName = optionalString(row.display_name);
  const collectedAt = optionalString(row.collected_at);
  const territorialLink = optionalString(row.territorial_link);
  const photoUrl = optionalString(row.photo_url);
  if (
    externalId === null ||
    displayName === null ||
    collectedAt === null ||
    Number.isNaN(Date.parse(collectedAt)) ||
    territorialLink === null ||
    (photoUrl !== null && !photoUrl.startsWith("https://")) ||
    row.methodology_version !== "federal-representatives/1.0.0"
  ) {
    return null;
  }
  return {
    externalId,
    displayName,
    civilName: optionalString(row.civil_name),
    party: optionalString(row.party),
    stateCode: optionalString(row.state_code),
    electoralStatus: optionalString(row.electoral_status),
    mandateStatus: optionalString(row.mandate_status),
    photoUrl,
    email: optionalString(row.email),
    birthState: optionalString(row.birth_state),
    birthCity: optionalString(row.birth_city),
    education: optionalString(row.education),
    legislature:
      typeof row.legislature === "number" && Number.isSafeInteger(row.legislature)
        ? row.legislature
        : null,
    territorialLink,
    collectedAt,
    methodologyVersion: "federal-representatives/1.0.0",
  };
}

export async function getFederalRepresentatives(): Promise<RepresentativesResult> {
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
      `${supabaseUrl}/rest/v1/rpc/get_federal_representatives`,
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
    const representatives: FederalRepresentative[] = [];
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
