export type SiconfiAnnualMetricKey =
  | "gross_revenue_realized"
  | "fundeb_deductions"
  | "expense_committed"
  | "expense_liquidated"
  | "expense_paid"
  | "nonprocessed_payables_registered"
  | "processed_payables_registered";

export type ParsedSiconfiAnnualMetric = Readonly<{
  totalId: string;
  fiscalYear: number;
  metricKey: SiconfiAnnualMetricKey;
  amount: string;
  currency: "BRL";
  officialAnnex: string;
  officialLabel: string;
  officialColumnLabel: string;
  officialAccountCode: string;
  officialAccountLabel: string;
  sourceUrl: string;
  sourceArtifactSha256: string;
  sourceRetrievedAt: string;
  methodologyVersion: "siconfi-annual-totals/1.0.0";
}>;

export type ParsedSiconfiAnnualYear = Readonly<{
  fiscalYear: number;
  metrics: readonly ParsedSiconfiAnnualMetric[];
}>;

export const SICONFI_ANNUAL_METRICS: readonly SiconfiAnnualMetricKey[];
export function parseSiconfiAnnualRows(
  payload: unknown,
): ParsedSiconfiAnnualYear[] | null;
