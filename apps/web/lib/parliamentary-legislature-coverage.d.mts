import type {
  ParliamentaryLegislatureRankingAmountStage,
  ParliamentaryLegislatureSphere,
} from "./parliamentary-legislature-rankings.mjs";

export type ParliamentaryLegislatureCoverageRow = Readonly<{
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
  contributionCount: number;
  authorCount: number;
  linkedAuthorCount: number;
  unlinkedAuthorCount: number;
  withObjectCount: number;
  objectFieldStatus: "published_by_source";
  withBeneficiaryCount: number | null;
  beneficiaryFieldStatus: "published_by_source" | "not_published_in_source";
  withCommittedCount: number;
  withLiquidatedCount: number | null;
  liquidatedFieldStatus: "published_by_source" | "not_published_in_source";
  withPaidCount: number;
  executionConfirmedCount: number;
  executionUnresolvedCount: number;
  primaryEvidenceCount: number;
  methodologyVersion: "parliamentary-legislature-coverage/1.0.0";
}>;

export function parseParliamentaryLegislatureCoverageRows(
  rows: unknown,
): ParliamentaryLegislatureCoverageRow[] | null;
