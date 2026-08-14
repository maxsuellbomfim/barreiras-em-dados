export type ParliamentaryTransferSource =
  | "legislaturas"
  | "federal-atual"
  | "federal-historico"
  | "estadual";

export type ParliamentaryTransferSourceSelection = Readonly<{
  source: ParliamentaryTransferSource;
  showLegislatures: boolean;
  showCurrentFederal: boolean;
  showHistoricalFederal: boolean;
  showState: boolean;
}>;

export function resolveTransferSourceSelection(
  requestedSource: string | readonly string[] | undefined,
): ParliamentaryTransferSourceSelection;
