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

export type CamaraLegislativePage = Readonly<{
  items: readonly CamaraLegislativeItem[];
  totalCount: number;
  page: number;
  pageSize: number;
}>;

export type CamaraLegislativeAuthorSummary = Readonly<{
  authorName: string;
  itemCount: number;
}>;

export type CamaraLegislativeFilters = Readonly<{
  query?: string | null;
  kind?: "lei" | "indicacao" | null;
  year?: number | null;
  author?: string | null;
}>;

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

function publicConfig(): { url: string; key: string } | null {
  const url = process.env.PUBLIC_DATA_SUPABASE_URL?.trim();
  const key = process.env.PUBLIC_DATA_SUPABASE_PUBLISHABLE_KEY?.trim();
  if (!url || !key || !url.startsWith("https://") || !key.startsWith("sb_publishable_")) return null;
  return { url, key };
}

async function fetchPage(page: number, pageSize: number, filters: CamaraLegislativeFilters = {}): Promise<CamaraLegislativePage | null> {
  const config = publicConfig();
  if (!config || !Number.isSafeInteger(page) || page < 1 || page > 1000) return null;
  const response = await fetch(`${config.url}/rest/v1/rpc/get_camara_legislative_page`, {
    method: "POST",
    headers: {
      Accept: "application/json",
      "Accept-Profile": "api",
      apikey: config.key,
      "Content-Profile": "api",
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      page_size: pageSize,
      page_offset: (page - 1) * pageSize,
      item_kind_filter: filters.kind ?? null,
      year_filter: filters.year ?? null,
      author_filter: filters.author?.trim() || null,
      query_filter: filters.query?.trim() || null,
    }),
    next: { revalidate: 900 },
    signal: AbortSignal.timeout(5_000),
  });
  if (!response.ok) return null;
  const payload = await response.json();
  if (!Array.isArray(payload)) return null;
  const items: CamaraLegislativeItem[] = [];
  let totalCount = 0;
  for (const row of payload) {
    const parsed = parseItem(row as Record<string, unknown>);
    const rawTotal = (row as Record<string, unknown>).total_count;
    if (parsed === null || (typeof rawTotal !== "number" && typeof rawTotal !== "string")) return null;
    const numericTotal = Number(rawTotal);
    if (!Number.isSafeInteger(numericTotal) || numericTotal < 0) return null;
    totalCount = numericTotal;
    items.push(parsed);
  }
  return { items, totalCount, page, pageSize };
}

export async function getCamaraLegislativePage(page = 1, pageSize = 50, filters: CamaraLegislativeFilters = {}): Promise<CamaraLegislativePage | null> {
  if (!Number.isSafeInteger(pageSize) || pageSize < 1 || pageSize > 100) return null;
  try {
    return await fetchPage(page, pageSize, filters);
  } catch {
    return null;
  }
}

export async function getCamaraLegislativeAuthorSummary(filters: CamaraLegislativeFilters = {}): Promise<readonly CamaraLegislativeAuthorSummary[]> {
  const config = publicConfig();
  if (!config) return [];
  try {
    const response = await fetch(`${config.url}/rest/v1/rpc/get_camara_legislative_author_summary`, {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Accept-Profile": "api",
        apikey: config.key,
        "Content-Profile": "api",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        item_kind_filter: filters.kind ?? null,
        year_filter: filters.year ?? null,
        author_filter: filters.author?.trim() || null,
        query_filter: filters.query?.trim() || null,
      }),
      next: { revalidate: 900 },
      signal: AbortSignal.timeout(5_000),
    });
    if (!response.ok) return [];
    const payload = await response.json();
    if (!Array.isArray(payload)) return [];
    const summaries: CamaraLegislativeAuthorSummary[] = [];
    for (const row of payload) {
      const record = row as Record<string, unknown>;
      const authorName = optionalString(record.author_name);
      const rawCount = record.item_count;
      const itemCount = typeof rawCount === "number" || typeof rawCount === "string" ? Number(rawCount) : NaN;
      if (!authorName || !Number.isSafeInteger(itemCount) || itemCount < 1) return [];
      summaries.push({ authorName, itemCount });
    }
    return summaries;
  } catch {
    return [];
  }
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
