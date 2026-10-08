begin;

-- O cron horário do GitHub pula a maioria das janelas (gate 6); o backfill
-- das edições 3353-3988 do Diário passa a rodar também pelo executor local
-- (scripts/run-direct-diary-backfill.ps1), cuja identidade técnica ainda não
-- podia gravar no prefixo do Diário direto. Mesmo padrão do TSE local.
insert into audit.storage_workload_identities (
  slug, auth_user_id, bucket_id, object_prefix, can_select, can_insert,
  status, activated_at, metadata
)
values (
  'barreiras-diario-local-collector',
  'c0f3b0e9-0e30-440b-b4c2-31a25a08cb3a',
  'raw-artifacts',
  'barreiras-diario/gazettes/',
  true,
  true,
  'active',
  statement_timestamp(),
  jsonb_build_object(
    'purpose', 'direct_diary_edition_backfill',
    'raw_visibility', 'private',
    'credentials', 'stored_outside_database_and_repository'
  )
)
on conflict (auth_user_id, object_prefix) do update
set
  slug = excluded.slug,
  can_select = excluded.can_select,
  can_insert = excluded.can_insert,
  status = excluded.status,
  activated_at = excluded.activated_at,
  metadata = excluded.metadata;

commit;
