export type StateAmendmentLoaStatus =
  | "observed"
  | "empty"
  | "partial"
  | "failed"
  | "blocked"
  | "unclassified";

export type StateAmendmentExecutionStatus =
  | "observed"
  | "partial"
  | "blocked_missing_official_key"
  | "scope_not_indexed"
  | "loa_unavailable"
  | "unclassified";

export type StateAmendmentSourceCoverage = Readonly<{
  fiscalYear: number;
  loaStatus: StateAmendmentLoaStatus;
  amendmentCount: number | null;
  authorCount: number | null;
  authorizedAmount: string | null;
  executionStatus: StateAmendmentExecutionStatus;
  matchedCount: number | null;
  ambiguousCount: number | null;
  notFoundCount: number | null;
  unavailableScopeCount: number | null;
  committedAmount: string | null;
  liquidatedAmount: string | null;
  paidAmount: string | null;
  lastAttemptedAt: string | null;
  sourceUrl: string;
  methodologyVersion:
    | "state-amendment-source-coverage/1.0.0"
    | "state-amendment-source-coverage/1.1.0";
}>;

export function parseStateAmendmentSourceCoverageRows(
  rows: unknown,
): StateAmendmentSourceCoverage[] | null;
