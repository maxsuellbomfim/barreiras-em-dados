export type FinanceFamilyCoverageState =
  | "complete"
  | "partial"
  | "observed"
  | "unavailable";

export type FinanceFamilyCoverage = Readonly<{
  key:
    | "monthly-finance"
    | "obligations"
    | "payroll"
    | "fiscal-statements"
    | "annual-accounts";
  title: string;
  cadence: "Mensal" | "Bimestral e quadrimestral" | "Anual";
  href: string;
  observedPeriods: number;
  classifiedPeriods: number | null;
  gapPeriods: number | null;
  latestObservedPeriod: string | null;
  state: FinanceFamilyCoverageState;
}>;

type CoverageRow = Readonly<{
  coverageStatus: string;
  periodStart?: string;
  referenceMonth?: string;
  publicBodyName?: string;
}>;

export function buildFinanceFamilyCoverage(input: Readonly<{
  financeRows: readonly CoverageRow[];
  obligationRows: readonly CoverageRow[];
  payrollRows: readonly CoverageRow[];
  fiscalDocuments: readonly Readonly<{
    sourceResource: string;
    referenceDate: string | null;
    fiscalYear: number | null;
  }>[];
  siconfiYears: readonly Readonly<{ fiscalYear: number }>[];
}>): FinanceFamilyCoverage[];
