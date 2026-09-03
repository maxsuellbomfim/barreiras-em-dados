export type StateLoaExecutionGroup = Readonly<{
  fiscalYear: number;
  authorExternalCode: string;
  authorKey: string;
  authorName: string;
  agencyCode: string;
  budgetUnitCode: string;
  actionCode: string;
  amendmentCount: number;
  amendmentNumbers: readonly string[];
  authorizedTotal: string;
  initialBudgetAmount: string;
  currentBudgetAmount: string;
  committedAmount: string;
  liquidatedAmount: string;
  paidAmount: string;
  executionCode: string;
  executionSourceUrl: string;
  executionSourceArtifactSha256: string;
  executionEvidenceSha256: string;
  executionSourceCollectedAt: string;
  methodologyVersion: "bahia-state-loa-execution-group/1.0.0";
}>;

export function parseStateLoaExecutionGroups(
  rows: unknown,
): StateLoaExecutionGroup[] | null;
