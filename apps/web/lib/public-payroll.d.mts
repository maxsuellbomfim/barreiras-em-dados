export type PublicPayrollMonth = Readonly<{
  referenceMonth: string;
  publicBodyName: string;
  employeeCount: number;
  grossAmount: string;
  deductionAmount: string;
  netAmount: string;
  subtotalCount: number;
  sourceUrl: string;
  artifactSha256: string;
  sourceRetrievedAt: string;
  parserVersion: "payroll-report-aggregate/1.0.0";
}>;

export type PublicPayrollResult =
  | Readonly<{ state: "available"; months: readonly PublicPayrollMonth[] }>
  | Readonly<{ state: "unavailable" }>;

export function parsePublicPayrollRow(
  row: Record<string, unknown>,
): PublicPayrollMonth | null;

export function getPublicPayrollMonths(
  pageSize?: number,
): Promise<PublicPayrollResult>;
