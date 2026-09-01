export type MunicipalControlDocumentSummary = Readonly<{
  documentId: string;
  title: string;
  referenceDate: string | null;
  excerpt: string;
  documentSourceUrl: string;
  documentArtifactSha256: string;
  collectedAt: string;
  methodologyVersion: "municipal-control-text/1.0.0";
}>;

export type MunicipalControlDocument = MunicipalControlDocumentSummary &
  Readonly<{
    description: string | null;
    fullText: string;
    textSha256: string;
    parserVersion: "docx-wordprocessingml/1.0.0";
  }>;

export type MunicipalControlSearchResult =
  | Readonly<{
      state: "available";
      documents: readonly MunicipalControlDocumentSummary[];
      totalCount: number;
    }>
  | Readonly<{ state: "unavailable" }>;

export type MunicipalControlDocumentResult =
  | Readonly<{ state: "available"; document: MunicipalControlDocument }>
  | Readonly<{ state: "not_found" }>
  | Readonly<{ state: "unavailable" }>;

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const SHA256 = /^[0-9a-f]{64}$/;
const METHODOLOGY = "municipal-control-text/1.0.0" as const;
const PARSER = "docx-wordprocessingml/1.0.0" as const;

function text(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function publicDataConfig() {
  const url = process.env.PUBLIC_DATA_SUPABASE_URL?.trim();
  const key = process.env.PUBLIC_DATA_SUPABASE_PUBLISHABLE_KEY?.trim();
  return url?.startsWith("https://") && key?.startsWith("sb_publishable_")
    ? { url, key }
    : null;
}

async function callRpc(name: string, body: object): Promise<unknown[] | null> {
  const config = publicDataConfig();
  if (!config) return null;
  try {
    const response = await fetch(`${config.url}/rest/v1/rpc/${name}`, {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Accept-Profile": "api",
        apikey: config.key,
        "Content-Profile": "api",
        "Content-Type": "application/json",
      },
      body: JSON.stringify(body),
      next: { revalidate: 300 },
      signal: AbortSignal.timeout(5_000),
    });
    if (!response.ok) return null;
    const payload = await response.json();
    return Array.isArray(payload) ? payload : null;
  } catch {
    return null;
  }
}

function parseSummary(
  row: Record<string, unknown>,
): MunicipalControlDocumentSummary | null {
  const documentId = text(row.document_id);
  const title = text(row.title);
  const excerpt = text(row.excerpt);
  const documentSourceUrl = text(row.document_source_url);
  const documentArtifactSha256 = text(row.document_artifact_sha256);
  const collectedAt = text(row.collected_at);
  if (
    !documentId || !UUID.test(documentId) || !title || !excerpt ||
    !documentSourceUrl?.startsWith("https://") ||
    !documentArtifactSha256 || !SHA256.test(documentArtifactSha256) ||
    !collectedAt || Number.isNaN(Date.parse(collectedAt)) ||
    row.methodology_version !== METHODOLOGY
  ) return null;
  return {
    documentId,
    title,
    referenceDate: text(row.reference_date),
    excerpt,
    documentSourceUrl,
    documentArtifactSha256,
    collectedAt,
    methodologyVersion: METHODOLOGY,
  };
}

export async function searchMunicipalControlDocuments({
  query = "",
  pageSize = 20,
  offset = 0,
}: Readonly<{
  query?: string;
  pageSize?: number;
  offset?: number;
}> = {}): Promise<MunicipalControlSearchResult> {
  const safeQuery = query.trim().slice(0, 100);
  const safePageSize = Math.min(50, Math.max(1, Math.trunc(pageSize)));
  const safeOffset = Math.min(10_000, Math.max(0, Math.trunc(offset)));
  const payload = await callRpc("search_public_municipal_control_documents", {
    search_query: safeQuery || null,
    page_size: safePageSize,
    page_offset: safeOffset,
  });
  if (!payload) return { state: "unavailable" };
  const documents: MunicipalControlDocumentSummary[] = [];
  let totalCount = 0;
  for (const value of payload) {
    if (typeof value !== "object" || value === null) return { state: "unavailable" };
    const row = value as Record<string, unknown>;
    const document = parseSummary(row);
    if (!document || typeof row.total_count !== "number" || row.total_count < 0) {
      return { state: "unavailable" };
    }
    totalCount = row.total_count;
    documents.push(document);
  }
  return { state: "available", documents, totalCount };
}

export async function getMunicipalControlDocument(
  documentId: string,
): Promise<MunicipalControlDocumentResult> {
  if (!UUID.test(documentId)) return { state: "not_found" };
  const payload = await callRpc("get_public_municipal_control_document", {
    document_id_filter: documentId,
  });
  if (!payload) return { state: "unavailable" };
  if (payload.length === 0) return { state: "not_found" };
  if (payload.length !== 1 || typeof payload[0] !== "object" || payload[0] === null) {
    return { state: "unavailable" };
  }
  const row = payload[0] as Record<string, unknown>;
  const summary = parseSummary({ ...row, excerpt: row.full_text });
  const fullText = text(row.full_text);
  const textSha256 = text(row.text_sha256);
  if (
    !summary || !fullText || !textSha256 || !SHA256.test(textSha256) ||
    row.parser_version !== PARSER
  ) return { state: "unavailable" };
  return {
    state: "available",
    document: {
      ...summary,
      description: text(row.description),
      fullText,
      textSha256,
      parserVersion: PARSER,
    },
  };
}
