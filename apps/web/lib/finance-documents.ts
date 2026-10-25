export type PublicFinanceDocument = Readonly<{
  documentId: string;
  sourceResource: string;
  title: string;
  referenceDate: string | null;
  fiscalYear: number | null;
  referenceMonth: number | null;
  description: string | null;
  documentUrl: string;
  apiSourceUrl: string;
  artifactSha256: string;
  collectedAt: string;
  sourceStatus: "api_response_preserved";
  methodologyVersion: "public-finance-documents/1.6.0";
  documentArtifactSha256: string | null;
  documentPreserved: boolean;
}>;

export type FinanceDocumentsResult =
  | Readonly<{
      state: "available";
      documents: readonly PublicFinanceDocument[];
    }>
  | Readonly<{ state: "unavailable" }>;

const SHA256 = /^[0-9a-f]{64}$/;

export const FINANCE_DOCUMENT_RESOURCES = [
  "balancetes", "pdc-contas-anuais", "pdc-receita-tributaria",
  "pdc-recursos-extraordinarios", "pdc-resumo-execucao-da-receita",
  "pdc-resumo-execucao-da-despesa", "pdc-transferencia",
  "pdc-emendas-parlamentares-receitas", "pdc-convenios-transferencias-realizadas",
  "pdc-obras-pdc", "rreo", "rgf",
] as const;
export const FINANCE_DOCUMENT_PAGE_SIZE = 25;
export type FinanceDocumentPageResult =
  | Readonly<{state: "available"; totalCount: number; availableYears: readonly number[];
      documents: readonly PublicFinanceDocument[]; page: number}>
  | Readonly<{state: "unavailable"}>;

export async function getPublicFinanceDocumentPage(
  year: number | null = null, resource: string | null = null, page = 1,
): Promise<FinanceDocumentPageResult> {
  if (!Number.isSafeInteger(page) || page < 1 || page > 100000 ||
      (year !== null && (!Number.isSafeInteger(year) || year < 1900 || year > 2100)) ||
      (resource !== null && !FINANCE_DOCUMENT_RESOURCES.some(value => value === resource))) {
    return {state: "unavailable"};
  }
  const url = process.env.PUBLIC_DATA_SUPABASE_URL?.trim();
  const key = process.env.PUBLIC_DATA_SUPABASE_PUBLISHABLE_KEY?.trim();
  if (!url?.startsWith("https://") || !key?.startsWith("sb_publishable_")) return {state:"unavailable"};
  try {
    const response = await fetch(`${url}/rest/v1/rpc/get_public_finance_document_page`, {
      method:"POST", headers: {apikey:key,"Accept-Profile":"api","Content-Profile":"api","Content-Type":"application/json"},
      body:JSON.stringify({page_size:FINANCE_DOCUMENT_PAGE_SIZE,page_number:page,year_filter:year,resource_filter:resource}),
      next:{revalidate:300},signal:AbortSignal.timeout(5000),
    });
    if (!response.ok) return {state:"unavailable"};
    const payload: unknown = await response.json();
    if (!Array.isArray(payload) || payload.length !== 1) return {state:"unavailable"};
    const row = payload[0];
    if (!row || !Number.isSafeInteger(row.total_count) || row.total_count < 0 ||
        !Array.isArray(row.items) || !Array.isArray(row.available_years) ||
        !row.available_years.every((value:unknown) => typeof value === "number" && Number.isInteger(value) && value>=1900 && value<=2100) ||
        row.items.length !== Math.min(FINANCE_DOCUMENT_PAGE_SIZE,Math.max(0,row.total_count-(page-1)*FINANCE_DOCUMENT_PAGE_SIZE))) return {state:"unavailable"};
    const documents: PublicFinanceDocument[] = [];
    const ids = new Set<string>();
    for (const value of row.items) {
      if (!value || typeof value !== "object") return {state:"unavailable"};
      const document = parseDocument(value);
      if (!document || ids.has(document.documentId) ||
          (year !== null && document.fiscalYear !== year) ||
          (resource !== null && document.sourceResource !== resource)) return {state:"unavailable"};
      ids.add(document.documentId); documents.push(document);
    }
    return {state:"available",totalCount:row.total_count,availableYears:row.available_years,documents,page};
  } catch { return {state:"unavailable"}; }
}

function text(value: unknown): string | null {
  return typeof value === "string" && value.trim().length > 0 ? value.trim() : null;
}

function positiveInteger(value: unknown): number | null {
  return typeof value === "number" && Number.isSafeInteger(value) && value > 0
    ? value
    : null;
}

