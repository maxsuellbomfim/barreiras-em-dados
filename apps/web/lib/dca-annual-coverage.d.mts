export type DcaAnnualCoverageStatus = "published" | "not_found" | "in_progress";

export type DcaAnnualCoverageEntry = Readonly<{
  fiscalYear: number;
  status: DcaAnnualCoverageStatus;
  sourceUrl: string | null;
}>;

export function buildDcaAnnualCoverage(
  years: readonly Readonly<{
    fiscalYear: number;
    metrics: readonly Readonly<{ sourceUrl: string }>[];
  }>[],
  options?: Readonly<{ yearFrom?: number; currentYear?: number }>,
): readonly DcaAnnualCoverageEntry[] | null;

export function dcaAnnualCoverageStatusLabel(
  status: DcaAnnualCoverageStatus,
): string;
