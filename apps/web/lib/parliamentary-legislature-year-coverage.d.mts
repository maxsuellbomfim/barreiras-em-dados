import type { ParliamentaryLegislatureSphere } from
  "./parliamentary-legislature-rankings.mjs";

export type ParliamentaryLegislatureYearCoverageRow = Readonly<{
  sphere: ParliamentaryLegislatureSphere;
  legislatureNumber: number;
  fiscalYear: number;
  observationStatus:
    | "observed"
    | "not_observed"
    | "source_empty"
    | "collection_incomplete"
    | "source_blocked"
    | "collected_no_record"
    | "not_collected";
  contributionCount: number;
  authorCount: number;
  primaryEvidenceCount: number;
  methodologyVersion:
    | "parliamentary-legislature-year-coverage/1.0.0"
    | "parliamentary-legislature-year-coverage/1.1.0";
}>;

export function parseParliamentaryLegislatureYearCoverageRows(
  rows: unknown,
): ParliamentaryLegislatureYearCoverageRow[] | null;

export function describeParliamentaryYearCoverageStatus(
  status: ParliamentaryLegislatureYearCoverageRow["observationStatus"],
): string;
