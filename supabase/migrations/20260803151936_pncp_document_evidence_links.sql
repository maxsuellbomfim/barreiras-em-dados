-- O Storage de artefatos continua privado. Este wrapper somente acrescenta,
-- quando existir, o documento filho oficial associado ao registro bruto.

alter function api.get_pncp_execution_summary(text)
  rename to get_pncp_execution_summary_base;

create function api.get_pncp_execution_summary(control_number_filter text)
returns jsonb
language sql
stable
security definer
set search_path = ''
as $function$
  with base as (
    select api.get_pncp_execution_summary_base(control_number_filter) as summary
  ),
  enriched as (
    select coalesce(
      jsonb_agg(
        item.item || jsonb_build_object(
          'document_source_url', child.source_url,
          'document_sha256', child.sha256,
          'document_retrieved_at', child.retrieved_at,
          'document_preserved', child.id is not null
        ) order by item.ordinality
      ),
      '[]'::jsonb
    ) as entries
    from base
    cross join lateral jsonb_array_elements(
      coalesce(base.summary -> 'evidence', '[]'::jsonb)
    ) with ordinality as item(item, ordinality)
    left join raw.raw_records as record
      on record.id = nullif(item.item ->> 'raw_record_id', '')::uuid
    left join raw.raw_artifacts as artifact
      on artifact.id = record.raw_artifact_id
    left join lateral (
      select document.id, document.source_url, document.sha256, document.retrieved_at
      from raw.raw_artifacts as document
      where document.parent_artifact_id = artifact.id
        and document.artifact_kind = 'document'
        and document.source_url ~ '^https://'
      order by document.created_at desc, document.id desc
      limit 1
    ) as child on true
  )
  select base.summary || jsonb_build_object(
    'methodology_version', 'pncp-execution-links/1.2.0',
    'evidence', enriched.entries
  )
  from base cross join enriched;
$function$;

revoke all on function api.get_pncp_execution_summary_base(text)
  from public, anon, authenticated;
revoke all on function api.get_pncp_execution_summary(text)
  from public, anon, authenticated;

comment on function api.get_pncp_execution_summary(text) is
  'Resumo PNCP com documento oficial filho quando preservado; o Storage bruto permanece privado.';
