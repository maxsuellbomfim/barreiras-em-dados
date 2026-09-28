begin;

-- ADR 0089: o catálogo estadual de emendas é consultado todo dia, mas publica
-- pouco; fora do ar é aviso por até 7 dias (24 h + 144 h) sem coleta
-- bem-sucedida. O PNCP (consulta-contratacoes) já tem 24 h + 24 h = 48 h.
update source.source_endpoints as endpoint
set freshness_policy_kind = 'scheduled',
    freshness_expected_hours = 24,
    freshness_grace_hours = 144,
    freshness_policy_note =
      'Consulta diária; fonte fora do ar é aviso por até 7 dias sem coleta bem-sucedida (ADR 0089).',
    freshness_policy_version = 'source-freshness/1.1.0'
from source.data_sources as source
where source.id = endpoint.data_source_id
  and source.slug = 'bahia-open-data'
  and endpoint.slug = 'state-parliamentary-amendments';

commit;
