-- Índices mínimos para a fila de aliases. A consulta reúne leis,
-- indicações, vereadores e votos históricos; sem o recorte por tipo o
-- worker podia ficar vários minutos em um acervo crescente.

create index if not exists raw_records_alias_assist_type_idx
  on raw.raw_records (record_type, collected_at desc)
  where record_type in (
    'municipal_transparency_leis',
    'municipal_transparency_indicacoes',
    'cm_barreiras_vereador',
    'tse_votacao_barreiras'
  );

create index if not exists raw_records_alias_assist_author_idx
  on raw.raw_records (
    (nullif(btrim(coalesce(
      payload ->> 'autoria',
      payload ->> 'autor',
      payload ->> 'author'
    )), ''))
  )
  where record_type in (
    'municipal_transparency_leis',
    'municipal_transparency_indicacoes'
  );
