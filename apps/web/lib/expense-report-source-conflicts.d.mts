export type PublicExpenseReportSourceConflict = Readonly<{
  expenseReportId: string;
  fiscalYear: number;
  periodStart: string;
  periodEnd: string;
  fieldName: string;
  fieldLabel: string;
  declaredAmount: string;
  calculatedAmount: string;
  differenceAmount: string;
  documentSourceUrl: string;
  documentArtifactSha256: string;
  methodologyVersion: "public-expense-source-conflicts/1.0.0";
}>;

export type ExpenseReportSourceConflictsResult =
  | Readonly<{ state: "available"; conflicts: readonly PublicExpenseReportSourceConflict[] }>
  | Readonly<{ state: "unavailable" }>;

export function parseExpenseReportSourceConflicts(
  payload: unknown,
): ExpenseReportSourceConflictsResult;

export function getPublicExpenseReportSourceConflicts(
  fiscalYear: number,
): Promise<ExpenseReportSourceConflictsResult>;
