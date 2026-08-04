-- O workload de processamento usa a conexão PostgreSQL diretamente. RLS sem
-- privilégios de schema/tabela ainda resulta em permission denied antes que a
-- policy possa ser avaliada; concedemos somente o corredor mínimo necessário.

grant usage on schema political to collector_worker;

grant select on table political.representative_tse_crosswalk
  to collector_worker;
grant select, insert, update on table political.representative_alias_suggestions
  to collector_worker;
grant select on table political.representative_aliases
  to collector_worker;

comment on schema political is
  'Dados políticos municipais; acesso de workloads sempre limitado por grants e RLS.';
