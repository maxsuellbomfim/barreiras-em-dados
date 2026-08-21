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
  methodologyVersion: "cgu-federal-amendment-documents/1.0.0";
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
  methodologyVersion: "cgu-federal-amendment-document-ranking/1.0.0";
}>;

export function parseCguFederalAmendmentDocumentRows(
  rows: unknown,
): readonly CguFederalAmendmentDocument[] | null;

export function parseCguFederalAmendmentDocumentRankingRows(
  rows: unknown,
): readonly CguFederalAmendmentDocumentRanking[] | null;
