import {
  parseCguFederalAmendmentDocumentRankingRows,
  parseCguFederalAmendmentDocumentRows,
} from "./cgu-federal-amendment-documents.mjs";

export type CguFederalAmendmentDocument = Readonly<{
  archiveYear: number;
  amendmentYear: number;
  amendmentCode: string;
  amendmentNumber: string;
  amendmentType: string;
  authorKind: "person" | "commission" | "bench" | "other";
  authorKey: string;
  authorName: string;
  documentDate: string;
  documentCode: string;
  expenseStage: "commitment" | "liquidation" | "payment";
  expenseStageSource: string;
  committedAmount: string;
  paidAmount: string;
  beneficiaryName: string;
  beneficiaryType: string | null;
  beneficiaryMunicipality: string | null;
  locality: string;
  agencyName: string;
  superiorAgencyName: string | null;
  functionName: string | null;
  subfunctionName: string | null;
  programName: string | null;
  actionName: string;
  citizenLanguage: string | null;
  sourceRowNumber: number;
  sourceUrl: string;
  artifactSha256: string;
  collectedAt: string;
  methodologyVersion: string;
}>;

export type CguFederalAmendmentDocumentRanking = Readonly<{
  rankPosition: number;
  authorKind: "person" | "commission" | "bench" | "other";
  authorKey: string;
  authorName: string;
  amendmentCount: number;
  documentCount: number;
  committedAmount: string;
  paidAmount: string;
  firstDocumentDate: string;
  lastDocumentDate: string;
  aggregationPolicy: "single_document_source_no_cross_source_sum";
  methodologyVersion: string;
}>;

export type CguFederalAmendmentDocumentsResult =
  | Readonly<{
      state: "available";
      documents: readonly CguFederalAmendmentDocument[];
      ranking: readonly CguFederalAmendmentDocumentRanking[];
    }>
  | Readonly<{ state: "unavailable" }>;

async function callRpc(
  supabaseUrl: string,
  publishableKey: string,
  functionName: string,
  args: Record<string, unknown>,
): Promise<unknown> {
  const response = await fetch(`${supabaseUrl}/rest/v1/rpc/${functionName}`, {
    method: "POST",
    headers: {
      Accept: "application/json",
      "Accept-Profile": "api",
      apikey: publishableKey,
      "Content-Profile": "api",
      "Content-Type": "application/json",
    },
    body: JSON.stringify(args),
    next: { revalidate: 300 },
    signal: AbortSignal.timeout(5_000),
  });
  if (!response.ok) return null;
  return response.json();
}

export async function getPublicCguFederalAmendmentDocuments(): Promise<
  CguFederalAmendmentDocumentsResult
> {
  const supabaseUrl = process.env.PUBLIC_DATA_SUPABASE_URL?.trim();
  const publishableKey = process.env.PUBLIC_DATA_SUPABASE_PUBLISHABLE_KEY?.trim();
  if (
    !supabaseUrl?.startsWith("https://") ||
    !publishableKey?.startsWith("sb_publishable_")
  ) return { state: "unavailable" };
  try {
    const [documentRows, rankingRows] = await Promise.all([
      callRpc(
        supabaseUrl,
        publishableKey,
        "get_public_cgu_federal_amendment_documents",
        {
          archive_year_filter: null,
          author_key_filter: null,
          page_size: 500,
        },
      ),
      callRpc(
        supabaseUrl,
        publishableKey,
        "get_public_cgu_federal_amendment_document_ranking",
        { archive_year_filter: null, page_size: 50 },
      ),
    ]);
    const documents = parseCguFederalAmendmentDocumentRows(documentRows);
    const ranking = parseCguFederalAmendmentDocumentRankingRows(rankingRows);
    if (documents === null || ranking === null) return { state: "unavailable" };
    return { state: "available", documents, ranking };
  } catch {
    return { state: "unavailable" };
  }
}
