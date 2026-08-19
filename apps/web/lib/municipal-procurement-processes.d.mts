export type MunicipalProcurementProcess = Readonly<{
  processRecordId: string;
  sourceProcessId: string | null;
  processNumber: string;
  noticeNumber: string | null;
  publicationDateText: string | null;
  openingDateText: string | null;
  processObject: string;
  biddingTypeCode: string | null;
  modalityCode: string | null;
  categoryCode: string | null;
  situationCode: string | null;
  resultCode: string | null;
  estimatedValueText: string | null;
  awardedValueText: string | null;
  apiSourceUrl: string;
  artifactSha256: string;
  collectedAt: string;
  methodologyVersion: "municipal-procurement-processes/1.0.0";
}>;

export function parseMunicipalProcurementProcessRows(
  rows: unknown,
): readonly MunicipalProcurementProcess[] | null;

export function municipalModalityLabel(code: string | null): string;

export function municipalCategoryLabel(code: string | null): string;

export function municipalSourceCodeLabel(code: string | null): string;
