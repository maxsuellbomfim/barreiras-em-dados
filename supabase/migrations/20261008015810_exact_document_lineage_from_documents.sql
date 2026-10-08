begin;

-- Mesmo resultado, caminho inverso: a linhagem exata partia de todos os
-- registros brutos com source_record_key (todas as fontes) para procurar
-- documentos; passa a partir dos artefatos de documento (poucos milhares) e
-- subir pelo pai até o registro de origem, usando os índices existentes
-- (raw_artifacts_municipal_document_identity_idx e
-- raw_records_artifact_source_key_idx). Medido em produção em 08/10/2026:
-- 2.215 pares idênticos nos dois sentidos, 1,65 s -> 16 ms. Seis funções
-- públicas de Finanças chamam esta função; sob visitas simultâneas elas
-- passavam do limite de 3 s do papel anon.
create or replace function finance.get_exact_document_lineage_pairs()
returns table (origin_raw_record_id uuid, document_artifact_id uuid)
language sql
stable
security definer
set search_path = ''
as $function$
  with municipal_lineage as materialized (
    select
      origin.id as origin_raw_record_id,
      document.id as document_artifact_id
    from raw.raw_artifacts as document
    join raw.raw_records as origin
      on origin.raw_artifact_id = document.parent_artifact_id
     and origin.source_record_key = document.metadata ->> 'source_record_key'
     and origin.payload ->> 'url' = document.source_url
    where document.artifact_kind = 'document'
      and document.metadata ->> 'schema_name' = 'municipal-transparency-document'
      and document.parent_artifact_id is not null
  ),
  tcm_ba_lineage as materialized (
    select
      origin.id as origin_raw_record_id,
      document.id as document_artifact_id
    from raw.raw_artifacts as document
    join raw.raw_artifacts as prepare
      on prepare.id = document.parent_artifact_id
     and prepare.artifact_kind = 'document'
     and prepare.metadata ->> 'schema_name' = 'tcm-ba-document-download-prepare'
     and prepare.metadata ->> 'document_role' = 'download-prepare'
     and prepare.metadata ->> 'source_record_key'
       = document.metadata ->> 'source_record_key'
     and prepare.source_url
       = 'https://e.tcm.ba.gov.br/epp/ConsultaPublica/listView.seam'
    join raw.raw_records as origin
      on origin.raw_artifact_id = prepare.parent_artifact_id
     and origin.source_record_key = document.metadata ->> 'source_record_key'
    where document.artifact_kind = 'document'
      and document.metadata ->> 'schema_name' = 'tcm-ba-monthly-document'
      and document.metadata ->> 'document_role' = 'pdf'
      and document.source_url
        = 'https://e.tcm.ba.gov.br/epp/PdfReadOnly/downloadDocumento.seam'
      and origin.record_type = 'tcm_ba_monthly_document'
      and left(origin.payload ->> 'category', 8) in ('PCMGE015', 'PCMGE016')
      and origin.payload ->> 'unit' = 'Prefeitura Municipal de BARREIRAS'
      and origin.payload ->> 'competence' ~ '^(0[1-9]|1[0-2])/[0-9]{4}$'
      and origin.payload ->> 'source_url'
        = 'https://e.tcm.ba.gov.br/epp/ConsultaPublica/listView.seam'
  ),
  direct_lineage as materialized (
    select * from municipal_lineage
    union
    select * from tcm_ba_lineage
  ),
  current_corrections as (
    select distinct on (
      lineage.document_artifact_id,
      lineage.normalized_origin_raw_record_id
    )
      lineage.document_artifact_id,
      lineage.normalized_origin_raw_record_id,
      lineage.effective_raw_record_id
    from finance.document_lineage_versions as lineage
    where lineage.lineage_status = 'corrected'
    order by
      lineage.document_artifact_id,
      lineage.normalized_origin_raw_record_id,
      lineage.version desc,
      lineage.created_at desc,
      lineage.id desc
  ),
  corrected_lineage as (
    select
      correction.normalized_origin_raw_record_id as origin_raw_record_id,
      correction.document_artifact_id
    from current_corrections as correction
    join direct_lineage as direct
      on direct.origin_raw_record_id = correction.effective_raw_record_id
     and direct.document_artifact_id = correction.document_artifact_id
  )
  select direct.origin_raw_record_id, direct.document_artifact_id
  from direct_lineage as direct
  union
  select corrected.origin_raw_record_id, corrected.document_artifact_id
  from corrected_lineage as corrected;
$function$;

commit;
