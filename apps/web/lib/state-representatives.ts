import { fetchPublicRpcRows } from "./public-rpc.mjs";

export type StateRepresentative = Readonly<{
  externalId: string;
  displayName: string;
  profileUrl: string;
  photoUrl: string | null;
  education: string | null;
  professionalActivity: string | null;
  electiveMandate: string | null;
  parliamentaryActivity: string | null;
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
  const photoUrl = optionalString(row.photo_url);
  const education = optionalString(row.education);
  const professionalActivity = optionalString(row.professional_activity);
  const electiveMandate = optionalString(row.elective_mandate);
  const parliamentaryActivity = optionalString(row.parliamentary_activity);
  const collectedAt = optionalString(row.collected_at);
  if (
    externalId === null ||
    !/^\d+$/.test(externalId) ||
    displayName === null ||
    profileUrl === null ||
    !/^https:\/\/www\.al\.ba\.gov\.br\/deputados\/deputado-estadual\/\d+$/.test(
      profileUrl,
    ) ||
    (photoUrl !== null && !/^https:\/\/www\.al\.ba\.gov\.br\/fserver\//.test(photoUrl)) ||
    collectedAt === null ||
    Number.isNaN(Date.parse(collectedAt)) ||
    row.methodology_version !== "state-representatives/alba/1.2.0"
  ) {
    return null;
  }
  return {
    externalId,
    displayName,
    profileUrl,
    photoUrl,
    education,
    professionalActivity,
    electiveMandate,
    parliamentaryActivity,
    collectedAt,
    methodologyVersion: "state-representatives/alba/1.2.0",
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
    const payload = await fetchPublicRpcRows({
      url: `${supabaseUrl}/rest/v1/rpc/get_state_representatives`,
      headers: {
        Accept: "application/json",
        "Accept-Profile": "api",
        apikey: publishableKey,
        "Content-Profile": "api",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ page_size: 100 }),
    });
    if (payload === null) {
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
