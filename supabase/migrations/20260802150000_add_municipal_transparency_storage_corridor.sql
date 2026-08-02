-- ADR 0016: corredor de evidência bruta da transparência municipal.
-- A migration somente amplia a allowlist de prefixos. Ela não cria usuário,
-- não ativa credencial e não insere identidade técnica.

alter table audit.storage_workload_identities
  drop constraint if exists storage_workload_identities_object_prefix_check;

alter table audit.storage_workload_identities
  add constraint storage_workload_identities_object_prefix_check
  check (
    object_prefix = any (
      array[
        'querido-diario/gazettes/',
        'barreiras-diario/gazettes/',
        'pncp/procurement/',
        'camara-federal/deputados/',
        'camara-municipal/vereadores/',
        'tse/votacao/',
        'alba/deputados/',
        'municipal-transparency/'
      ]
    )
  );

comment on constraint storage_workload_identities_object_prefix_check
  on audit.storage_workload_identities is
  'Corredores fechados por fonte; municipal-transparency exige identidade técnica ativa em migration posterior.';
