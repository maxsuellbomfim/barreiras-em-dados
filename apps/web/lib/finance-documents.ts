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
  methodologyVersion: "public-finance-documents/1.5.0";
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
    row.methodology_version !== "public-finance-documents/1.5.0" ||
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
    methodologyVersion: "public-finance-documents/1.5.0",
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

export function financeResourceLabel(resource: string): string {
  const labels: Record<string, string> = {
    balancetes: "Balancetes mensais",
    "pdc-contas-anuais": "Contas anuais",
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
