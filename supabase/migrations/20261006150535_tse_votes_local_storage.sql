begin;

-- O CDN do TSE responde HTTP 403 aos servidores do GitHub; os pleitos
-- municipais anteriores (2012, 2016, 2020) são preservados pelo executor
-- local (scripts/run-tse-votes.ps1), cuja identidade técnica ainda não podia
-- gravar no prefixo da votação. Mesmo padrão do cadastro CNPJ da Receita.
insert into audit.storage_workload_identities (
  slug, auth_user_id, bucket_id, object_prefix, can_select, can_insert,
  status, activated_at, metadata
)
values (
  'tse-votes-local-collector',
  'c0f3b0e9-0e30-440b-b4c2-31a25a08cb3a',
  'raw-artifacts',
  'tse/votacao/',
  true,
  true,
  'active',
  statement_timestamp(),
  jsonb_build_object(
    'purpose', 'tse_municipal_election_backfill',
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
