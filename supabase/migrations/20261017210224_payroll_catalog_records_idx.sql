begin;

-- Cobertura da folha (/financas): o catálogo de "Relação de Servidores" era
-- lido percorrendo os 2,4 mil artefatos do endpoint e buscando registros por
-- artefato (≈10 mil páginas frias, 1,8 s com cache quente e até 6,5 s frio em
-- 17/10/2026). Índice parcial de cobertura: varredura só-índice dos 1,2 mil
-- registros do catálogo (21 ms). Sem mudança de resultado.
create index if not exists raw_records_payroll_catalog_idx
  on raw.raw_records (source_record_key, collected_at desc, id desc)
  include (raw_artifact_id, payload)
  where record_type = 'municipal_transparency_servidores';

commit;
