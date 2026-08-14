export type TransferCoverageYear = Readonly<{
  fiscalYear: number;
  coverageStatus: string;
  publishedAmendmentCount: number | null;
}>;

export function resolveCurrentFederalTransferYear(
  requestedYear: string | readonly string[] | undefined,
  coverage: readonly TransferCoverageYear[] | null,
): number | null;

export function buildCurrentTransferRankingRequest(
  authorScope: "person" | "collective",
  fiscalYear: number | null,
): Readonly<{
  author_scope: "person" | "collective";
  fiscal_year_filter: number | null;
  page_size: 50;
}>;

export function buildCurrentTransfersRequest(
  fiscalYear: number,
): Readonly<{
  fiscal_year_filter: number;
  author_kind_filter: null;
  page_size: 200;
}>;
