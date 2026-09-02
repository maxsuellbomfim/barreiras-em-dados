export type ParliamentaryTransferQueryScope =
  | "current"
  | "historical"
  | "state"
  | "none";

export type ParliamentaryTransferQueryPlan = Readonly<{
  current: boolean;
  historical: boolean;
  state: boolean;
}>;

export function buildParliamentaryTransferQueryPlan(
  scope: unknown,
): ParliamentaryTransferQueryPlan;
