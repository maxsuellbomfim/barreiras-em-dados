begin;

with
  corrections (slug, name, description) as (
    values
      (
        'querido-diario',
        'Querido Diário',
        'Agregador de diários oficiais municipais mantido pela Open Knowledge Brasil.'
      ),
      (
        'prefeitura-barreiras-transparencia',
        'Portal da Transparência da Prefeitura de Barreiras',
        'API oficial de contratos, processos, documentos fiscais, RH e prestação de contas.'
      ),
      (
        'camara-barreiras-transparencia',
        'Portal da Transparência da Câmara Municipal de Barreiras',
        'API oficial de contratos, atos, documentos, RH e atividade legislativa.'
      )
  ),
  prior as materialized (
    select
      data_source.id,
      data_source.slug,
      data_source.name,
      data_source.description
    from source.data_sources as data_source
    join corrections
      on corrections.slug = data_source.slug
  ),
  corrected as (
    update source.data_sources as data_source
    set
      name = corrections.name,
      description = corrections.description
    from corrections
    where data_source.slug = corrections.slug
      and (
        data_source.name,
        data_source.description
      ) is distinct from (
        corrections.name,
        corrections.description
      )
    returning data_source.id, data_source.slug, data_source.name,
      data_source.description
  )
insert into audit.audit_events (
  actor_type,
  actor_subject,
  action,
  target_type,
  target_id,
  before_state,
  after_state,
  metadata
)
select
  'system',
  'migration:repair_source_catalog_utf8',
  'source_catalog.encoding_corrected',
  'source.data_sources',
  corrected.id::text,
  jsonb_build_object(
    'slug', prior.slug,
    'name', prior.name,
    'description', prior.description
  ),
  jsonb_build_object(
    'slug', corrected.slug,
    'name', corrected.name,
    'description', corrected.description
  ),
  jsonb_build_object(
    'reason', 'repair_utf8_mojibake',
    'review', 'visual_data_quality_review'
  )
from corrected
join prior
  on prior.id = corrected.id;

commit;
