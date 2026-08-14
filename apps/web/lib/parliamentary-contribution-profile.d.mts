export type ParliamentaryContributionSphere = "federal" | "state";

export type ParliamentaryContributionRow = Readonly<{
  sphere: ParliamentaryContributionSphere;
  legislatureNumber: number;
  legislatureLabel: string;
  beginsOn: string;
  endsOn: string;
  fullFiscalYearFrom: number;
  fullFiscalYearTo: number;
  officialSourceUrl: string;
  officialSourceNote: string;
  excludedTransitionYears: readonly number[];
  rankingAmountStage: "destination" | "authorized";
  authorKey: string;
  authorName: string;
  representativeSourceKind: ParliamentaryContributionSphere | null;
  representativeExternalId: string | null;
  representativeProfileUrl: string | null;
  associationStatus: "approved_official_crosswalk" | "not_linked";
  totalAmendmentCount: number;
  totalRankingAmount: string;
  totalCommittedAmount: string | null;
  totalLiquidatedAmount: string | null;
  totalPaidAmount: string | null;
  rowPosition: number;
  contributionKey: string;
  fiscalYear: number;
  amendmentNumber: string | null;
  beneficiaryName: string | null;
  objectDescription: string | null;
  rankingAmount: string;
  committedAmount: string | null;
  liquidatedAmount: string | null;
  paidAmount: string | null;
  executionStatus: string;
  primarySourceUrl: string;
  primaryArtifactSha256: string;
  secondarySourceUrl: string | null;
  secondaryArtifactSha256: string | null;
  evidenceExcerpt: string | null;
  pageNumber: number | null;
  methodologyVersion: "parliamentary-legislature-contributions/1.0.0";
}>;

export type ParliamentaryContributionProfile = Readonly<{
  sphere: ParliamentaryContributionSphere;
  legislatureNumber: number;
  legislatureLabel: string;
  beginsOn: string;
  endsOn: string;
  fullFiscalYearFrom: number;
  fullFiscalYearTo: number;
  officialSourceUrl: string;
  officialSourceNote: string;
  excludedTransitionYears: readonly number[];
  rankingAmountStage: "destination" | "authorized";
  authorKey: string;
  authorName: string;
  representativeSourceKind: ParliamentaryContributionSphere | null;
  representativeExternalId: string | null;
  representativeProfileUrl: string | null;
  associationStatus: "approved_official_crosswalk" | "not_linked";
  totalAmendmentCount: number;
  totalRankingAmount: string;
  totalCommittedAmount: string | null;
  totalLiquidatedAmount: string | null;
  totalPaidAmount: string | null;
  contributions: readonly ParliamentaryContributionRow[];
  methodologyVersion: "parliamentary-legislature-contributions/1.0.0";
}>;

export function parseParliamentaryContributionProfileRows(
  rows: unknown,
): ParliamentaryContributionProfile | null;
