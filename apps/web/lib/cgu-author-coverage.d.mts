import type { CguFederalAmendment } from "./cgu-federal-amendments.mjs";
import type { FederalTransferSourceCoverage } from
  "./federal-transfer-source-coverage.mjs";

export type CguAuthorCoverageSummary = Readonly<{
  authorKey: string;
  authorName: string;
  recordCount: number;
  foundYears: readonly number[];
  committedAmount: string;
  effectivePaidAmount: string;
  observedWithoutAuthorYears: readonly number[];
  emptyMunicipalYears: readonly number[];
  unresolvedYears: readonly number[];
}>;

export function buildCguAuthorCoverageSummary(
  amendments: readonly CguFederalAmendment[],
  coverage: readonly FederalTransferSourceCoverage[],
  authorKey: string | null,
  minimumCoverageYear?: number,
): CguAuthorCoverageSummary | null;
