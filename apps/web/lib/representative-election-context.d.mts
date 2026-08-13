export type ElectionOutcome =
  | "elected"
  | "alternate"
  | "not_elected"
  | "other"
  | "unknown";

export function classifyElectionOutcome(situation: string | null): ElectionOutcome;
export function outcomeLabel(outcome: ElectionOutcome): string;
export function electionCycleLabel(electionYear: number, office: string | null): string;
export function electionPeriodLabel(electionYear: number, office: string | null): string;
export function latestElectionYear(years: readonly number[]): string;
