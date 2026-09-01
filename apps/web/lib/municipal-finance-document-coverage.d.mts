export type MunicipalFinanceDocumentResource =
  | "balancetes"
  | "pdc-resumo-execucao-da-receita"
  | "pdc-resumo-execucao-da-despesa";

export type MunicipalFinanceDocumentCoverageEntry = Readonly<{
  documentId: string;
  resource: MunicipalFinanceDocumentResource;
  fiscalYear: number;
  referenceMonth: number;
  documentUrl: string;
  documentPreserved: boolean;
  artifactSha256: string | null;
  collectedAt: string;
}>;

export type MunicipalFinanceDocumentCoverageResult =
  | Readonly<{ state: "available"; entries: readonly MunicipalFinanceDocumentCoverageEntry[] }>
  | Readonly<{ state: "unavailable" }>;

export type MunicipalFinanceDocumentCoverageStatus =
  | "preserved"
  | "catalogued"
  | "not_listed"
  | "not_due";

export const MUNICIPAL_FINANCE_DOCUMENT_FAMILIES: readonly Readonly<{
  resource: MunicipalFinanceDocumentResource;
  shortLabel: string;
}>[];

export function toMunicipalFinanceDocumentCoverageEntry(
  value: unknown,
): MunicipalFinanceDocumentCoverageEntry | null;
export function municipalFinanceDocumentCoverageStatusLabel(
  status: MunicipalFinanceDocumentCoverageStatus,
): string;
export function buildMunicipalFinanceDocumentCoverage(
  entries: readonly MunicipalFinanceDocumentCoverageEntry[],
  options?: Readonly<{ startYear?: number; today?: string }>,
): Readonly<{
  families: typeof MUNICIPAL_FINANCE_DOCUMENT_FAMILIES;
  years: readonly Readonly<{
    year: number;
    months: readonly Readonly<{
      referenceMonth: number;
      families: readonly Readonly<{
        resource: MunicipalFinanceDocumentResource;
        shortLabel: string;
        status: MunicipalFinanceDocumentCoverageStatus;
        entry: MunicipalFinanceDocumentCoverageEntry | null;
        evidenceCount: number;
      }>[];
    }>[];
  }>[];
}> | null;
export function parseMunicipalFinanceDocumentCoverageApiPayload(
  value: unknown,
): MunicipalFinanceDocumentCoverageResult | null;
