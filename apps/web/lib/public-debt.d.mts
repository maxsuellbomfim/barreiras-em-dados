export type DebtCompositionLine = Readonly<{ code: string; account: string; value: string }>;

export type DebtStatement = Readonly<{
  fiscalYear: number;
  period: 1 | 2 | 3;
  periodEnd: string;
  consolidatedDebt: string | null;
  deductions: string | null;
  netConsolidatedDebt: string | null;
  adjustedNetCurrentRevenue: string | null;
  netDebtRevenuePercent: string | null;
  senateLimit: string | null;
  alertLimit: string | null;
  composition: readonly DebtCompositionLine[];
  artifactSha256: string;
  retrievedAt: string;
  sourceUrl: string;
}>;

export type DebtStatementResult =
  | Readonly<{ state: "available"; statements: readonly DebtStatement[] }>
  | Readonly<{ state: "unavailable" }>;

export function parseDebtStatementRows(rows: unknown): DebtStatement[] | null;

export function getPublicDebtStatements(): Promise<DebtStatementResult>;
