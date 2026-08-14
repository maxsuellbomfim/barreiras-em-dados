export type ParliamentaryLegislatureSphere = "federal" | "state";
export type ParliamentaryLegislatureRankingAmountStage =
  | "destination"
  | "authorized";

export type ParliamentaryLegislatureRankingRow = Readonly<{
  sphere: ParliamentaryLegislatureSphere;
  legislatureNumber: number;
  legislatureLabel: string;
  beginsOn: string;
  endsOn: string;
  fullFiscalYearFrom: number;
  fullFiscalYearTo: number;
  officialSourceUrl: string;
  officialSourceNote: string;
  excludedTransitionYears: readonly number[];
  rankingAmountStage: ParliamentaryLegislatureRankingAmountStage;
  rankPosition: number | null;
  authorKey: string | null;
  authorName: string | null;
  representativeSourceKind: "federal" | "state" | null;
  representativeExternalId: string | null;
  representativeProfileUrl: string | null;
  associationStatus: "approved_official_crosswalk" | "not_linked" | null;
  amendmentCount: number | null;
  rankingAmount: string | null;
  committedAmount: string | null;
  liquidatedAmount: string | null;
  paidAmount: string | null;
  firstYear: number | null;
  lastYear: number | null;
  methodologyVersion: "parliamentary-legislature-transfer-ranking/1.0.0";
}>;

export type ParliamentaryLegislatureRankingGroup = Readonly<{
  sphere: ParliamentaryLegislatureSphere;
  legislatureNumber: number;
  legislatureLabel: string;
  beginsOn: string;
  endsOn: string;
  fullFiscalYearFrom: number;
  fullFiscalYearTo: number;
  officialSourceUrl: string;
  officialSourceNote: string;
  excludedTransitionYears: readonly number[];
  rankingAmountStage: ParliamentaryLegislatureRankingAmountStage;
  rankings: readonly ParliamentaryLegislatureRankingRow[];
}>;

export function parseParliamentaryLegislatureRankingRows(
  rows: unknown,
): ParliamentaryLegislatureRankingRow[] | null;
export function groupParliamentaryLegislatureRankings(
  rows: readonly ParliamentaryLegislatureRankingRow[],
): ParliamentaryLegislatureRankingGroup[];
