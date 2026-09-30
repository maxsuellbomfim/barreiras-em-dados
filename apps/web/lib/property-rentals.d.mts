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
