-- Reconhece o PDF analítico de despesa do SIGA/TCM-BA como segunda fonte
-- oficial, sem reclassificá-lo como documento do portal municipal.

create or replace function finance.has_tcm_ba_document_lineage(
  origin_record_id uuid,
  document_artifact_id uuid
)
returns boolean
language sql
stable
security definer
set search_path = ''
as $function$
  select exists (
    select 1
    from raw.raw_records as origin
    join raw.raw_artifacts as catalog
      on catalog.id = origin.raw_artifact_id
    join raw.raw_artifacts as prepare
      on prepare.parent_artifact_id = catalog.id
     and prepare.artifact_kind = 'document'
     and prepare.metadata ->> 'schema_name'
       = 'tcm-ba-document-download-prepare'
     and prepare.metadata ->> 'document_role' = 'download-prepare'
     and prepare.metadata ->> 'source_record_key'
       = origin.source_record_key
     and prepare.source_url
       = 'https://e.tcm.ba.gov.br/epp/ConsultaPublica/listView.seam'
    join raw.raw_artifacts as document
      on document.id = $2
     and document.parent_artifact_id = prepare.id
     and document.artifact_kind = 'document'
     and document.metadata ->> 'schema_name'
       = 'tcm-ba-monthly-document'
     and document.metadata ->> 'document_role' = 'pdf'
     and document.metadata ->> 'source_record_key'
       = origin.source_record_key
     and document.source_url
       = 'https://e.tcm.ba.gov.br/epp/PdfReadOnly/downloadDocumento.seam'
    where origin.id = $1
      and origin.record_type = 'tcm_ba_monthly_document'
      and origin.source_record_key is not null
      and origin.payload ->> 'category' like 'PCMGE015%'
      and origin.payload ->> 'unit'
        = 'Prefeitura Municipal de BARREIRAS'
      and origin.payload ->> 'competence'
        ~ '^(0[1-9]|1[0-2])/[0-9]{4}$'
      and origin.payload ->> 'source_url'
        = 'https://e.tcm.ba.gov.br/epp/ConsultaPublica/listView.seam'
  );
$function$;

create or replace function finance.resolve_document_origin(
  origin_record_id uuid,
  document_artifact_id uuid
)
returns uuid
language sql
stable
security definer
set search_path = ''
as $function$
  select case
    when finance.has_direct_document_lineage($1, $2)
      or finance.has_tcm_ba_document_lineage($1, $2)
      then $1
    else (
      select lineage.effective_raw_record_id
      from finance.document_lineage_versions as lineage
      where lineage.document_artifact_id = $2
        and lineage.normalized_origin_raw_record_id = $1
        and lineage.lineage_status = 'corrected'
        and (
          finance.has_direct_document_lineage(
            lineage.effective_raw_record_id,
            $2
          )
          or finance.has_tcm_ba_document_lineage(
            lineage.effective_raw_record_id,
            $2
          )
        )
      order by lineage.version desc, lineage.created_at desc, lineage.id desc
      limit 1
    )
  end;
$function$;

create or replace function finance.get_exact_document_lineage_pairs()
returns table (
  origin_raw_record_id uuid,
  document_artifact_id uuid
)
language sql
stable
security definer
set search_path = ''
as $function$
  with municipal_lineage as materialized (
    select
      origin.id as origin_raw_record_id,
      document.id as document_artifact_id
    from raw.raw_records as origin
    join raw.raw_artifacts as source_artifact
      on source_artifact.id = origin.raw_artifact_id
    join raw.raw_artifacts as document
      on document.parent_artifact_id = source_artifact.id
     and document.artifact_kind = 'document'
     and document.metadata ->> 'schema_name'
       = 'municipal-transparency-document'
     and document.metadata ->> 'source_record_key'
       = origin.source_record_key
     and document.source_url = origin.payload ->> 'url'
    where origin.source_record_key is not null
  ),
  tcm_ba_lineage as materialized (
    select
      origin.id as origin_raw_record_id,
      document.id as document_artifact_id
    from raw.raw_records as origin
    join raw.raw_artifacts as catalog
      on catalog.id = origin.raw_artifact_id
    join raw.raw_artifacts as prepare
      on prepare.parent_artifact_id = catalog.id
     and prepare.artifact_kind = 'document'
     and prepare.metadata ->> 'schema_name'
       = 'tcm-ba-document-download-prepare'
     and prepare.metadata ->> 'document_role' = 'download-prepare'
     and prepare.metadata ->> 'source_record_key'
       = origin.source_record_key
     and prepare.source_url
       = 'https://e.tcm.ba.gov.br/epp/ConsultaPublica/listView.seam'
    join raw.raw_artifacts as document
      on document.parent_artifact_id = prepare.id
     and document.artifact_kind = 'document'
     and document.metadata ->> 'schema_name'
       = 'tcm-ba-monthly-document'
     and document.metadata ->> 'document_role' = 'pdf'
     and document.metadata ->> 'source_record_key'
       = origin.source_record_key
     and document.source_url
       = 'https://e.tcm.ba.gov.br/epp/PdfReadOnly/downloadDocumento.seam'
    where origin.record_type = 'tcm_ba_monthly_document'
      and origin.source_record_key is not null
      and origin.payload ->> 'category' like 'PCMGE015%'
      and origin.payload ->> 'unit'
        = 'Prefeitura Municipal de BARREIRAS'
      and origin.payload ->> 'competence'
        ~ '^(0[1-9]|1[0-2])/[0-9]{4}$'
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

revoke all on function finance.has_tcm_ba_document_lineage(uuid, uuid)
  from public, anon, authenticated;
revoke all on function finance.resolve_document_origin(uuid, uuid)
  from public, anon, authenticated;
revoke all on function finance.get_exact_document_lineage_pairs()
  from public, anon, authenticated;

comment on function finance.has_tcm_ba_document_lineage(uuid, uuid) is
  'Confere registro PCMGE015, preparação e PDF exato do SIGA/TCM-BA.';
