import type {
  PublicPayrollCoverageResult,
  PublicPayrollCoverageRow,
} from "./public-payroll.mjs";

export type PayrollCoverageMatrixStatus =
  | PublicPayrollCoverageRow["coverageStatus"]
  | "unclassified"
  | "not_due";

export type PayrollCoverageMatrix = Readonly<{
  latestPeriod: string | null;
  years: readonly Readonly<{
    year: number;
    months: readonly Readonly<{
      month: number;
      status: PayrollCoverageMatrixStatus;
      row: PublicPayrollCoverageRow | null;
    }>[];
  }>[];
}>;

export function payrollCoverageStatusLabel(status: PayrollCoverageMatrixStatus): string;
export function buildPayrollCoverageMatrix(
  rows: readonly PublicPayrollCoverageRow[],
  startYear?: number,
): PayrollCoverageMatrix | null;
export function parsePayrollCoverageApiPayload(payload: unknown): PublicPayrollCoverageResult | null;
