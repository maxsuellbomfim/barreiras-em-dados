import type { OfficialDiaryCatalogEntry } from "./official-diary-catalog";

export type GazetteDocument = Readonly<{
  documentId: string;
  documentOrder: number;
  literalTitle: string;
  documentType: string | null;
  pageStart: number;
  pageEnd: number;
  fullText: string;
  textSha256: string;
  publicationStatus: "validated" | "edition_fallback";
}>;

export type IntegralGazetteEdition = Readonly<{
  edition: number;
  editionYear: number;
  editionDate: string | null;
  artifactSha256: string;
  documents: readonly GazetteDocument[];
  methodologyVersion: "integral-gazette-documents/1.0.0";
  officialPublicationUrl: string | null;
  catalogUrl: string | null;
  catalogDate: string | null;
}>;

export type IntegralGazetteResult =
  | Readonly<{
      state: "available";
      editions: readonly IntegralGazetteEdition[];
      pageSize: number;
      offset: number;
      hasMore: boolean;
    }>
  | Readonly<{ state: "unavailable" }>;

export type IntegralGazettePageOptions = Readonly<{
  pageSize?: number;
  offset?: number;
  query?: string;
}>;

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;
const SHA256 = /^[0-9a-f]{64}$/;
const STATUSES = new Set(["validated", "edition_fallback"]);

function positiveInteger(value: unknown): value is number {
  return typeof value === "number" && Number.isSafeInteger(value) && value > 0;
}

function optionalString(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function optionalHttpsUrl(value: unknown): string | null {
  const valueString = optionalString(value);
  return valueString?.startsWith("https://") ? valueString : null;
}

function parseDocument(value: unknown): GazetteDocument | null {
  if (typeof value !== "object" || value === null) return null;
  const row = value as Record<string, unknown>;
  const documentOrder = row.document_order;
  const pageStart = row.page_start;
  const pageEnd = row.page_end;
  const fullText = row.full_text;
  const literalTitle = row.literal_title;
  const textSha256 = row.text_sha256;
  const publicationStatus = row.publication_status;
  if (
    typeof row.document_id !== "string" ||
    !row.document_id.trim() ||
    !positiveInteger(documentOrder) ||
    !positiveInteger(pageStart) ||
    !positiveInteger(pageEnd) ||
    pageEnd < pageStart ||
    typeof literalTitle !== "string" ||
    !literalTitle.trim() ||
    typeof fullText !== "string" ||
    !fullText.trim() ||
    typeof textSha256 !== "string" ||
    !SHA256.test(textSha256) ||
    typeof publicationStatus !== "string" ||
    !STATUSES.has(publicationStatus)
  ) {
    return null;
  }
  if (!fullText.includes(literalTitle)) return null;
  return {
    documentId: row.document_id,
    documentOrder,
    literalTitle,
    documentType: optionalString(row.document_type),
    pageStart,
    pageEnd,
    fullText,
    textSha256,
    publicationStatus: publicationStatus as GazetteDocument["publicationStatus"],
  };
}

function parseIntegralGazetteEdition(
  value: unknown,
): IntegralGazetteEdition | null {
  if (typeof value !== "object" || value === null) return null;
  const row = value as Record<string, unknown>;
  const edition = row.edition;
  const editionYear = row.edition_year;
  const editionDate = row.edition_date;
  const artifactSha256 = row.artifact_sha256;
  if (
    !positiveInteger(edition) ||
    !positiveInteger(editionYear) ||
    editionYear < 2000 ||
    editionYear > 2100 ||
    (editionDate !== null &&
      (typeof editionDate !== "string" || !ISO_DATE.test(editionDate))) ||
    typeof artifactSha256 !== "string" ||
    !SHA256.test(artifactSha256) ||
    row.methodology_version !== "integral-gazette-documents/1.0.0" ||
    !Array.isArray(row.documents) ||
    row.documents.length === 0
  ) {
    return null;
  }
  const documents: GazetteDocument[] = [];
  const orders = new Set<number>();
  for (const rawDocument of row.documents) {
    const document = parseDocument(rawDocument);
    if (document === null || orders.has(document.documentOrder)) return null;
    orders.add(document.documentOrder);
    documents.push(document);
  }
  documents.sort((left, right) => left.documentOrder - right.documentOrder);
  if (
    documents.some(
      (document, index) => document.documentOrder !== index + 1,
    )
  ) {
    return null;
  }
  return {
    edition,
    editionYear,
    editionDate,
    artifactSha256,
    documents,
    methodologyVersion: "integral-gazette-documents/1.0.0",
    officialPublicationUrl: null,
    catalogUrl: null,
    catalogDate: null,
  };
}

export function enrichIntegralGazetteEditions(
  editions: readonly IntegralGazetteEdition[],
  catalogEntries: readonly OfficialDiaryCatalogEntry[],
): readonly IntegralGazetteEdition[] {
  const byEdition = new Map(
    catalogEntries.map((entry) => [
      `${entry.editionYear}:${entry.edition}`,
      entry,
    ]),
  );
  return editions.map((edition) => {
    const catalog = byEdition.get(
      `${edition.editionYear}:${edition.edition}`,
    );
    if (!catalog) return edition;
    return {
      ...edition,
      officialPublicationUrl: catalog.officialPublicationUrl,
      catalogUrl: catalog.catalogUrl,
      catalogDate: catalog.editionDate,
    };
  });
}

export async function getIntegralGazetteEditions(
  options: IntegralGazettePageOptions = {},
): Promise<IntegralGazetteResult> {
  const pageSize = options.pageSize ?? 20;
  const offset = options.offset ?? 0;
  const query = options.query?.trim() ?? "";
  if (
    !positiveInteger(pageSize) ||
    pageSize > 100 ||
    !Number.isSafeInteger(offset) ||
    offset < 0 ||
    query.length > 120
  ) {
    return { state: "unavailable" };
  }
  // One extra row lets the page render a reliable "mais antigas" link
  // without loading the whole archive or maintaining a second count query.
  const requestPageSize = pageSize + 1;
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
      `${supabaseUrl}/rest/v1/rpc/${query ? "search_integral_gazette_editions" : "get_integral_gazette_editions_page"}`,
      {
        method: "POST",
        headers: {
          Accept: "application/json",
          "Accept-Profile": "api",
          apikey: publishableKey,
          "Content-Profile": "api",
          "Content-Type": "application/json",
        },
        body: JSON.stringify(
          query
            ? {
                query_text: query,
                page_size: requestPageSize,
                page_offset: offset,
              }
            : {
                page_size: requestPageSize,
                page_offset: offset,
              },
        ),
        next: { revalidate: 300 },
        signal: AbortSignal.timeout(5_000),
      },
    );
    if (!response.ok) return { state: "unavailable" };
    const payload = await response.json();
    if (!Array.isArray(payload)) return { state: "unavailable" };
    const editions: IntegralGazetteEdition[] = [];
    for (const row of payload) {
      const edition = parseIntegralGazetteEdition(row);
      if (edition === null) return { state: "unavailable" };
      editions.push(edition);
    }
    editions.sort(
      (left, right) =>
        right.editionYear - left.editionYear || right.edition - left.edition,
    );
    const hasMore = editions.length > pageSize;
    return {
      state: "available",
      editions: hasMore ? editions.slice(0, pageSize) : editions,
      pageSize,
      offset,
      hasMore,
    };
  } catch {
    return { state: "unavailable" };
  }
}
