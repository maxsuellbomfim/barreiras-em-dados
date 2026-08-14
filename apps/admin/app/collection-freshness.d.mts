export type CollectionFreshnessInput = Readonly<{
  freshness_status:
    | "current"
    | "overdue"
    | "never_updated"
    | "not_monitored";
  freshness_expected_hours: number | null;
  freshness_grace_hours: number;
  freshness_due_at: string | null;
  freshness_overdue_hours: number | null;
}>;

export function formatFreshnessPolicy(
  item: CollectionFreshnessInput,
): string;

export function formatFreshnessStatus(
  item: CollectionFreshnessInput,
): string;

export function freshnessRequiresAttention(
  item: CollectionFreshnessInput,
): boolean;
