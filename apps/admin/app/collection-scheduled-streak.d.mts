export type ScheduledRunStreakInput = Readonly<{
  scheduled_success_streak: number | null;
  scheduled_runs_observed: number | null;
  latest_scheduled_run_at: string | null;
}>;

export type ScheduledRunStreakPresentation = Readonly<{
  progress: string;
  note: string;
  percent: number;
  ready: boolean;
}>;

export function formatScheduledRunStreak(
  item: ScheduledRunStreakInput,
): ScheduledRunStreakPresentation | null;
