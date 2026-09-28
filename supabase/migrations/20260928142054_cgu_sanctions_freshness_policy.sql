begin;

-- ADR 0089: fonte fora do ar só é falha tratada dentro de um prazo. As
-- sanções da CGU rodam todo dia; 48 horas de tolerância somam 72 horas sem
-- coleta válida antes de a indisponibilidade virar falha não tratada.
update source.source_endpoints as endpoint
set freshness_policy_kind = 'scheduled',
    freshness_expected_hours = 24,
    freshness_grace_hours = 48,
    freshness_policy_note =
      'Rotina diária; fonte fora do ar é aviso por até 72 horas sem coleta válida (ADR 0089).',
    freshness_policy_version = 'source-freshness/1.1.0'
from source.data_sources as source
where source.id = endpoint.data_source_id
  and source.slug = 'cgu-portal-transparencia'
  and endpoint.slug = 'sanctions-api';

commit;
