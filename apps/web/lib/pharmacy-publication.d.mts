export type PharmacyRecord = { id: string; establishment: string; date: string; amount: string; sha256: string };
export type PharmacyPublication = {status: 'pending' | 'unavailable' | 'ready'; year?: number; records: PharmacyRecord[]}
  | {status: 'empty_page'; year: number; records: []};
export function readPharmacyPublication(input: unknown): PharmacyPublication;
