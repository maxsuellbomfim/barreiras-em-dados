export type CamaraLegislativeItem = Readonly<{
  itemId: string;
  itemKind: "lei" | "indicacao";
  protocolNumber: string | null;
  publicationDate: string | null;
  referenceYear: number | null;
  itemType: string | null;
  title: string | null;
  summary: string | null;
  authorName: string | null;
  situation: string | null;
  sourceUrl: string | null;
  active: boolean | null;
  collectedAt: string;
  methodologyVersion: string;
}>;

export type CamaraLegislativeResult =
  | Readonly<{ state: "available"; items: readonly CamaraLegislativeItem[] }>
  | Readonly<{ state: "unavailable" }>;

function optionalString(value: unknown): string | null {
  return typeof value === "string" && value.trim().length > 0 ? value.trim() : null;
}

function parseItem(row: Record<string, unknown>): CamaraLegislativeItem | null {
  const itemId = optionalString(row.item_id);
  const itemKind = row.item_kind === "lei" || row.item_kind === "indicacao" ? row.item_kind : null;
  const collectedAt = optionalString(row.collected_at);
  const methodologyVersion = optionalString(row.methodology_version);
  if (!itemId || !itemKind || !collectedAt || Number.isNaN(Date.parse(collectedAt))) return null;
  if (methodologyVersion !== "camara-legislative/1.0.0") return null;
  const referenceYear = typeof row.reference_year === "number" && Number.isSafeInteger(row.reference_year)
    ? row.reference_year
    : null;
  const sourceUrl = optionalString(row.source_url);
  if (sourceUrl !== null && !sourceUrl.startsWith("https://")) return null;
  return {
    itemId,
    itemKind,
    protocolNumber: optionalString(row.protocol_number),
    publicationDate: optionalString(row.publication_date),
    referenceYear,
    itemType: optionalString(row.item_type),
    title: optionalString(row.title),
    summary: optionalString(row.summary),
    authorName: optionalString(row.author_name),
    situation: optionalString(row.situation),
    sourceUrl,
    active: typeof row.active === "boolean" ? row.active : null,
    collectedAt,
    methodologyVersion,
  };
}

export async function getCamaraLegislativeItems(): Promise<CamaraLegislativeResult> {
  const supabaseUrl = process.env.PUBLIC_DATA_SUPABASE_URL?.trim();
  const publishableKey = process.env.PUBLIC_DATA_SUPABASE_PUBLISHABLE_KEY?.trim();
  if (!supabaseUrl || !publishableKey || !supabaseUrl.startsWith("https://") || !publishableKey.startsWith("sb_publishable_")) {
    return { state: "unavailable" };
  }
  try {
    const response = await fetch(`${supabaseUrl}/rest/v1/rpc/get_camara_legislative_items`, {
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
    });
    if (!response.ok) return { state: "unavailable" };
    const payload = await response.json();
    if (!Array.isArray(payload)) return { state: "unavailable" };
    const items: CamaraLegislativeItem[] = [];
    for (const row of payload) {
      const item = parseItem(row as Record<string, unknown>);
      if (item === null) return { state: "unavailable" };
      items.push(item);
    }
    return { state: "available", items };
  } catch {
    return { state: "unavailable" };
  }
}
