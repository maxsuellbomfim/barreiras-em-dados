export type StateLoaStudyEnvelope = Readonly<{
  amendmentRows: readonly unknown[];
  executionRows: readonly unknown[];
  totalCount: number;
  methodologyVersion: "bahia-state-loa-study/1.0.0";
}>;

export function parseStateLoaStudyRows(
  rows: unknown,
): StateLoaStudyEnvelope | null;

export function resolveStateLoaStudyPage(rawPage: unknown): number;

export function stateLoaStudyPageHref(
  fiscalYear: number,
  page: number,
): string;
