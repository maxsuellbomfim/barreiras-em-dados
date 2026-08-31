export type CollectionWorkProgressInput = Readonly<{
  latest_work_completed: number | null;
  latest_work_total: number | null;
  latest_work_remaining: number | null;
  latest_batch_processed: number | null;
}>;

export type CollectionWorkProgressPresentation = Readonly<{
  completed: string;
  remaining: string;
  latestBatch: string;
  percent: number;
}>;

export function formatCollectionWorkProgress(
  item: CollectionWorkProgressInput,
): CollectionWorkProgressPresentation | null;
