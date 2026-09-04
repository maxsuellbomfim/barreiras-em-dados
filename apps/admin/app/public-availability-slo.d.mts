export type PublicAvailabilitySloInput = Readonly<{
  availability_success_streak_days: number | null;
  availability_days_observed: number | null;
  availability_expected_runs_per_day: number | null;
  availability_daily_history: unknown;
}>;

export type PublicAvailabilityDay = Readonly<{
  day: string;
  label: string;
  detail: string;
  tone: "healthy" | "failed" | "attention" | "unknown";
}>;

export type PublicAvailabilitySloPresentation = Readonly<{
  progress: string;
  percent: number;
  ready: boolean;
  note: string;
  limitation: string;
  history: readonly PublicAvailabilityDay[];
}>;

export function formatPublicAvailabilitySlo(
  item: PublicAvailabilitySloInput,
): PublicAvailabilitySloPresentation | null;
