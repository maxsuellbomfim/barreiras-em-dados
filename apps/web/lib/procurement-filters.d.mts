export type ProcurementFilterValues = {
  supplierKey?: string;
  fiscalYear?: number;
  query?: string;
  modality?: string;
  status?: string;
  unit?: string;
};

export function procurementFiltersFromParams(
  params: Readonly<Record<string, string | undefined>>,
): ProcurementFilterValues;

export function procurementExportHref(filters: Readonly<ProcurementFilterValues>): string;

export const PROCUREMENT_EXPORT_PARAMS: readonly string[];
