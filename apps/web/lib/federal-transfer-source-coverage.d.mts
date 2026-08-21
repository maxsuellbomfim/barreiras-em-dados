export type FederalTransferSourceKey =
  | "cgu_execution"
  | "transferegov_historical"
  | "transferegov_current";

export type FederalTransferSourceCoverageStatus =
  | "observed"
  | "empty"
  | "partial"
  | "failed"
  | "blocked"
  | "unclassified";

export type FederalTransferSourceCoverage = Readonly<{
  sourceKey: FederalTransferSourceKey;
  fiscalYear: number;
  coverageStatus: FederalTransferSourceCoverageStatus;
  recordCount: number | null;
  lastAttemptedAt: string | null;
  sourceUrl: string;
  methodologyVersion: "federal-transfer-source-coverage/1.0.0";
}>;

export type FederalTransferSourceCoverageGroup = Readonly<{
  fiscalYear: number;
  sources: readonly FederalTransferSourceCoverage[];
}>;

export function parseFederalTransferSourceCoverageRows(
  rows: unknown,
): FederalTransferSourceCoverage[] | null;

export function groupFederalTransferSourceCoverage(
  rows: readonly FederalTransferSourceCoverage[],
): FederalTransferSourceCoverageGroup[];
