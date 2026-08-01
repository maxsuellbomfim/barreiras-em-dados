export type ApprovedGazetteAct = Readonly<{
  actId: string;
  actType: "nomeacao" | "exoneracao";
  personName: string | null;
  positionTitle: string | null;
  positionSymbol: string | null;
  organization: string | null;
  gazetteDate: string | null;
  gazetteUrl: string | null;
  excerpt: string | null;
  approvedAt: string;
  artifactSha256: string;
  methodologyVersion: string;
}>;

export type ApprovedActsResult =
  | Readonly<{ state: "available"; acts: readonly ApprovedGazetteAct[] }>
  | Readonly<{ state: "unavailable" }>;

type ActRow = Readonly<Record<string, unknown>>;

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;
const SHA256 = /^[0-9a-f]{64}$/;

function optionalString(value: unknown): string | null {
  return typeof value === "string" && value.trim().length > 0 ? value : null;
}

function parseAct(row: ActRow): ApprovedGazetteAct | null {
  const actId = row.act_id;
  const actType = row.act_type;
  const approvedAt = row.approved_at;
  const artifactSha256 = row.artifact_sha256;
  const gazetteDate = optionalString(row.gazette_date);
  const gazetteUrl = optionalString(row.gazette_url);
  if (
    typeof actId !== "string" ||
    (actType !== "nomeacao" && actType !== "exoneracao") ||
    typeof approvedAt !== "string" ||
    Number.isNaN(Date.parse(approvedAt)) ||
    typeof artifactSha256 !== "string" ||
    !SHA256.test(artifactSha256) ||
    (gazetteDate !== null && !ISO_DATE.test(gazetteDate)) ||
    (gazetteUrl !== null && !gazetteUrl.startsWith("https://")) ||
    row.methodology_version !== "approved-gazette-acts/1.0.0"
  ) {
    return null;
  }

  return {
    actId,
    actType,
    personName: optionalString(row.person_name),
    positionTitle: optionalString(row.position_title),
    positionSymbol: optionalString(row.position_symbol),
    organization: optionalString(row.organization),
    gazetteDate,
    gazetteUrl,
    excerpt: optionalString(row.excerpt),
    approvedAt,
    artifactSha256,
    methodologyVersion: "approved-gazette-acts/1.0.0",
  };
}

export async function getApprovedGazetteActs(): Promise<ApprovedActsResult> {
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
      `${supabaseUrl}/rest/v1/rpc/get_approved_gazette_acts`,
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
    const acts: ApprovedGazetteAct[] = [];
    for (const row of payload) {
      const act = parseAct(row as ActRow);
      if (act === null) {
        return { state: "unavailable" };
      }
      acts.push(act);
    }
    return { state: "available", acts };
  } catch {
    return { state: "unavailable" };
  }
}
