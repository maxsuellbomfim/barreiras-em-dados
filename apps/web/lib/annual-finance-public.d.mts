import type { AnnualFinanceSummary } from "./annual-finance-summary.mjs";

export function getPublicAnnualFinanceSummary(): Promise<
  | Readonly<{ state: "available"; summaries: readonly AnnualFinanceSummary[] }>
  | Readonly<{ state: "unavailable" }>
>;
