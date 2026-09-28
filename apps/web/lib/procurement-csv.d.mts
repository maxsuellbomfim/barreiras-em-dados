export const PROCUREMENT_CSV_VERSION: string;
export const PROCUREMENT_EXPORT_LIMIT: number;
export const PROCUREMENT_EXPORT_PAGE: number;

export type ProcurementExport =
  | { status: "ready"; rows: readonly Record<string, unknown>[] }
  | { status: "empty" }
  | { status: "too_large" }
  | { status: "unavailable" };

export function parseExactProcurementRows(text: string): unknown;

export function loadProcurementExport(
  fetchPageText: (offset: number) => Promise<string>,
): Promise<ProcurementExport>;

export function serializeProcurementCsv(
  result: ProcurementExport,
  sourceUrl: (control: string) => string | null,
  exportedAt?: string,
): string;
