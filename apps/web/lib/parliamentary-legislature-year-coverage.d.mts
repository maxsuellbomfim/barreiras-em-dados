import type { ParliamentaryLegislatureSphere } from
  "./parliamentary-legislature-rankings.mjs";

export type ParliamentaryLegislatureYearCoverageRow = Readonly<{
  sphere: ParliamentaryLegislatureSphere;
  legislatureNumber: number;
  fiscalYear: number;
  observationStatus: "observed" | "not_observed";
  contributionCount: number;
  authorCount: number;
  primaryEvidenceCount: number;
  methodologyVersion: "parliamentary-legislature-year-coverage/1.0.0";
}>;

export function parseParliamentaryLegislatureYearCoverageRows(
  rows: unknown,
): ParliamentaryLegislatureYearCoverageRow[] | null;
