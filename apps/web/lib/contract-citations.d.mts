export type ContractCitationGroup = Readonly<{
  /** pf_aggregate = pessoas físicas somadas por órgão, sem nome. */
  kind: "entity" | "pf_aggregate";
  category: "sem_correspondencia" | "publicado_no_pncp";
  publicBody: string;
  creditorName: string | null;
  citedNumber: string | null;
  citedExcerpt: string | null;
  commitments: number;
  payments: number;
  unreadablePayments: number;
  /** Soma exata das ordens de pagamento ligadas aos empenhos pela chave oficial. */
  paidAmount: string;
  firstIssueDate: string;
  lastIssueDate: string;
  /** Data em que a regra comparou a citação com a lista do portal. */
  listReadOn: string;
  latestCommitmentKey: string | null;
  pncpUrl: string | null;
  sourcePageUrl: string;
}>;

export type ContractCitationResult =
  | Readonly<{ state: "approved"; approvedAt: string; groups: readonly ContractCitationGroup[] }>
  | Readonly<{ state: "awaiting_review" }>
  | Readonly<{ state: "unavailable" }>;

export const FIRST_CITATION_YEAR: number;

export function parseContractCitationRows(
  rows: unknown,
): Exclude<ContractCitationResult, Readonly<{ state: "unavailable" }>> | null;

export function citationYear(value: string | undefined, currentYear: number): number;

export function getPublicContractCitations(year: number): Promise<ContractCitationResult>;
