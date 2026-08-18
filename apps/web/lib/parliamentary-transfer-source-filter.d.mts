export type ParliamentaryTransferSource =
  | "legislaturas"
  | "federal-atual"
  | "federal-historico"
  | "federal-execucao"
  | "estadual";

export type ParliamentaryTransferSourceSelection = Readonly<{
  source: ParliamentaryTransferSource;
  showLegislatures: boolean;
  showCurrentFederal: boolean;
  showHistoricalFederal: boolean;
  showCguExecution: boolean;
  showState: boolean;
}>;

export function resolveTransferSourceSelection(
  requestedSource: string | readonly string[] | undefined,
): ParliamentaryTransferSourceSelection;
