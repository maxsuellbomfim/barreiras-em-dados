export type FiscalReportCoverageEntry = Readonly<{
  resource: "rreo" | "rgf";
  fiscalYear: number;
  referenceMonth: number;
  documentUrl: string;
  documentPreserved: boolean;
  artifactSha256: string | null;
  collectedAt: string;
}>;

export type FiscalReportCoverageResult =
  | Readonly<{ state: "available"; entries: readonly FiscalReportCoverageEntry[] }>
  | Readonly<{ state: "unavailable" }>;

export type FiscalReportCoverageStatus =
  | "preserved"
  | "catalogued"
  | "not_found"
  | "not_due";

export function toFiscalCoverageEntry(value: unknown): FiscalReportCoverageEntry | null;
export function fiscalReportCoverageStatusLabel(status: FiscalReportCoverageStatus): string;
export function buildFiscalReportCoverageMatrix(
  entries: readonly FiscalReportCoverageEntry[],
  options?: Readonly<{ startYear?: number; today?: string }>,
): Readonly<{
  columns: readonly Readonly<{
    resource: "rreo" | "rgf";
    referenceMonth: number;
    shortLabel: string;
  }>[];
  years: readonly Readonly<{
    year: number;
    periods: readonly Readonly<{
      resource: "rreo" | "rgf";
      referenceMonth: number;
      shortLabel: string;
      status: FiscalReportCoverageStatus;
      entry: FiscalReportCoverageEntry | null;
      evidenceCount: number;
    }>[];
  }>[];
}> | null;
export function parseFiscalReportCoverageApiPayload(value: unknown): FiscalReportCoverageResult | null;
