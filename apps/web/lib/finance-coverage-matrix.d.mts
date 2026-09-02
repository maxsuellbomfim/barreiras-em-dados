import type {
  PublicFinanceCoverageResult,
  PublicFinanceCoverageRow,
} from "./finance-coverage";

export type FinanceCoverageMatrixStatus =
  | PublicFinanceCoverageRow["coverageStatus"]
  | "unclassified"
  | "not_due";

export type FinanceCoverageMatrix = Readonly<{
  latestPeriod: string | null;
  bodies: readonly Readonly<{
    publicBodyName: string;
    years: readonly Readonly<{
      year: number;
      months: readonly Readonly<{
        month: number;
        status: FinanceCoverageMatrixStatus;
        row: PublicFinanceCoverageRow | null;
      }>[];
    }>[];
  }>[];
}>;

export function financeCoverageStatusLabel(
  status: FinanceCoverageMatrixStatus,
): string;

export function buildFinanceCoverageMatrix(
  rows: readonly PublicFinanceCoverageRow[],
  startYear?: number,
  currentPeriod?: string | null,
): FinanceCoverageMatrix | null;

export function parseFinanceCoverageApiPayload(
  payload: unknown,
): PublicFinanceCoverageResult | null;
