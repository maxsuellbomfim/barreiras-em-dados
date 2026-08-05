export type CollectionBackfillInput = Readonly<{
  backfill_horizon: string | null;
  continuous_coverage_start: string | null;
  continuous_coverage_end: string | null;
  next_backfill_start: string | null;
  next_backfill_end: string | null;
  backfill_classified_days: number | null;
  backfill_total_days: number | null;
  backfill_progress_percent: number | null;
}>;

export type CollectionBackfillPresentation = Readonly<{
  coverage: string;
  nextWindow: string;
  progress: string;
  horizon: string;
}>;

export function formatBackfillProgress(
  item: CollectionBackfillInput,
): CollectionBackfillPresentation | null;
