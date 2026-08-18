export type MunicipalContract = Readonly<{
  contractId: string;
  sourceContractId: string | null;
  contractNumber: string;
  contractObject: string | null;
  supplierName: string;
  supplierDocumentKind:
    | "cnpj"
    | "cpf_pessoa_fisica"
    | "nao_informado"
    | "outro_formato";
  supplierDocument: string | null;
  contractValueText: string | null;
  referentialValueText: string | null;
  modalityCode: string | null;
  categoryCode: string | null;
  validityStartText: string | null;
  validityEndText: string | null;
  documentUrl: string;
  apiSourceUrl: string;
  artifactSha256: string;
  documentArtifactSha256: string | null;
  documentPreserved: boolean;
  collectedAt: string;
  methodologyVersion: "municipal-contracts/1.0.0";
}>;

export function parseMunicipalContractRows(
  rows: unknown,
): readonly MunicipalContract[] | null;

export function municipalSupplierLabel(contract: MunicipalContract): string;
