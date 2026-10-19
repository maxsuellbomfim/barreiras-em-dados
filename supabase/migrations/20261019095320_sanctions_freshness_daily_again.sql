begin;

-- Com a v10 (1.11.1) contando execução parcial sem erro, os lotes diários
-- das sanções da CGU voltam a atestar a coleta: o prazo volta a ser o diário
-- do ADR 0089 (alerta após 72 horas), em vez do ciclo semanal.
update source.source_endpoints as endpoint
set freshness_expected_hours = 24,
    freshness_grace_hours = 48,
    freshness_policy_note =
      'Lotes diários de 100 CNPJs (ciclo completo a cada ~7 dias); fonte fora do ar é aviso por até 72 horas sem execução concluída (ADR 0089).',
    freshness_policy_version = 'source-freshness/1.2.0'
from source.data_sources as source
where source.id = endpoint.data_source_id
  and source.slug = 'cgu-portal-transparencia'
  and endpoint.slug = 'sanctions-api';

commit;
