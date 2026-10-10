const SHA256 = /^[0-9a-f]{64}$/;
const CNPJ = /^\d{14}$/;
const REGISTRIES = new Set(["ceis", "cnep", "cepim", "leniencia"]);
const METHODOLOGY = "supplier-sanctions/1.0.0";

function requiredText(value) {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function optionalText(value) {
  return value === null || value === undefined ? null : requiredText(value);
}

function parseSanctionRow(row) {
  if (typeof row !== "object" || row === null) return null;
  const registry = requiredText(row.registry);
  const sanctionId = requiredText(row.sanction_id);
  const supplierCnpj = requiredText(row.supplier_cnpj);
  const sanctionedName = requiredText(row.sanctioned_name);
  const apiSourceUrl = requiredText(row.api_source_url);
  const artifactSha256 = requiredText(row.artifact_sha256);
  const collectedAt = requiredText(row.collected_at);
  const legalBasisCodes = Array.isArray(row.legal_basis_codes)
    ? row.legal_basis_codes.filter((code) => typeof code === "string")
    : null;
  if (
    !registry || !REGISTRIES.has(registry) || !sanctionId ||
    // A projeção só publica pessoa jurídica; qualquer documento fora do CNPJ
    // de 14 dígitos invalida o lote inteiro no navegador também.
    !supplierCnpj || !CNPJ.test(supplierCnpj) ||
    !sanctionedName || legalBasisCodes === null ||
    !apiSourceUrl?.startsWith("https://") ||
    !artifactSha256 || !SHA256.test(artifactSha256) ||
    !collectedAt || !Number.isFinite(Date.parse(collectedAt)) ||
    row.methodology_version !== METHODOLOGY
  ) return null;
  return {
    sanctionRecordId: requiredText(row.sanction_record_id),
    registry,
    sanctionId,
    supplierCnpj,
    sanctionedName,
    companyName: optionalText(row.company_name),
    sanctionType: optionalText(row.sanction_type),
    sanctioningBody: optionalText(row.sanctioning_body),
    sanctioningBodySphere: optionalText(row.sanctioning_body_sphere),
    sanctioningBodyUf: optionalText(row.sanctioning_body_uf),
    sanctionSource: optionalText(row.sanction_source),
    processNumber: optionalText(row.process_number),
    startDateText: optionalText(row.start_date_text),
    endDateText: optionalText(row.end_date_text),
    publicationDateText: optionalText(row.publication_date_text),
    referenceDateText: optionalText(row.reference_date_text),
    legalBasisCodes,
    apiSourceUrl,
    artifactSha256,
    collectedAt,
    methodologyVersion: METHODOLOGY,
  };
}

export function parseSupplierSanctionRows(rows) {
  if (!Array.isArray(rows)) return null;
  const parsed = rows.map(parseSanctionRow);
  return parsed.some((row) => row === null) ? null : parsed;
}

export function formatSanctionCnpj(cnpj) {
  return `${cnpj.slice(0, 2)}.${cnpj.slice(2, 5)}.${cnpj.slice(5, 8)}/${cnpj.slice(8, 12)}-${cnpj.slice(12)}`;
}

const REGISTRY_LABELS = {
  ceis: "CEIS — Empresas Inidôneas e Suspensas",
  cnep: "CNEP — Empresas Punidas (Lei Anticorrupção)",
  cepim: "CEPIM — Entidades sem Fins Lucrativos Impedidas",
  leniencia: "Acordo de Leniência — Lei Anticorrupção",
};

export function sanctionRegistryLabel(registry) {
  return REGISTRY_LABELS[registry] ?? registry;
}

export function sanctionPortalUrl(cnpj) {
  // A consulta oficial cobre todos os cadastros para o documento informado.
  return `https://portaldatransparencia.gov.br/sancoes/consulta?cpfCnpj=${cnpj}`;
}

// supplier-sanction-scope/1.0.0: alcance legal da sanção, por tipo e órgão,
// para o leitor não confundir impedimento em outro órgão com proibição de
// contratar com Barreiras. Classificação conservadora; quando o tipo não é
// reconhecido, diz que o alcance não foi classificado.
function normalizedText(value) {
  return (value ?? "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase();
}

export function sanctionLegalScope(sanction) {
  const type = normalizedText(sanction.sanctionType);
  const body = normalizedText(sanction.sanctioningBody);
  const appliedByBarreiras =
    /\bbarreiras\b/.test(body) &&
    normalizedText(sanction.sanctioningBodySphere) === "municipal";
  if (sanction.registry === "cepim") {
    return {
      kind: "transferencias_federais",
      appliesToBarreiras: false,
      text: "Impede a entidade de firmar convênios e receber transferências da União; não trata de contratos com o município.",
    };
  }
  if (sanction.registry === "leniencia") {
    return {
      kind: "sem_proibicao",
      appliesToBarreiras: false,
      text: "Acordo de leniência: não proíbe a empresa de contratar com o poder público.",
    };
  }
  if (type.includes("inidone")) {
    return {
      kind: "toda_administracao",
      appliesToBarreiras: true,
      text: "Declaração de inidoneidade: impede licitar e contratar com toda a administração pública, em qualquer esfera.",
    };
  }
  if (type.includes("proibicao de contratar com o poder publico") ||
      type.includes("proibicao de receber")) {
    return {
      kind: "decisao_judicial",
      appliesToBarreiras: null,
      text: "Proibição imposta por decisão judicial: o alcance está definido na própria decisão.",
    };
  }
  if (type.includes("impedimento") || type.includes("suspens")) {
    if (appliedByBarreiras) {
      return {
        kind: "ente_aplicador",
        appliesToBarreiras: true,
        text: "Aplicada por órgão de Barreiras: alcança licitações e contratos do próprio município.",
      };
    }
    return {
      kind: "ente_aplicador",
      appliesToBarreiras: false,
      text: type.includes("suspens")
        ? "Suspensão: vale para o órgão que a aplicou (entendimento do TCU); não proíbe contratar com Barreiras."
        : "Impedimento: vale só para o ente federativo que o aplicou (Lei 14.133, art. 156, § 4º); não proíbe contratar com Barreiras.",
    };
  }
  if (type.includes("multa") || type.includes("publicacao extraordinaria")) {
    return {
      kind: "sem_proibicao",
      appliesToBarreiras: false,
      text: "Multa ou publicação da condenação: não proíbe a empresa de contratar com o poder público.",
    };
  }
  return {
    kind: "nao_classificado",
    appliesToBarreiras: null,
    text: "Alcance não classificado automaticamente: consulte o órgão sancionador.",
  };
}
