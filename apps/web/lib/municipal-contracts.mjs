const SHA256 = /^[0-9a-f]{64}$/;
const CNPJ = /^\d{14}$/;
const DOCUMENT_KINDS = new Set([
  "cnpj",
  "cpf_pessoa_fisica",
  "nao_informado",
  "outro_formato",
]);
const METHODOLOGY = "municipal-contracts/1.0.0";

function requiredText(value) {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function optionalText(value) {
  return value === null || value === undefined ? null : requiredText(value);
}

function parseContractRow(row) {
  if (typeof row !== "object" || row === null) return null;
  const contractId = requiredText(row.contract_id);
  const contractNumber = requiredText(row.contract_number);
  const supplierName = requiredText(row.supplier_name);
  const documentKind = requiredText(row.supplier_document_kind);
  const supplierDocument = optionalText(row.supplier_document);
  const documentUrl = requiredText(row.document_url);
  const apiSourceUrl = requiredText(row.api_source_url);
  const artifactSha256 = requiredText(row.artifact_sha256);
  const collectedAt = requiredText(row.collected_at);
  if (
    !contractId || !contractNumber || !supplierName ||
    !documentKind || !DOCUMENT_KINDS.has(documentKind) ||
    // CPF de pessoa física jamais chega ao navegador; se a API publicar um
    // documento fora do formato CNPJ, o lote inteiro é rejeitado.
    (documentKind === "cnpj"
      ? supplierDocument === null || !CNPJ.test(supplierDocument)
      : supplierDocument !== null) ||
    !documentUrl?.startsWith("https://") ||
    !apiSourceUrl?.startsWith("https://") ||
    !artifactSha256 || !SHA256.test(artifactSha256) ||
    !collectedAt || !Number.isFinite(Date.parse(collectedAt)) ||
    typeof row.document_preserved !== "boolean" ||
    row.methodology_version !== METHODOLOGY
  ) return null;
  return {
    contractId,
    sourceContractId: optionalText(row.source_contract_id),
    contractNumber,
    contractObject: optionalText(row.contract_object),
    supplierName,
    supplierDocumentKind: documentKind,
    supplierDocument,
    contractValueText: optionalText(row.contract_value_text),
    referentialValueText: optionalText(row.referential_value_text),
    modalityCode: optionalText(row.modality_code),
    categoryCode: optionalText(row.category_code),
    validityStartText: optionalText(row.validity_start_text),
    validityEndText: optionalText(row.validity_end_text),
    documentUrl,
    apiSourceUrl,
    artifactSha256,
    documentArtifactSha256: optionalText(row.document_artifact_sha256),
    documentPreserved: row.document_preserved,
    collectedAt,
    methodologyVersion: METHODOLOGY,
  };
}

export function parseMunicipalContractRows(rows) {
  if (!Array.isArray(rows)) return null;
  const parsed = rows.map(parseContractRow);
  return parsed.some((row) => row === null) ? null : parsed;
}

export function municipalSupplierLabel(contract) {
  if (contract.supplierDocumentKind === "cnpj" && contract.supplierDocument) {
    const d = contract.supplierDocument;
    return `CNPJ ${d.slice(0, 2)}.${d.slice(2, 5)}.${d.slice(5, 8)}/${d.slice(8, 12)}-${d.slice(12)}`;
  }
  if (contract.supplierDocumentKind === "cpf_pessoa_fisica") {
    return "pessoa física (CPF não publicado por proteção de dados)";
  }
  if (contract.supplierDocumentKind === "outro_formato") {
    return "documento em formato não reconhecido na fonte";
  }
  return "documento não informado na fonte";
}
