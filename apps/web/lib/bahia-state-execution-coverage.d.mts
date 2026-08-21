export type BahiaStateExecutionCoverage = Readonly<{
  fiscalYear: number;
  sourceAggregateCount: number;
  sourceAuthorCount: number;
  territorialKeyStatus: "territorial_key_unavailable_in_source";
  sourceSnapshotStatus: "source_snapshot_observed";
  sourceUrl: string;
  sourceArtifactSha256: string;
  sourceCollectedAt: string;
  methodologyVersion: "bahia-state-execution-source-coverage/1.0.0";
}>;

export function parseBahiaStateExecutionCoverageRows(
  rows: unknown,
): BahiaStateExecutionCoverage[] | null;
