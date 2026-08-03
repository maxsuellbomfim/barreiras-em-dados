export type ExecutiveProfile = Readonly<{
  profileKey: string;
  role: "prefeito" | "vice-prefeito" | "secretario";
  departmentName: string | null;
  displayName: string;
  profileUrl: string;
  photoUrl: string | null;
  sourceExcerpt: string | null;
  collectedAt: string;
  sourceUrl: string;
  artifactSha256: string;
  methodologyVersion: "executive-profiles/barreiras/1.0.0";
}>;

export type ExecutiveProfilesResult =
  | Readonly<{ state: "available"; profiles: readonly ExecutiveProfile[] }>
  | Readonly<{ state: "unavailable" }>;

type Row = Record<string, unknown>;
const SHA256 = /^[0-9a-f]{64}$/;
const METHODOLOGY = "executive-profiles/barreiras/1.0.0" as const;

function stringValue(value: unknown): string | null {
  return typeof value === "string" && value.trim().length > 0 ? value : null;
}

function parseProfile(row: Row): ExecutiveProfile | null {
  const profileKey = stringValue(row.profile_key);
  const role = row.role;
  const displayName = stringValue(row.display_name);
  const profileUrl = stringValue(row.profile_url);
  const collectedAt = stringValue(row.collected_at);
  const sourceUrl = stringValue(row.source_url);
  const artifactSha256 = stringValue(row.artifact_sha256);
  if (
    profileKey === null ||
    (role !== "prefeito" && role !== "vice-prefeito" && role !== "secretario") ||
    displayName === null ||
    profileUrl === null ||
    !profileUrl.startsWith("https://barreiras.ba.gov.br/") ||
    collectedAt === null ||
    Number.isNaN(Date.parse(collectedAt)) ||
    sourceUrl === null ||
    !sourceUrl.startsWith("https://barreiras.ba.gov.br/") ||
    artifactSha256 === null ||
    !SHA256.test(artifactSha256) ||
    row.methodology_version !== METHODOLOGY
  ) {
    return null;
  }
  return {
    profileKey,
    role,
    departmentName: stringValue(row.department_name),
    displayName,
    profileUrl,
    photoUrl: stringValue(row.photo_url),
    sourceExcerpt: stringValue(row.source_excerpt),
    collectedAt,
    sourceUrl,
    artifactSha256,
    methodologyVersion: METHODOLOGY,
  };
}

export async function getExecutiveProfiles(): Promise<ExecutiveProfilesResult> {
  const supabaseUrl = process.env.PUBLIC_DATA_SUPABASE_URL?.trim();
  const publishableKey = process.env.PUBLIC_DATA_SUPABASE_PUBLISHABLE_KEY?.trim();
  if (!supabaseUrl?.startsWith("https://") || !publishableKey?.startsWith("sb_publishable_")) {
    return { state: "unavailable" };
  }
  try {
    const response = await fetch(`${supabaseUrl}/rest/v1/rpc/get_executive_profiles`, {
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
    });
    if (!response.ok) return { state: "unavailable" };
    const payload = await response.json();
    if (!Array.isArray(payload)) return { state: "unavailable" };
    const profiles: ExecutiveProfile[] = [];
    for (const row of payload) {
      const profile = parseProfile(row as Row);
      if (profile === null) return { state: "unavailable" };
      profiles.push(profile);
    }
    return { state: "available", profiles };
  } catch {
    return { state: "unavailable" };
  }
}
