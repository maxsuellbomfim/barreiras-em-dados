export type CguFederalAmendmentAuthorKind =
  | "person"
  | "commission"
  | "bench"
  | "collective"
  | "other";

export type CguFederalAmendmentLinkStatus =
  | "code_unavailable"
  | "not_found_in_transferegov"
  | "matched_transferegov_unique"
  | "conflict_non_unique_transferegov";

export type CguFederalAmendment = Readonly<{
  fiscalYear: number;
  amendmentCode: string;
  hasOfficialCode: boolean;
  amendmentNumber: string;
  amendmentType: string;
  authorKind: CguFederalAmendmentAuthorKind;
  authorCode: string;
  authorKey: string;
  authorName: string;
  authorIdentified: boolean;
  locality: string;
  functionName: string;
  programName: string;
  actionName: string;
  budgetPlanName: string | null;
  committedAmount: string;
  liquidatedAmount: string;
  paidAmount: string;
  outstandingRegisteredAmount: string;
  outstandingCancelledAmount: string;
  outstandingPaidAmount: string;
  effectivePaidAmount: string;
  transferegovLinkStatus: CguFederalAmendmentLinkStatus;
  transferegovReconciliationKey: string | null;
  sourceRowNumber: number;
  sourceUrl: string;
  artifactSha256: string;
  collectedAt: string;
  methodologyVersion: "cgu-federal-amendment-executions/1.0.0";
}>;

export type CguFederalAmendmentRanking = Readonly<{
  rankPosition: number;
  authorKind: Exclude<CguFederalAmendmentAuthorKind, "other">;
  authorKey: string;
  authorName: string;
  authorCode: string;
  amendmentCount: number;
  committedAmount: string;
  effectivePaidAmount: string;
  firstYear: number;
  lastYear: number;
  rankingAmountStage: "committed";
  methodologyVersion: "cgu-federal-amendment-ranking/1.0.0";
}>;

export function parseCguFederalAmendmentRows(
  rows: unknown,
): readonly CguFederalAmendment[] | null;

export function parseCguFederalAmendmentRankingRows(
  rows: unknown,
  scope: "person" | "collective",
): readonly CguFederalAmendmentRanking[] | null;
