begin;

-- Fontes com coleta agendada ainda marcadas como "manual" (sem prazo) ficavam
-- "não monitoradas" no painel: se a coleta parasse, nada acusava. Cadência
-- conferida nas execuções gravadas de 10/09 a 19/10/2026. Fontes externas
-- seguem o ADR 0089 (fora do ar é aviso dentro do prazo, depois falha).
update source.source_endpoints as endpoint
set freshness_policy_kind = 'scheduled',
    freshness_expected_hours = policy.expected_hours,
    freshness_grace_hours = policy.grace_hours,
    freshness_policy_note = policy.note,
    freshness_policy_version = 'source-freshness/1.2.0'
from source.data_sources as source,
  (values
    ('cgu-portal-transparencia', 'federal-amendments-open-data', 24, 48,
      'Rotina diária; fonte fora do ar é aviso por até 72 horas sem coleta válida (ADR 0089).'),
    ('cgu-portal-transparencia', 'federal-amendment-documents-open-data', 24, 48,
      'Rotina diária; fonte fora do ar é aviso por até 72 horas sem coleta válida (ADR 0089).'),
    ('siconfi-barreiras', 'dca', 24, 48,
      'Rotina diária; fonte fora do ar é aviso por até 72 horas sem coleta válida (ADR 0089).'),
    ('siconfi-barreiras', 'rgf-anexo-02', 24, 48,
      'Rotina diária; fonte fora do ar é aviso por até 72 horas sem coleta válida (ADR 0089).'),
    ('bahia-open-data', 'state-special-transfers', 24, 144,
      'Consulta diária; fonte fora do ar é aviso por até 7 dias sem coleta bem-sucedida (ADR 0089).'),
    ('prefeitura-barreiras-despesas-webrun', 'webrun-empenhos', 408, 72,
      'Coleta nos dias 3 e 20 de cada mês; alerta após 20 dias sem coleta válida.'),
    ('prefeitura-barreiras-despesas-webrun', 'webrun-liquidacoes', 408, 72,
      'Coleta nos dias 3 e 20 de cada mês; alerta após 20 dias sem coleta válida.'),
    ('prefeitura-barreiras-despesas-webrun', 'webrun-pagamentos', 408, 72,
      'Coleta nos dias 3 e 20 de cada mês; alerta após 20 dias sem coleta válida.'),
    ('tcm-ba', 'prestacoes-contas-mensais', 24, 120,
      'Executor local (Windows) diário; depende da máquina ligada; alerta após 6 dias sem coleta válida.'),
    ('fns-farmacia-popular', 'payment', 24, 120,
      'Executor local (Windows) diário; depende da máquina ligada; alerta após 6 dias sem coleta válida.'),
    ('receita-federal-cnpj', 'dados-abertos-cnpj', 168, 96,
      'Executor local (Windows) semanal; alerta após 11 dias sem coleta válida.')
  ) as policy(source_slug, endpoint_slug, expected_hours, grace_hours, note)
where source.id = endpoint.data_source_id
  and source.slug = policy.source_slug
  and endpoint.slug = policy.endpoint_slug
  and endpoint.freshness_policy_kind = 'manual';

commit;
