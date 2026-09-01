import type {
  PublicObligationCoverageResult,
  PublicObligationCoverageRow,
} from "./public-obligations.mjs";

export type ObligationCoverageMatrixStatus =
  | PublicObligationCoverageRow["coverageStatus"]
  | "unclassified"
  | "not_due";

export type ObligationCoverageMatrix = Readonly<{
  latestPeriod: string | null;
  years: readonly Readonly<{
    year: number;
    months: readonly Readonly<{
      month: number;
      status: ObligationCoverageMatrixStatus;
      row: PublicObligationCoverageRow | null;
    }>[];
  }>[];
}>;

export function obligationCoverageStatusLabel(
  status: ObligationCoverageMatrixStatus,
): string;
export function buildObligationCoverageMatrix(
  rows: readonly PublicObligationCoverageRow[],
  startYear?: number,
): ObligationCoverageMatrix | null;
export function parseObligationCoverageApiPayload(
  payload: unknown,
): PublicObligationCoverageResult | null;
