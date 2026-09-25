export type CommitmentPayment = Readonly<{
  commitmentKey: string;
  paymentId: string;
  paymentDateText: string;
  amountText: string;
  gridArtifactSha256: string;
  gridMonth: string;
  processNumber: string | null;
  contractText: string | null;
}>;

export function parseCommitmentPaymentRows(
  rows: unknown,
): readonly CommitmentPayment[] | null;

export function groupPaymentsByCommitment(
  payments: readonly CommitmentPayment[],
): ReadonlyMap<string, readonly CommitmentPayment[]>;
