export type ParliamentaryTransferSource =
  | "federal-atual"
  | "federal-historico"
  | "estadual";

export type ParliamentaryTransferSourceSelection = Readonly<{
  source: ParliamentaryTransferSource;
  showCurrentFederal: boolean;
  showHistoricalFederal: boolean;
  showState: boolean;
}>;

export function resolveTransferSourceSelection(
  requestedSource: string | readonly string[] | undefined,
): ParliamentaryTransferSourceSelection;
