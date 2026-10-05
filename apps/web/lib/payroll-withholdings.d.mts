export type PayrollWithholdingCreditor = Readonly<{
  /** null = pessoas físicas e pensão alimentícia, somadas sem nome. */
  creditorName: string | null;
  commitments: number;
  /** Soma líquida, estornos incluídos. */
  amount: string;
  /** Soma dos estornos (zero ou negativa). */
  reversalAmount: string;
  firstCommitmentDate: string;
  lastCommitmentDate: string;
  latestCommitmentKey: string;
  gridArtifactSha256: string;
}>;

export type PayrollWithholdingSummary = Readonly<{
  commitments: number;
  amount: string;
  reversalAmount: string;
  gridMonths: number;
  /** Pagamentos publicados que apontam, pela chave oficial, para estes empenhos. */
  linkedPayments: number;
  months: readonly Readonly<{ month: string; commitments: number; amount: string }>[];
  sourcePageUrl: string;
}>;

export type PayrollWithholdingResult =
  | Readonly<{
      state: "available";
      summary: PayrollWithholdingSummary | null;
      creditors: readonly PayrollWithholdingCreditor[];
    }>
  | Readonly<{ state: "unavailable" }>;

export const FIRST_WITHHOLDING_YEAR: number;

export function parsePayrollWithholdingRows(
  rows: unknown,
): { summary: PayrollWithholdingSummary | null; creditors: PayrollWithholdingCreditor[] } | null;

export function withholdingYear(value: string | undefined, currentYear: number): number;

export function getPublicPayrollWithholdings(year: number): Promise<PayrollWithholdingResult>;
