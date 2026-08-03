export type ProcurementResult = Readonly<{
  numeroItem: number;
  fornecedor: string;
  tipoPessoa: string | null;
  niFornecedor: string | null;
  valorTotalHomologado: number | null;
  dataResultado: string | null;
}>;

export type ProcurementExecutionSummary = Readonly<{
  state: "linked" | "no_linked_execution" | "not_normalized" | "not_available";
  methodologyVersion: string;
  contractsCount: number;
  commitmentsCount: number;
  liquidationsCount: number;
  paymentsCount: number;
  contractCurrentAmount: number;
  committedAmount: number;
  liquidatedAmount: number;
  paidAmount: number;
  evidenceCount: number;
  evidence: readonly ProcurementEvidence[];
}>;

export type ProcurementEvidence = Readonly<{
  entityType: "contratacao" | "contrato" | "empenho" | "liquidacao" | "pagamento";
  rawRecordId: string;
  recordType: string;
  sourceUrl: string;
  sha256: string;
  retrievedAt: string;
  collectorVersion: string;
  parserVersion: string;
}>;

export type Procurement = Readonly<{
  controlNumber: string;
  ano: number;
  sequencial: number;
  modalidade: string | null;
  objeto: string;
  situacao: string | null;
  unidade: string | null;
  valorEstimado: number | null;
  valorHomologado: number | null;
  dataPublicacao: string | null;
  resultados: readonly ProcurementResult[];
  executionSummary: ProcurementExecutionSummary;
  methodologyVersion: string;
}>;

export type ProcurementsResult =
  | Readonly<{ state: "available"; procurements: readonly Procurement[] }>
  | Readonly<{ state: "unavailable" }>;

export type ProcurementFilterOption = Readonly<{
  optionType: "modalidade" | "situacao" | "orgao";
  value: string;
  variantCount: number;
  variants: readonly string[];
  procurementCount: number;
}>;

export type ProcurementFilterOptionsResult =
  | Readonly<{ state: "available"; options: readonly ProcurementFilterOption[] }>
  | Readonly<{ state: "unavailable" }>;

export type ProcurementFilters = Readonly<{
  supplierKey?: string;
  fiscalYear?: number;
  query?: string;
  modality?: string;
  status?: string;
  unit?: string;
}>;

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;

function optionalString(value: unknown): string | null {
  return typeof value === "string" && value.trim().length > 0 ? value : null;
}

function optionalNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function parseFilterOption(row: Record<string, unknown>): ProcurementFilterOption | null {
  const optionType = row.option_type;
  const value = optionalString(row.option_value);
  const variants = row.variants;
  const variantValues = Array.isArray(variants)
    ? variants.filter((variant): variant is string => typeof variant === "string" && variant.trim().length > 0)
    : [];
  const variantCount = row.variant_count;
  const count = row.procurement_count;
  if (
    (optionType !== "modalidade" && optionType !== "situacao" && optionType !== "orgao") ||
    value === null ||
    !Number.isSafeInteger(variantCount) ||
    Number(variantCount) < 1 ||
    variantValues.length !== Number(variantCount) ||
    !Number.isSafeInteger(count) ||
    Number(count) < 1
  ) {
    return null;
  }
  return {
    optionType,
    value,
    variantCount: Number(variantCount),
    variants: variantValues,
    procurementCount: Number(count),
  };
}

function parseResults(value: unknown): readonly ProcurementResult[] | null {
  if (!Array.isArray(value)) {
    return null;
  }
  const results: ProcurementResult[] = [];
  for (const raw of value) {
    if (typeof raw !== "object" || raw === null) {
      return null;
    }
    const row = raw as Record<string, unknown>;
    const fornecedor = optionalString(row.fornecedor);
    if (!Number.isSafeInteger(row.numero_item) || fornecedor === null) {
      return null;
    }
    const dataResultado = optionalString(row.data_resultado);
    if (dataResultado !== null && !ISO_DATE.test(dataResultado)) {
      return null;
    }
    results.push({
      numeroItem: Number(row.numero_item),
      fornecedor,
      tipoPessoa: optionalString(row.tipo_pessoa),
      niFornecedor: optionalString(row.ni_fornecedor),
      valorTotalHomologado: optionalNumber(row.valor_total_homologado),
      dataResultado,
    });
  }
  return results;
}

