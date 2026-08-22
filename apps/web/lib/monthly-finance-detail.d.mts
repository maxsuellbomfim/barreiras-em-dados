export type MonthlyFinanceStatus = "operational" | "needs_data" | "needs_review";

export type MonthlyFinanceRevenueDocument = Readonly<{
  documentUrl: string;
  artifactSha256: string;
  sourceUrl: string;
  sourceArtifactSha256: string;
  lineCount: number;
  reportAmount: string;
}>;

export type MonthlyFinanceExpenseDocument = Readonly<{
  documentUrl: string;
  artifactSha256: string;
  sourceUrl: string;
  sourceArtifactSha256: string;
  committedAmount: string;
  liquidatedAmount: string;
  paidAmount: string;
}>;

export type PublicMonthlyFinanceDetail = Readonly<{
  closureId: string;
  fiscalYear: number;
  periodStart: string;
  periodEnd: string;
  publicBodyName: string;
  revenueReportAmount: string | null;
  revenueReportCount: number;
  revenueLineCount: number;
  expensePaidAmount: string | null;
  expenseCommittedAmount: string | null;
  expenseLiquidatedAmount: string | null;
  expenseReportCount: number;
  operationalDifferenceAmount: string | null;
  closureStatus: MonthlyFinanceStatus;
  coverageNote: string;
  calculationMethodology: "monthly-finance-closure/1.1.0";
  revenueDocuments: readonly MonthlyFinanceRevenueDocument[];
  expenseDocuments: readonly MonthlyFinanceExpenseDocument[];
  evidenceMethodology: "public-monthly-finance-detail/1.0.0";
}>;

export type MonthlyFinanceStatusCopy = Readonly<{
  label: string;
  heading: string;
  explanation: string;
  canShowDifference: boolean;
}>;

export function periodStartFromSlug(slug: string): string | null;
export function monthlyFinanceHref(periodStart: string): string;
export function monthlyFinanceStatusCopy(
  detail: PublicMonthlyFinanceDetail | null,
): MonthlyFinanceStatusCopy;
export function selectMonthlyExpenseReportId(
  reports: readonly Readonly<{
    expenseReportId: string;
    fiscalYear: number;
    periodStart: string;
    periodEnd: string;
  }>[],
  detail: Readonly<{
    fiscalYear: number;
    periodStart: string;
    periodEnd: string;
    expenseReportCount: number;
  }>,
): string | null;
export function parseMonthlyFinanceDetail(
  row: Record<string, unknown>,
): PublicMonthlyFinanceDetail | null;
