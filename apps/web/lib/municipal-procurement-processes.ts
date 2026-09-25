import {
  parseMunicipalProcurementProcessRows,
  type MunicipalProcurementProcess,
} from "./municipal-procurement-processes.mjs";

export type { MunicipalProcurementProcess } from "./municipal-procurement-processes.mjs";
export {
  municipalCategoryLabel,
  municipalModalityLabel,
  municipalSourceCodeLabel,
} from "./municipal-procurement-processes.mjs";

export type MunicipalProcurementProcessesResult =
  | Readonly<{
      state: "available";
      page: number;
      hasMore: boolean;
      processes: readonly MunicipalProcurementProcess[];
    }>
  | Readonly<{ state: "unavailable" }>;

const PAGE_SIZE = 24;

export async function getPublicMunicipalProcurementProcesses(
  page = 1,
): Promise<
  MunicipalProcurementProcessesResult
> {
  const supabaseUrl = process.env.PUBLIC_DATA_SUPABASE_URL?.trim();
  const publishableKey = process.env.PUBLIC_DATA_SUPABASE_PUBLISHABLE_KEY?.trim();
  if (
    !supabaseUrl?.startsWith("https://") ||
    !publishableKey?.startsWith("sb_publishable_")
  ) {
    return { state: "unavailable" };
  }
  try {
    const response = await fetch(
      `${supabaseUrl}/rest/v1/rpc/get_public_municipal_procurement_processes`,
      {
        method: "POST",
        headers: {
          Accept: "application/json",
          "Accept-Profile": "api",
          apikey: publishableKey,
          "Content-Profile": "api",
          "Content-Type": "application/json",
        },
        // Uma linha a mais revela se há próxima página sem consulta de contagem.
        body: JSON.stringify({
          page_size: PAGE_SIZE + 1,
          page_offset: (page - 1) * PAGE_SIZE,
        }),
        next: { revalidate: 300 },
        signal: AbortSignal.timeout(5_000),
      },
    );
    if (!response.ok) return { state: "unavailable" };
    const processes = parseMunicipalProcurementProcessRows(
      await response.json(),
    );
    if (processes === null) return { state: "unavailable" };
    return {
      state: "available",
      page,
      hasMore: processes.length > PAGE_SIZE,
      processes: processes.slice(0, PAGE_SIZE),
    };
  } catch {
    return { state: "unavailable" };
  }
}
