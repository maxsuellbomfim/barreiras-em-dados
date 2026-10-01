export type PaymentGroupKey =
  | "compras_servicos"
  | "pessoal"
  | "tributos_encargos"
  | "divida"
  | "transferencias"
  | "auxilios"
  | "judicial"
  | "restituicoes"
  | "nao_identificado";

export type PaymentRecipient = Readonly<{
  /** null: agregado de pessoas físicas e credores sem forma jurídica no nome. */
  creditorName: string | null;
  creditors: number;
  payments: number;
  paidAmount: string;
  firstPaymentDate: string;
  lastPaymentDate: string;
  mainNature: string | null;
  gridArtifactSha256: string;
}>;

export type PaymentGroup = Readonly<{
  key: PaymentGroupKey;
  label: string;
  payments: number;
  creditors: number;
  paidAmount: string;
  recipients: readonly PaymentRecipient[];
  others: PaymentRecipient | null;
}>;

export type PaymentBody = Readonly<{
  publicBody: string;
  payments: number;
  paidAmount: string;
}>;

export type PaymentRecipientSummary = Readonly<{
  payments: number;
  paidAmount: string;
  priorCommitmentAmount: string;
  uncollectedCommitmentAmount: string;
  bodies: readonly PaymentBody[];
  gridMonths: number;
  unreadableRows: number;
  excludedRows: number;
  sourcePageUrl: string;
  refreshedAt: string;
}>;

export type PaymentRecipientResult =
  | Readonly<{
      state: "available";
      summary: PaymentRecipientSummary | null;
      groups: readonly PaymentGroup[];
    }>
  | Readonly<{ state: "unavailable" }>;

export const FIRST_PAYMENT_YEAR: number;

export const PAYMENT_GROUPS: Readonly<Record<PaymentGroupKey, string>>;

export function parsePaymentRecipientRows(
  rows: unknown,
): { summary: PaymentRecipientSummary | null; groups: PaymentGroup[] } | null;

export function paymentYear(value: string | undefined, currentYear: number): number;

export function getPublicPaymentRecipients(year: number): Promise<PaymentRecipientResult>;
