export type SanctionRegistry = "ceis" | "cnep" | "cepim" | "leniencia";

export type SupplierSanction = Readonly<{
  sanctionRecordId: string | null;
  registry: SanctionRegistry;
  sanctionId: string;
  supplierCnpj: string;
  sanctionedName: string;
  companyName: string | null;
  sanctionType: string | null;
  sanctioningBody: string | null;
  sanctioningBodySphere: string | null;
  sanctioningBodyUf: string | null;
  sanctionSource: string | null;
  processNumber: string | null;
  startDateText: string | null;
  endDateText: string | null;
  publicationDateText: string | null;
  referenceDateText: string | null;
  legalBasisCodes: readonly string[];
  apiSourceUrl: string;
  artifactSha256: string;
  collectedAt: string;
  methodologyVersion: "supplier-sanctions/1.0.0";
}>;

export function parseSupplierSanctionRows(
  rows: unknown,
): readonly SupplierSanction[] | null;

export function formatSanctionCnpj(cnpj: string): string;

export function sanctionRegistryLabel(registry: SanctionRegistry): string;

export function sanctionPortalUrl(cnpj: string): string;
