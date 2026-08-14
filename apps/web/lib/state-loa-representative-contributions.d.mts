export type StateLoaRepresentativeContribution = Readonly<{
  representativeSourceKind: "federal" | "state";
  representativeExternalId: string;
  representativeProfileUrl: string;
  authorKey: string;
  authorName: string;
  fiscalYear: number;
  amendmentCount: number;
  authorizedAmount: string;
  matchedAmendmentCount: number;
  matchedAuthorizedAmount: string | null;
  committedAmount: string | null;
  liquidatedAmount: string | null;
  paidAmount: string | null;
  blockedAmendmentCount: number;
  methodologyVersion: "bahia-state-loa-representative-contributions/1.0.0";
}>;

export function parseStateLoaRepresentativeContributions(
  rows: unknown,
): StateLoaRepresentativeContribution[] | null;

export function stateLoaContributionsForRepresentative(
  rows: readonly StateLoaRepresentativeContribution[],
  sourceKind: "federal" | "state",
  representativeExternalId: string,
): StateLoaRepresentativeContribution[];
