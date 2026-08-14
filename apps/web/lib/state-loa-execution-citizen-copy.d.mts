export type StateLoaExecutionPublicStatus =
  | "execution_confirmed"
  | "ambiguous_official_key"
  | "not_found_in_execution_source"
  | "scope_not_available";

export type StateLoaExecutionStatusCopy = Readonly<{
  tone: "confirmed" | "pending" | "not-found" | "unavailable";
  label: string;
  explanation: string;
}>;

export function stateLoaExecutionStatusCopy(record: Readonly<{
  executionStatus: StateLoaExecutionPublicStatus;
  loaScopeOccurrences: number;
  executionOccurrences: number;
  paidAmount: string | null;
}>): StateLoaExecutionStatusCopy;
