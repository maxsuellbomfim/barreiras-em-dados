export type OfficialDiaryCatalogEntry = Readonly<{
  catalogId: string;
  edition: number;
  editionYear: number;
  editionDate: string;
  officialTitle: string | null;
  officialSummary: string | null;
  officialPublicationUrl: string | null;
  catalogUrl: string | null;
  artifactSha256: string;
  collectedAt: string;
  methodologyVersion: "official-diary-catalog/1.0.0";
}>;

export type OfficialDiaryCatalogResult =
  | Readonly<{
      state: "available";
      entries: readonly OfficialDiaryCatalogEntry[];
    }>
  | Readonly<{ state: "unavailable" }>;

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;
const SHA256 = /^[0-9a-f]{64}$/;

function optionalString(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function optionalHttpsUrl(value: unknown): string | null {
  const url = optionalString(value);
  return url?.startsWith("https://") ? url : null;
}

function parseEntry(
  row: Record<string, unknown>,
): OfficialDiaryCatalogEntry | null {
  const edition = row.edition;
  const editionYear = row.edition_year;
  const editionDate = row.edition_date;
  const artifactSha256 = row.artifact_sha256;
  const collectedAt = row.collected_at;
  if (
    typeof row.catalog_id !== "string" ||
    !Number.isSafeInteger(edition) ||
    !Number.isSafeInteger(editionYear) ||
    typeof editionDate !== "string" ||
    !ISO_DATE.test(editionDate) ||
    typeof artifactSha256 !== "string" ||
    !SHA256.test(artifactSha256) ||
    typeof collectedAt !== "string" ||
    Number.isNaN(Date.parse(collectedAt)) ||
    row.methodology_version !== "official-diary-catalog/1.0.0"
  ) {
    return null;
  }
  return {
    catalogId: row.catalog_id,
    edition: Number(edition),
    editionYear: Number(editionYear),
    editionDate,
    officialTitle: optionalString(row.official_title),
    officialSummary: optionalString(row.official_summary),
    officialPublicationUrl: optionalHttpsUrl(row.official_publication_url),
    catalogUrl: optionalHttpsUrl(row.catalog_url),
    artifactSha256,
    collectedAt,
    methodologyVersion: "official-diary-catalog/1.0.0",
  };
}

export async function getOfficialDiaryCatalog(): Promise<OfficialDiaryCatalogResult> {
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
      supabaseUrl + "/rest/v1/rpc/get_official_diary_catalog",
      {
        method: "POST",
        headers: {
          Accept: "application/json",
          "Accept-Profile": "api",
          apikey: publishableKey,
          "Content-Profile": "api",
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ page_size: 40 }),
        next: { revalidate: 300 },
        signal: AbortSignal.timeout(5_000),
      },
    );
    if (!response.ok) return { state: "unavailable" };
    const payload = await response.json();
    if (!Array.isArray(payload)) return { state: "unavailable" };
    const entries: OfficialDiaryCatalogEntry[] = [];
    for (const row of payload) {
      const entry = parseEntry(row as Record<string, unknown>);
      if (entry === null) return { state: "unavailable" };
      entries.push(entry);
    }
    return { state: "available", entries };
  } catch {
    return { state: "unavailable" };
  }
}
