export type CommitmentLiquidation = Readonly<{
  commitmentKey: string;
  liquidationDateText: string;
  amountText: string;
  gridArtifactSha256: string;
  gridMonth: string;
}>;

export function parseCommitmentLiquidationRows(
  rows: unknown,
): readonly CommitmentLiquidation[] | null;

export function groupLiquidationsByCommitment(
  liquidations: readonly CommitmentLiquidation[],
): ReadonlyMap<string, readonly CommitmentLiquidation[]>;
