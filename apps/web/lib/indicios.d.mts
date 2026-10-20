export type Indicio = Readonly<{
  findingId: string;
  ruleSlug: "supplier-recent-opening";
  ruleName: string;
  ruleDescription: string;
  ruleMethodology: string;
  severity: "information" | "low" | "medium" | "high";
  publicExplanation: string;
  /** Justificativa da revisão que aprovou o indício. */
  reviewRationale: string;
  /** automated = revisão automatizada registrada (código + agente), sem revisão humana. */
  reviewKind: "human" | "automated";
  reviewedAt: string;
  /** Razão social do cadastro da Receita, nunca nome de pessoa física. */
  supplierName: string;
  supplierCnpj: string;
  contractNumber: string;
  contractObject: string | null;
  contractValue: string;
  contractStart: string;
  openedOn: string;
  daysAfterOpening: number;
  amendmentsValue: string | null;
  contractSourceUrl: string | null;
  contractArtifactSha256: string;
  registryArtifactSha256: string;
  /** Há contestação aberta: o caso está em nova conferência. */
  underContestation: boolean;
}>;

export type IndiciosResult =
  | Readonly<{ state: "available"; items: readonly Indicio[] }>
  | Readonly<{ state: "unavailable" }>;

export function parseIndicioRows(rows: unknown): readonly Indicio[] | null;

export function formatCnpj(cnpj: string): string;

export function getPublicIndicios(): Promise<IndiciosResult>;
