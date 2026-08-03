export type ProcurementResult = Readonly<{
  numeroItem: number;
  fornecedor: string;
  tipoPessoa: string | null;
  niFornecedor: string | null;
  valorTotalHomologado: number | null;
  dataResultado: string | null;
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

function parseProcurement(
  row: Record<string, unknown>,
): Procurement | null {
  const controlNumber = optionalString(row.control_number);
  const objeto = optionalString(row.objeto);
  const dataPublicacao = optionalString(row.data_publicacao);
  const resultados = parseResults(row.resultados);
  if (
    controlNumber === null ||
    objeto === null ||
    !Number.isSafeInteger(row.ano) ||
    !Number.isSafeInteger(row.sequencial) ||
    (dataPublicacao !== null && !ISO_DATE.test(dataPublicacao)) ||
    resultados === null ||
    row.methodology_version !== "pncp-procurements/1.0.0" &&
    row.methodology_version !== "pncp-procurements/1.1.0" &&
    row.methodology_version !== "pncp-procurements/1.2.0"
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
      `${supabaseUrl}/rest/v1/rpc/get_pncp_procurements_structured`,
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
