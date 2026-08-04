-- Corredores de Storage por fonte: a identidade técnica passa a poder ter
-- um corredor por prefixo autorizado (linhas distintas, mesma disciplina),
-- e o prefixo da coleta direta do Diário de Barreiras entra na lista
-- fechada. Nenhuma identidade é cadastrada pela migration.

alter table audit.storage_workload_identities
  drop constraint storage_workload_identities_object_prefix_check;

alter table audit.storage_workload_identities
  add constraint storage_workload_identities_object_prefix_check check (
    object_prefix in (
      'querido-diario/gazettes/',
      'barreiras-diario/gazettes/'
    )
  );

alter table audit.storage_workload_identities
  drop constraint storage_workload_identities_auth_user_id_key;

alter table audit.storage_workload_identities
  add constraint storage_workload_identities_user_prefix_key
  unique (auth_user_id, object_prefix);
