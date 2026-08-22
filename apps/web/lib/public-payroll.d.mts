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
  parserVersion:
    | "payroll-report-aggregate/1.0.0"
    | "payroll-monthly-total/1.0.0";
  documentCount: number;
  sourceDocuments: readonly Readonly<{
    payrollCycle: "regular" | "thirteenth_advance" | "thirteenth_final";
    sourceUrl: string;
    artifactSha256: string;
    sourceRetrievedAt: string;
    parserVersion:
      | "payroll-report-aggregate/1.0.0"
      | "payroll-report-aggregate/1.1.0"
      | "payroll-report-aggregate/1.2.0"
      | "payroll-report-aggregate/1.3.0"
      | "payroll-report-aggregate/1.4.0";
  }>[];
}>;

export type PublicPayrollResult =
  | Readonly<{ state: "available"; months: readonly PublicPayrollMonth[] }>
  | Readonly<{ state: "unavailable" }>;

export type PublicPayrollCoverageRow = Readonly<{
  referenceMonth: string;
  coverageStatus:
    | "published"
    | "document_not_found"
    | "source_conflict"
    | "processing_pending";
  coverageNote: string;
  catalogDocumentCount: number;
  preservedDocumentCount: number;
  sourceUrl: string;
  artifactSha256: string | null;
  catalogCheckedAt: string;
  methodologyVersion: "payroll-coverage/1.0.0";
}>;

export type PublicPayrollCoverageResult =
  | Readonly<{
      state: "available";
      rows: readonly PublicPayrollCoverageRow[];
    }>
  | Readonly<{ state: "unavailable" }>;

export function parsePublicPayrollRow(
  row: Record<string, unknown>,
): PublicPayrollMonth | null;

export function getPublicPayrollMonths(
  maxMonths?: number,
): Promise<PublicPayrollResult>;

export function parsePublicPayrollCoverageRow(
  row: Record<string, unknown>,
): PublicPayrollCoverageRow | null;

export function getPublicPayrollCoverage(
  maxMonths?: number,
): Promise<PublicPayrollCoverageResult>;
