export type PublicObligation = Readonly<{
  obligationId: string;
  obligationType: string;
  description: string;
  fiscalYear: number;
  periodStart: string | null;
  periodEnd: string;
  openingBalance: string | null;
  additionsAmount: string | null;
  reductionsAmount: string | null;
  paymentsPriorAmount: string | null;
  paymentsPeriodAmount: string | null;
  paymentsToDateAmount: string | null;
  closingBalance: string | null;
  status: "reported" | "active" | "settled" | "suspended" | "disputed" | "unknown";
  validationState: "validated" | "reconciled";
  sourceUrl: string;
  artifactSha256: string;
  sourceRetrievedAt: string;
  documentSourceUrl: string;
  documentArtifactSha256: string;
  documentRetrievedAt: string;
  methodologyVersion: string;
}>;

export type PublicObligationsResult =
  | Readonly<{ state: "available"; obligations: readonly PublicObligation[] }>
  | Readonly<{ state: "unavailable" }>;

export function getPublicObligations(
  fiscalYear?: number,
  obligationType?: string,
): Promise<PublicObligationsResult>;

export type PublicObligationCoverageRow = Readonly<{
  coverageId: string;
  fiscalYear: number;
  periodStart: string;
  periodEnd: string;
  coverageStatus:
    | "published"
    | "section_absent"
    | "section_incomplete"
    | "document_not_found"
    | "document_not_confirmed";
  sourceUrl: string | null;
  documentArtifactSha256: string | null;
  searchEvidenceSha256: string | null;
  evidenceArtifactCount: number | null;
  checkedAt: string | null;
  methodologyVersion: "public-obligation-coverage/1.1.0";
}>;

export type PublicObligationCoverageResult =
  | Readonly<{ state: "available"; rows: readonly PublicObligationCoverageRow[] }>
  | Readonly<{ state: "unavailable" }>;

export function getPublicObligationCoverage(
  fiscalYearFrom?: number,
  fiscalYearTo?: number,
): Promise<PublicObligationCoverageResult>;
