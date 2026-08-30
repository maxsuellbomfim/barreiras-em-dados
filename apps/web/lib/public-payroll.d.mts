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

export type PublicPayrollYearSummary = Readonly<{
  year: number;
  publishedMonthCount: number;
  expectedMonthCount: number;
  isComplete: boolean;
  grossAmount: string;
  deductionAmount: string;
  netAmount: string;
}>;

export function summarizePublicPayrollYears(
  months: readonly PublicPayrollMonth[],
): readonly PublicPayrollYearSummary[];

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

export type PublicNonpayrollWorkforceCoverageRow = Readonly<{
  referenceMonth: string;
  workforceCategory: "interns" | "outsourced_workers";
  categoryLabel: "Estagiários" | "Terceirizados";
  coverageStatus: "document_preserved" | "catalogued" | "not_listed";
  coverageNote: string;
  catalogDocumentCount: number;
  preservedDocumentCount: number;
  sourceUrl: string;
  artifactSha256: string | null;
  catalogCheckedAt: string;
  methodologyVersion: "nonpayroll-workforce-coverage/1.0.1";
}>;

export type PublicNonpayrollWorkforceCoverageResult =
  | Readonly<{
      state: "available";
      rows: readonly PublicNonpayrollWorkforceCoverageRow[];
    }>
  | Readonly<{ state: "unavailable" }>;

export type PublicPayrollRegimeRow = Readonly<{
  referenceMonth: string;
  regimeCode:
    | "statutory"
    | "commissioned"
    | "selection_process"
    | "ceded"
    | "political_agent"
    | "guardianship_council"
    | "pensioner"
    | "temporary_worker";
  regimeLabel: string;
  employeeCount: number;
  grossAmount: string;
  deductionAmount: string;
  netAmount: string;
  sourceDocumentCount: number;
  methodologyVersion: "payroll-regime-monthly/1.0.0";
}>;

export type PublicPayrollRegimeResult =
  | Readonly<{
      state: "available";
      rows: readonly PublicPayrollRegimeRow[];
    }>
  | Readonly<{ state: "unavailable" }>;

export type PublicPayrollCompensationRow = Readonly<{
  referenceMonth: string;
  bandCode:
    | "up_to_1500"
    | "from_1500_01_to_3000"
    | "from_3000_01_to_5000"
    | "from_5000_01_to_10000"
    | "from_10000_01_to_20000"
    | "above_20000";
  bandLabel: string;
  employeeCount: number;
  grossAmount: string;
  averageGrossAmount: string;
  maximumGrossAmount: string;
  methodologyVersion: "payroll-compensation-monthly/1.0.0";
}>;

export type PublicPayrollCompensationResult =
  | Readonly<{
      state: "available";
      rows: readonly PublicPayrollCompensationRow[];
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

export function parsePublicNonpayrollWorkforceCoverageRow(
  row: Record<string, unknown>,
): PublicNonpayrollWorkforceCoverageRow | null;

export function getPublicNonpayrollWorkforceCoverage(
  maxMonths?: number,
): Promise<PublicNonpayrollWorkforceCoverageResult>;

export function parsePublicPayrollRegimeRow(
  row: Record<string, unknown>,
): PublicPayrollRegimeRow | null;

export function payrollRegimeBreakdownMatchesMonth(
  rows: readonly PublicPayrollRegimeRow[],
  month: PublicPayrollMonth | null,
): boolean;

export function getPublicPayrollRegimeBreakdown(
  referenceMonth: string,
): Promise<PublicPayrollRegimeResult>;

export function parsePublicPayrollCompensationRow(
  row: Record<string, unknown>,
): PublicPayrollCompensationRow | null;

export function payrollCompensationMatchesMonth(
  rows: readonly PublicPayrollCompensationRow[],
  month: PublicPayrollMonth | null,
): boolean;

export function getPublicPayrollCompensationDistribution(
  referenceMonth: string,
): Promise<PublicPayrollCompensationResult>;
