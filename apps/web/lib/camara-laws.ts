export type CamaraLaw = Readonly<{
  lawId: string;
  publicationDate: string | null;
  referenceYear: number | null;
  lawType: string | null;
  title: string | null;
  summary: string | null;
  sourceUrl: string | null;
  active: boolean | null;
  collectedAt: string;
  methodologyVersion: string;
}>;

export type CamaraLawsResult =
  | Readonly<{ state: "available"; laws: readonly CamaraLaw[] }>
  | Readonly<{ state: "unavailable" }>;

function optionalString(value: unknown): string | null {
  return typeof value === "string" && value.trim().length > 0 ? value : null;
}

function parseLaw(row: Record<string, unknown>): CamaraLaw | null {
  const lawId = optionalString(row.law_id);
  const collectedAt = optionalString(row.collected_at);
  if (
    lawId === null ||
    collectedAt === null ||
    Number.isNaN(Date.parse(collectedAt)) ||
    row.methodology_version !== "camara-laws/1.0.0"
  ) {
    return null;
  }
  const referenceYear =
    typeof row.reference_year === "number" &&
    Number.isSafeInteger(row.reference_year)
      ? row.reference_year
      : null;
  const sourceUrl = optionalString(row.source_url);
  if (sourceUrl !== null && !sourceUrl.startsWith("https://")) {
    return null;
  }
  return {
    lawId,
    publicationDate: optionalString(row.publication_date),
    referenceYear,
    lawType: optionalString(row.law_type),
    title: optionalString(row.title),
    summary: optionalString(row.summary),
    sourceUrl,
    active: typeof row.active === "boolean" ? row.active : null,
    collectedAt,
    methodologyVersion: "camara-laws/1.0.0",
  };
}

export async function getCamaraLaws(): Promise<CamaraLawsResult> {
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
      `${supabaseUrl}/rest/v1/rpc/get_camara_laws`,
      {
        method: "POST",
        headers: {
          Accept: "application/json",
          "Accept-Profile": "api",
          apikey: publishableKey,
          "Content-Profile": "api",
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ page_size: 500 }),
        next: { revalidate: 900 },
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
    const laws: CamaraLaw[] = [];
    for (const row of payload) {
      const law = parseLaw(row as Record<string, unknown>);
      if (law === null) {
        return { state: "unavailable" };
      }
      laws.push(law);
    }
    return { state: "available", laws };
  } catch {
    return { state: "unavailable" };
  }
}
