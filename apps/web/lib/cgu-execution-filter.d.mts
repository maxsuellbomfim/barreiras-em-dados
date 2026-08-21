import type { CguFederalAmendment } from "./cgu-federal-amendments.mjs";

export type CguExecutionFilters = Readonly<{
  authorKey: string | null;
  fiscalYear: number | null;
}>;

export function resolveCguExecutionFilters(
  requestedAuthor: string | readonly string[] | undefined,
  requestedYear: string | readonly string[] | undefined,
  amendments: readonly CguFederalAmendment[],
): CguExecutionFilters;

export function filterCguExecutionAmendments(
  amendments: readonly CguFederalAmendment[],
  filters: CguExecutionFilters,
): readonly CguFederalAmendment[];
