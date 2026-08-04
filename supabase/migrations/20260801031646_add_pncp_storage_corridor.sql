-- Corredor de Storage da Etapa 2 (PNCP): entra na lista fechada de
-- prefixos. Nenhuma identidade é cadastrada pela migration; a ativação do
-- corredor é um ato registrado, como nos anteriores.

alter table audit.storage_workload_identities
  drop constraint storage_workload_identities_object_prefix_check;

alter table audit.storage_workload_identities
  add constraint storage_workload_identities_object_prefix_check check (
    object_prefix in (
      'querido-diario/gazettes/',
      'barreiras-diario/gazettes/',
      'pncp/procurement/'
    )
  );
