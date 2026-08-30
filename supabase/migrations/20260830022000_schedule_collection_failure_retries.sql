update source.collection_failures
set next_retry_at = failed_at + interval '1 hour'
where status = 'retry_scheduled'
  and retryable
  and next_retry_at is null;

alter table source.collection_failures
  add constraint collection_failures_scheduled_retry_time_check
  check (status <> 'retry_scheduled' or next_retry_at is not null) not valid;

alter table source.collection_failures
  validate constraint collection_failures_scheduled_retry_time_check;