function parseDocument(row: Record<string, unknown>): PublicFinanceDocument | null {
  const documentId = text(row.document_id);
  const sourceResource = text(row.source_resource);
  const title = text(row.title);
  const documentUrl = text(row.document_url);
  const apiSourceUrl = text(row.api_source_url);
  const artifactSha256 = text(row.artifact_sha256);
  const collectedAt = text(row.collected_at);
  if (
    !documentId ||
    !sourceResource ||
    !title ||
    !documentUrl?.startsWith("https://") ||
    !apiSourceUrl?.startsWith("https://") ||
    !artifactSha256 ||
    !SHA256.test(artifactSha256) ||
    !collectedAt ||
    Number.isNaN(Date.parse(collectedAt)) ||
    row.source_status !== "api_response_preserved" ||
    row.methodology_version !== "public-finance-documents/1.6.0" ||
    typeof row.document_preserved !== "boolean"
  ) {
    return null;
  }

  const fiscalYear = row.fiscal_year === null ? null : positiveInteger(row.fiscal_year);
  const referenceMonth =
    row.reference_month === null ? null : positiveInteger(row.reference_month);
  if (row.fiscal_year !== null && fiscalYear === null) return null;
  if (row.reference_month !== null && referenceMonth === null) return null;

  return {
    documentId,
    sourceResource,
    title,
    referenceDate: text(row.reference_date),
    fiscalYear,
    referenceMonth,
    description: text(row.description),
    documentUrl,
    apiSourceUrl,
    artifactSha256,
    collectedAt,
    sourceStatus: "api_response_preserved",
    methodologyVersion: "public-finance-documents/1.6.0",
    documentArtifactSha256: text(row.document_artifact_sha256),
    documentPreserved: row.document_preserved,
  };
}

export async function getPublicFinanceDocuments(
  resource?: string,
): Promise<FinanceDocumentsResult> {
  const supabaseUrl = process.env.PUBLIC_DATA_SUPABASE_URL?.trim();
  const publishableKey = process.env.PUBLIC_DATA_SUPABASE_PUBLISHABLE_KEY?.trim();
  if (
    !supabaseUrl?.startsWith("https://") ||
    !publishableKey?.startsWith("sb_publishable_")
  ) {
    return { state: "unavailable" };
  }

  try {
    const response = await fetch(`${supabaseUrl}/rest/v1/rpc/get_public_finance_documents`, {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Accept-Profile": "api",
        apikey: publishableKey,
        "Content-Profile": "api",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        page_size: 200,
        resource_filter: resource ?? null,
      }),
      next: { revalidate: 300 },
      signal: AbortSignal.timeout(5_000),
    });
    if (!response.ok) return { state: "unavailable" };
    const payload = await response.json();
    if (!Array.isArray(payload)) return { state: "unavailable" };
    const documents: PublicFinanceDocument[] = [];
    for (const row of payload) {
      if (typeof row !== "object" || row === null) return { state: "unavailable" };
      const document = parseDocument(row as Record<string, unknown>);
      if (!document) return { state: "unavailable" };
      documents.push(document);
    }
    return { state: "available", documents };
  } catch {
    return { state: "unavailable" };
  }
}

export function mergePublicFinanceDocumentResults(
  ...results: readonly FinanceDocumentsResult[]
): PublicFinanceDocument[] {
  const documents = new Map<string, PublicFinanceDocument>();
  for (const result of results) {
    if (result.state !== "available") continue;
    for (const document of result.documents) {
      if (!documents.has(document.documentId)) {
        documents.set(document.documentId, document);
      }
    }
  }
  return [...documents.values()];
}

// Successful limited responses are available, never proof of a complete archive.
export function getFinanceDocumentConsultationState(
  ...results: readonly FinanceDocumentsResult[]
): "available" | "partial" | "unavailable" {
  const available = results.filter((result) => result.state === "available").length;
  if (available === 0) return "unavailable";
  return available === results.length ? "available" : "partial";
}

export function financeResourceLabel(resource: string): string {
  const labels: Record<string, string> = {
    balancetes: "Balancetes mensais",
    "pdc-contas-anuais": "Legislação de controle e prestação de contas",
    "pdc-receita-tributaria": "Receita tributaria",
    "pdc-recursos-extraordinarios": "Receitas extraorcamentarias",
    "pdc-resumo-execucao-da-receita": "Execucao da receita",
    "pdc-resumo-execucao-da-despesa": "Execucao da despesa",
    "pdc-transferencia": "Transferencias recebidas",
    "pdc-emendas-parlamentares-receitas": "Emendas e receitas",
    "pdc-convenios-transferencias-realizadas": "Transferencias concedidas",
    "pdc-obras-pdc": "Obras e prestacao de contas",
    rreo: "RREO",
    rgf: "RGF",
  };
  return labels[resource] ?? resource;
}
