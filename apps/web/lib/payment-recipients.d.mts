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
  /** 1.3.0: liquidado no ano; null em versões anteriores. */
  liquidations: number | null;
  liquidatedAmount: string | null;
  /** null quando o credor só tem liquidação no ano. */
  firstPaymentDate: string | null;
  lastPaymentDate: string | null;
  mainNature: string | null;
  gridArtifactSha256: string;
  /** Cadastro da Receita, só quando o empenho pago tem contrato confirmado. */
  registry: PaymentRegistry | null;
}>;

export type PaymentRegistry = Readonly<{
  cnpj: string;
  legalName: string;
  legalNature: string;
  month: string;
}>;

export type PaymentGroup = Readonly<{
  key: PaymentGroupKey;
  label: string;
  payments: number;
  creditors: number;
  paidAmount: string;
  liquidatedAmount: string | null;
  recipients: readonly PaymentRecipient[];
  /** Pessoas físicas e credores sem forma jurídica, agregados por natureza. */
  others: readonly PaymentRecipient[];
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
  liquidations: number | null;
  liquidatedAmount: string | null;
  liquidationGridMonths: number | null;
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

export function formatCnpj(cnpj: string): string;

export function compareWithDeclared(
  portalPaid: string,
  declaredPaid: string,
): Readonly<{ differenceAmount: string; coveragePercent: string }> | null;

export function paymentYear(value: string | undefined, currentYear: number): number;

export function getPublicPaymentRecipients(year: number): Promise<PaymentRecipientResult>;