function parseExecutionSummary(value: unknown): ProcurementExecutionSummary | null {
  if (typeof value !== "object" || value === null) return null;
  const row = value as Record<string, unknown>;
  const state = row.state;
  if (
    state !== "linked" &&
    state !== "no_linked_execution" &&
    state !== "not_normalized" &&
    state !== "not_available"
  ) {
    return null;
  }
  const counts = [
    row.contracts_count,
    row.commitments_count,
    row.liquidations_count,
    row.payments_count,
  ];
  if (!counts.every((count) => Number.isSafeInteger(count) && Number(count) >= 0)) {
    return null;
  }
  const amounts = [
    row.contract_current_amount,
    row.committed_amount,
    row.liquidated_amount,
    row.paid_amount,
  ];
  if (!amounts.every((amount) => typeof amount === "number" && Number.isFinite(amount) && amount >= 0)) {
    return null;
  }
  const methodologyVersion = optionalString(row.methodology_version);
  if (methodologyVersion === null) return null;
  const rawEvidence = row.evidence;
  const evidence: ProcurementEvidence[] = [];
  if (rawEvidence !== undefined) {
    if (!Array.isArray(rawEvidence)) return null;
    for (const candidate of rawEvidence) {
      if (typeof candidate !== "object" || candidate === null) return null;
      const item = candidate as Record<string, unknown>;
      const entityType = item.entity_type;
      const rawRecordId = optionalString(item.raw_record_id);
      const recordType = optionalString(item.record_type);
      const sourceUrl = optionalString(item.source_url);
      const sha256 = optionalString(item.sha256);
      const retrievedAt = optionalString(item.retrieved_at);
      const collectorVersion = optionalString(item.collector_version);
      const parserVersion = optionalString(item.parser_version);
      if (
        (entityType !== "contratacao" && entityType !== "contrato" && entityType !== "empenho" && entityType !== "liquidacao" && entityType !== "pagamento") ||
        rawRecordId === null ||
        recordType === null ||
        sourceUrl === null ||
        !sourceUrl.startsWith("https://") ||
        sha256 === null ||
        !/^[0-9a-f]{64}$/.test(sha256) ||
        retrievedAt === null ||
        collectorVersion === null ||
        parserVersion === null
      ) {
        return null;
      }
      evidence.push({
        entityType,
        rawRecordId,
        recordType,
        sourceUrl,
        sha256,
        retrievedAt,
        collectorVersion,
        parserVersion,
      });
    }
  }
  const evidenceCount = row.evidence_count === undefined ? evidence.length : row.evidence_count;
  if (!Number.isSafeInteger(evidenceCount) || Number(evidenceCount) !== evidence.length) {
    return null;
  }
  return {
    state,
    methodologyVersion,
    contractsCount: Number(counts[0]),
    commitmentsCount: Number(counts[1]),
    liquidationsCount: Number(counts[2]),
    paymentsCount: Number(counts[3]),
    contractCurrentAmount: Number(amounts[0]),
    committedAmount: Number(amounts[1]),
    liquidatedAmount: Number(amounts[2]),
    paidAmount: Number(amounts[3]),
    evidenceCount: Number(evidenceCount),
    evidence,
  };
}

function parseProcurement(
  row: Record<string, unknown>,
): Procurement | null {
  const controlNumber = optionalString(row.control_number);
  const objeto = optionalString(row.objeto);
  const dataPublicacao = optionalString(row.data_publicacao);
  const resultados = parseResults(row.resultados);
  const executionSummary =
    row.execution_summary === undefined
      ? {
          state: "not_available" as const,
          methodologyVersion: "pncp-execution-links/unknown",
          contractsCount: 0,
          commitmentsCount: 0,
          liquidationsCount: 0,
          paymentsCount: 0,
          contractCurrentAmount: 0,
          committedAmount: 0,
          liquidatedAmount: 0,
          paidAmount: 0,
          evidenceCount: 0,
          evidence: [],
        }
      : parseExecutionSummary(row.execution_summary);
  if (
    controlNumber === null ||
    objeto === null ||
    !Number.isSafeInteger(row.ano) ||
    !Number.isSafeInteger(row.sequencial) ||
    (dataPublicacao !== null && !ISO_DATE.test(dataPublicacao)) ||
    resultados === null ||
    (row.methodology_version !== "pncp-procurements/1.0.0" &&
      row.methodology_version !== "pncp-procurements/1.1.0" &&
      row.methodology_version !== "pncp-procurements/1.2.0" &&
      row.methodology_version !== "pncp-procurements/1.3.0" &&
      row.methodology_version !== "pncp-procurements/1.4.0") ||
    executionSummary === null
  ) {
    return null;
  }
  return {
    controlNumber,
    ano: Number(row.ano),
    sequencial: Number(row.sequencial),
    modalidade: optionalString(row.modalidade),
    objeto,
    situacao: optionalString(row.situacao),
    unidade: optionalString(row.unidade),
    valorEstimado: optionalNumber(row.valor_estimado),
    valorHomologado: optionalNumber(row.valor_homologado),
    dataPublicacao,
    resultados,
    executionSummary,
    methodologyVersion: String(row.methodology_version),
  };
}

