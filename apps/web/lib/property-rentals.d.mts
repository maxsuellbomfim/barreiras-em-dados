export type PropertyRental = Readonly<{
  landlordName: string;
  publicBody: string;
  contractText: string | null;
  commitments: number;
  committedAmount: string;
  paidAmount: string;
  firstCommitmentDate: string;
  lastCommitmentDate: string;
  description: string | null;
  /** Trecho literal do histórico; null quando o histórico não cita endereço. */
  addressText: string | null;
  useText: string | null;
  /** 1.4.0: de onde veio o endereço; null nas versões anteriores. */
  addressSource: "historico_empenho" | "diario_oficial" | null;
  addressGazette: Readonly<{ year: number; edition: number; page: number }> | null;
  latestCommitmentKey: string;
  gridArtifactSha256: string;
  sourcePageUrl: string;
}>;

export type PropertyRentalSummary = Readonly<{
  landlords: number;
  commitments: number;
  committedAmount: string;
  paidAmount: string;
  gridMonths: number;
  /** Endereços distintos citados nos históricos do ano (1.3.0). */
  addresses: number | null;
}>;

export type PropertyRentalResult =
  | Readonly<{
      state: "available";
      summary: PropertyRentalSummary | null;
      rentals: readonly PropertyRental[];
    }>
  | Readonly<{ state: "unavailable" }>;

export const FIRST_RENTAL_YEAR: number;

export function parsePropertyRentalRows(
  rows: unknown,
): { summary: PropertyRentalSummary | null; rentals: PropertyRental[] } | null;

export function rentalYear(value: string | undefined, currentYear: number): number;

export function getPublicPropertyRentals(year: number): Promise<PropertyRentalResult>;

export function serializePropertyRentalsCsv(
  year: number,
  result: PropertyRentalResult,
  exportedAt?: string,
): string;
