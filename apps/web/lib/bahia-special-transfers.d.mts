export type BahiaSpecialTransferPayment = Readonly<{
  fiscalYear: number;
  amendmentNumber: string;
  amendmentYear: number;
  officialAmendmentCode: string;
  sourceAuthorName: string;
  authorKey: string | null;
  officialAuthorName: string;
  representativeSourceKind: "federal" | "state" | null;
  representativeExternalId: string | null;
  representativeProfileUrl: string | null;
  associationStatus: "approved_official_author_code_crosswalk" | "not_linked";
  agencyName: string;
  budgetUnitName: string;
  actionName: string;
  paymentId: string;
  paymentNumber: string;
  paymentDate: string;
  paymentAmount: string;
  paymentStatus: string;
  objectText: string;
  paymentUrl: string;
  financialStage: "paid_by_bahia_state";
  territorialScope: "payment_object_literal_barreiras";
  federalLinkStatus:
    | "matched_cgu_unique"
    | "not_found_in_cgu"
    | "conflict_non_unique_cgu";
  aggregationPolicy: "single_source_no_cross_source_sum";
  evidenceText: string;
  evidenceSha256: string;
  sourceUrl: string;
  sourceArtifactSha256: string;
  sourceCollectedAt: string;
  methodologyVersion: "bahia-special-transfer-payments/1.0.0";
}>;

export type BahiaSpecialTransferRanking = Readonly<{
  rankPosition: number;
  authorKey: string;
  officialAuthorName: string;
  representativeSourceKind: "federal" | "state";
  representativeExternalId: string;
  representativeProfileUrl: string;
  paymentCount: number;
  amendmentCount: number;
  paidAmount: string;
  firstPaymentDate: string;
  lastPaymentDate: string;
  rankingAmountStage: "paid_by_bahia_state";
  territorialScope: "payment_object_literal_barreiras";
  aggregationPolicy: "single_source_no_cross_source_sum";
  methodologyVersion: "bahia-special-transfer-ranking/1.0.0";
}>;

export function parseBahiaSpecialTransferPayments(
  rows: unknown,
): BahiaSpecialTransferPayment[] | null;

export function parseBahiaSpecialTransferRanking(
  rows: unknown,
): BahiaSpecialTransferRanking[] | null;
