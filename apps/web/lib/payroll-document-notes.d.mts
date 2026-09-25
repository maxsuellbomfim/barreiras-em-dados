export type PayrollDocumentNote = Readonly<{ title: string; body: string }>;

export const PAYROLL_DOCUMENT_NOTES: ReadonlyMap<string, PayrollDocumentNote>;

export function payrollDocumentNotes(
  documents: readonly Readonly<{ artifactSha256: string }>[],
): readonly PayrollDocumentNote[];
