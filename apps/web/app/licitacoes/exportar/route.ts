import { loadProcurementExport, serializeProcurementCsv } from "../../../lib/procurement-csv.mjs";
import {
  PROCUREMENT_EXPORT_PARAMS,
  procurementFiltersFromParams,
} from "../../../lib/procurement-filters.mjs";
import { pncpProcurementSourceUrl } from "../../../lib/pncp-source-url";

export const dynamic = "force-dynamic";
export const revalidate = 0;

const headers = { "Cache-Control": "no-store, max-age=0", "X-Content-Type-Options": "nosniff" };
const errorResponse = (message: string, status: number) =>
  new Response(message + "\n", {
    status,
    headers: { ...headers, "Content-Type": "text/plain; charset=utf-8" },
  });

export async function GET(request: Request): Promise<Response> {
  const params = new URL(request.url).searchParams;
  if (
    [...params.keys()].some((key) => !PROCUREMENT_EXPORT_PARAMS.includes(key)) ||
    PROCUREMENT_EXPORT_PARAMS.some((key) => params.getAll(key).length > 1)
  ) {
    return errorResponse("Consulta inválida. Volte à página de compras e ajuste os filtros.", 400);
  }
  const filters = procurementFiltersFromParams(Object.fromEntries(params));
  const supabaseUrl = process.env.PUBLIC_DATA_SUPABASE_URL?.trim();
  const publishableKey = process.env.PUBLIC_DATA_SUPABASE_PUBLISHABLE_KEY?.trim();
  if (!supabaseUrl?.startsWith("https://") || !publishableKey?.startsWith("sb_publishable_")) {
    return errorResponse("A exportação está indisponível no momento.", 503);
  }

  const result = await loadProcurementExport(async (offset) => {
    const response = await fetch(`${supabaseUrl}/rest/v1/rpc/get_pncp_procurements_page`, {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Accept-Profile": "api",
        apikey: publishableKey,
        "Content-Profile": "api",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        page_size: 100,
        page_offset: offset,
        supplier_key_filter: filters.supplierKey ?? null,
        fiscal_year_filter: filters.fiscalYear ?? null,
        query_filter: filters.query ?? null,
        modality_filter: filters.modality ?? null,
        status_filter: filters.status ?? null,
        unit_filter: filters.unit ?? null,
      }),
      cache: "no-store",
      signal: AbortSignal.timeout(10_000),
    });
    if (!response.ok) throw Error("Unavailable");
    return response.text();
  });

  if (result.status === "empty") {
    return errorResponse(
      "Nenhuma contratação publicada nesta seleção. Isso não significa que a fonte oficial não tenha contratações.",
      409,
    );
  }
  if (result.status === "too_large") {
    return errorResponse("A seleção passa de 2.000 contratações. Use um filtro de ano ou órgão.", 413);
  }
  try {
    if (result.status !== "ready") throw Error("Unavailable");
    const csv = serializeProcurementCsv(result, pncpProcurementSourceUrl);
    const suffix = filters.fiscalYear ? `-${filters.fiscalYear}` : "";
    return new Response(csv, {
      headers: {
        ...headers,
        "Content-Type": "text/csv; charset=utf-8",
        "Content-Disposition": `attachment; filename="contratacoes-pncp-barreiras${suffix}.csv"`,
      },
    });
  } catch {
    return errorResponse(
      "Não foi possível validar o arquivo completo. Tente novamente. Isso não significa que não haja contratações.",
      503,
    );
  }
}
