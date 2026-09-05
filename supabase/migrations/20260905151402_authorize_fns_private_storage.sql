begin;

-- User-authorized scope: immutable private FNS originals only.
alter table audit.storage_workload_identities
  drop constraint storage_workload_identities_object_prefix_check;
alter table audit.storage_workload_identities
  add constraint storage_workload_identities_object_prefix_check check (
    object_prefix = any(array[
      'querido-diario/gazettes/', 'barreiras-diario/gazettes/',
      'pncp/procurement/', 'camara-federal/deputados/', 'alba/deputados/',
      'camara-municipal/vereadores/', 'tse/votacao/', 'municipal-transparency/',
      'prefeitura/executivo/', 'transferegov/parcerias/',
      'bahia/emendas-estaduais/', 'bahia/loa-emendas-estaduais/',
      'bahia/transferencias-especiais/', 'cgu/emendas-federais/', 'cgu/sancoes/',
      'siconfi/dca/', 'tcm-ba/monthly/', 'tcm-ba/monthly-documents/',
      'fns/payments/'
    ])
  );

with registered as (
  insert into audit.storage_workload_identities (
    slug, auth_user_id, bucket_id, object_prefix, can_select, can_insert,
    status, activated_at, metadata
  ) values (
    'fns-payment-evidence-collector', 'c0f3b0e9-0e30-440b-b4c2-31a25a08cb3a',
    'raw-artifacts', 'fns/payments/', true, true, 'active', statement_timestamp(),
    jsonb_build_object('purpose','fns_payment_raw_evidence', 'raw_visibility','private',
      'authorization','explicit_user_authorization', 'scope','single_closed_prefix')
  ) on conflict (auth_user_id, object_prefix) do nothing
  returning id, slug, bucket_id, object_prefix, status
)
insert into audit.audit_events (
  actor_type, actor_subject, action, target_type, target_id, after_state, metadata
)
select 'administrator', 'migration:authorize-fns-private-storage',
  'storage_workload_identity.activated', 'audit.storage_workload_identities',
  id, jsonb_build_object('slug',slug,'bucket_id',bucket_id,
    'object_prefix',object_prefix,'status',status),
  jsonb_build_object('raw_visibility','private','secret_values_persisted',false)
from registered;

-- Existing SELECT/INSERT policies resolve this closed prefix. No UPDATE,
-- DELETE, public bucket, service key or new authentication user is introduced.
commit;
