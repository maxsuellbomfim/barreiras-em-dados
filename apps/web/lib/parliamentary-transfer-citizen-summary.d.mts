export type CurrentTransferSummaryInput = Readonly<{
  fiscalYear: number;
  destinationAmount: string;
  committedAmount: string | null;
  paidAmount: string | null;
}>;

export type CurrentTransferCitizenSummary = Readonly<{
  fiscalYear: number;
  transferCount: number;
  destinationAmount: string;
  committedAmount: string | null;
  paidAmount: string | null;
  commitmentFoundCount: number;
  paymentFoundCount: number;
  paymentNotFoundCount: number;
  destinationWithoutPaymentAmount: string;
}>;

export function buildCurrentTransferCitizenSummary(
  transfers: readonly CurrentTransferSummaryInput[],
): CurrentTransferCitizenSummary | null;
