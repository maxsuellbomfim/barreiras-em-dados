export type PublicDiaryCoverageItem = Readonly<{
  coverageDay: string;
  status: "complete" | "empty" | "unclassified";
  preservedEditions: number;
  preservedDocuments: number;
}>;

export type PublicDiaryCoverageResult =
  | Readonly<{ state: "available"; items: readonly PublicDiaryCoverageItem[] }>
  | Readonly<{ state: "unavailable" }>;

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;

function nonNegativeInteger(value: unknown): value is number {
  return Number.isSafeInteger(value) && Number(value) >= 0;
}

function parseItem(value: unknown): PublicDiaryCoverageItem | null {
  if (typeof value !== "object" || value === null) return null;
  const row = value as Record<string, unknown>;
  if (
    typeof row.coverage_day !== "string" ||
    !ISO_DATE.test(row.coverage_day) ||
    (row.coverage_status !== "complete" &&
      row.coverage_status !== "empty" &&
      row.coverage_status !== "unclassified") ||
    !nonNegativeInteger(row.preserved_editions) ||
    !nonNegativeInteger(row.preserved_documents)
  ) {
    return null;
  }
  return {
    coverageDay: row.coverage_day,
    status: row.coverage_status,
    preservedEditions: row.preserved_editions,
    preservedDocuments: row.preserved_documents,
  };
}

export async function getPublicDiaryCoverage(
  pageSize = 31,
  pageOffset = 0,
): Promise<PublicDiaryCoverageResult> {
  if (
    !Number.isSafeInteger(pageSize) ||
    pageSize < 1 ||
    pageSize > 366 ||
    !Number.isSafeInteger(pageOffset) ||
    pageOffset < 0 ||
    pageOffset > 5000
  ) {
    return { state: "unavailable" };
  }
  const supabaseUrl = process.env.PUBLIC_DATA_SUPABASE_URL?.trim();
  const publishableKey =
    process.env.PUBLIC_DATA_SUPABASE_PUBLISHABLE_KEY?.trim();
  if (
    !supabaseUrl?.startsWith("https://") ||
    !publishableKey?.startsWith("sb_publishable_")
  ) {
    return { state: "unavailable" };
  }
  try {
    const response = await fetch(
      `${supabaseUrl}/rest/v1/rpc/get_public_querido_diario_coverage`,
      {
        method: "POST",
        headers: {
          Accept: "application/json",
          "Accept-Profile": "api",
          apikey: publishableKey,
          "Content-Profile": "api",
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ page_size: pageSize, page_offset: pageOffset }),
        next: { revalidate: 300 },
        signal: AbortSignal.timeout(5_000),
      },
    );
    if (!response.ok) return { state: "unavailable" };
    const payload = await response.json();
    if (!Array.isArray(payload)) return { state: "unavailable" };
    const items: PublicDiaryCoverageItem[] = [];
    for (const row of payload) {
      const item = parseItem(row);
      if (item === null) return { state: "unavailable" };
      items.push(item);
    }
    return { state: "available", items };
  } catch {
    return { state: "unavailable" };
  }
}