export async function getPncpProcurements(
  filters: ProcurementFilters = {},
): Promise<ProcurementsResult> {
  const supabaseUrl = process.env.PUBLIC_DATA_SUPABASE_URL?.trim();
  const publishableKey =
    process.env.PUBLIC_DATA_SUPABASE_PUBLISHABLE_KEY?.trim();
  if (
    !supabaseUrl ||
    !publishableKey ||
    !supabaseUrl.startsWith("https://") ||
    !publishableKey.startsWith("sb_publishable_")
  ) {
    return { state: "unavailable" };
  }

  try {
    const response = await fetch(
      `${supabaseUrl}/rest/v1/rpc/get_pncp_procurements_normalized`,
      {
        method: "POST",
        headers: {
          Accept: "application/json",
          "Accept-Profile": "api",
          apikey: publishableKey,
          "Content-Profile": "api",
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          page_size: 60,
          supplier_key_filter: filters.supplierKey ?? null,
          fiscal_year_filter: filters.fiscalYear ?? null,
          query_filter: filters.query ?? null,
          modality_filter: filters.modality ?? null,
          status_filter: filters.status ?? null,
          unit_filter: filters.unit ?? null,
        }),
        next: { revalidate: 300 },
        signal: AbortSignal.timeout(5_000),
      },
    );
    if (!response.ok) {
      return { state: "unavailable" };
    }
    const payload = await response.json();
    if (!Array.isArray(payload)) {
      return { state: "unavailable" };
    }
    const procurements: Procurement[] = [];
    for (const row of payload) {
      const procurement = parseProcurement(row as Record<string, unknown>);
      if (procurement === null) {
        return { state: "unavailable" };
      }
      procurements.push(procurement);
    }
    return { state: "available", procurements };
  } catch {
    return { state: "unavailable" };
  }
}

export async function getPncpProcurementFilterOptions(): Promise<ProcurementFilterOptionsResult> {
  const supabaseUrl = process.env.PUBLIC_DATA_SUPABASE_URL?.trim();
  const publishableKey =
    process.env.PUBLIC_DATA_SUPABASE_PUBLISHABLE_KEY?.trim();
  if (
    !supabaseUrl ||
    !publishableKey ||
    !supabaseUrl.startsWith("https://") ||
    !publishableKey.startsWith("sb_publishable_")
  ) {
    return { state: "unavailable" };
  }

  try {
    const response = await fetch(
      `${supabaseUrl}/rest/v1/rpc/get_pncp_procurement_filter_options_normalized`,
      {
        method: "POST",
        headers: {
          Accept: "application/json",
          "Accept-Profile": "api",
          apikey: publishableKey,
          "Content-Profile": "api",
          "Content-Type": "application/json",
        },
        body: "{}",
        next: { revalidate: 300 },
        signal: AbortSignal.timeout(5_000),
      },
    );
    if (!response.ok) return { state: "unavailable" };
    const payload = await response.json();
    if (!Array.isArray(payload)) return { state: "unavailable" };
    const options: ProcurementFilterOption[] = [];
    for (const row of payload) {
      const option = parseFilterOption(row as Record<string, unknown>);
      if (option === null) return { state: "unavailable" };
      options.push(option);
    }
    return { state: "available", options };
  } catch {
    return { state: "unavailable" };
  }
}
