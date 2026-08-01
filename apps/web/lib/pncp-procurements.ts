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

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;

function optionalString(value: unknown): string | null {
  return typeof value === "string" && value.trim().length > 0 ? value : null;
}

function optionalNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
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
    row.methodology_version !== "pncp-procurements/1.0.0"
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
    methodologyVersion: "pncp-procurements/1.0.0",
  };
}

export async function getPncpProcurements(): Promise<ProcurementsResult> {
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
      `${supabaseUrl}/rest/v1/rpc/get_pncp_procurements`,
      {
        method: "POST",
        headers: {
          Accept: "application/json",
          "Accept-Profile": "api",
          apikey: publishableKey,
          "Content-Profile": "api",
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ page_size: 60 }),
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
