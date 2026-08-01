-- Atos aprovados 1.2.0: o resumo assistido em linguagem simples acompanha o
-- ato publicado, mas SOMENTE quando a sugestão já existia no momento da
-- aprovação — ou seja, quando a pessoa revisora a viu ao decidir. O rótulo
-- de origem (provedor) sai junto, por transparência (ADR 0011).

drop function if exists api.get_approved_gazette_acts(integer);

create function api.get_approved_gazette_acts(
  page_size integer default 50
)
returns table (
  act_id uuid,
  act_type text,
  person_name text,
  position_title text,
  position_symbol text,
  organization text,
  gazette_date date,
  gazette_url text,
  excerpt text,
  assisted_summary text,
  assisted_provider text,
  approved_at timestamptz,
  artifact_sha256 text,
  extractor_version text,
  methodology_version text
)
language plpgsql
stable
security definer
set search_path = ''
as $function$
begin
  if page_size < 1 or page_size > 200 then
    raise exception 'page_size deve estar entre 1 e 200'
      using errcode = '22023';
  end if;

  return query
  select
    result.id,
    result.candidate_type,
    result.result_payload #>> '{fields,person_name,value}',
    result.result_payload #>> '{fields,position,value}',
    result.result_payload #>> '{fields,position_symbol,value}',
    result.result_payload #>> '{fields,organization,value}',
    gazette.published_date,
    gazette.source_url,
    result.result_payload ->> 'excerpt',
    reviewed_assist.summary,
    reviewed_assist.provider,
    latest.reviewed_at,
    artifact.sha256,
    result.extractor_version,
    'approved-gazette-acts/1.2.0'::text
  from raw.extraction_results as result
  join raw.extraction_jobs as job
    on job.id = result.extraction_job_id
  join raw.raw_artifacts as artifact
    on artifact.id = job.raw_artifact_id
  join lateral (
    select review.decision, review.reviewed_at
    from editorial.editorial_reviews as review
    where review.target_type = 'raw.extraction_results'
      and review.target_id = result.id
    order by review.created_at desc, review.id desc
    limit 1
  ) as latest on true
  left join lateral (
    select
      enrichment.result_payload ->> 'summary' as summary,
      enrichment.result_payload ->> 'provider' as provider
    from raw.extraction_results as enrichment
    where enrichment.supersedes_id = result.id
      and enrichment.candidate_type = 'assisted_enrichment'
      and enrichment.created_at <= latest.reviewed_at
      and enrichment.result_payload ->> 'summary' is not null
    order by enrichment.created_at desc, enrichment.id desc
    limit 1
  ) as reviewed_assist on true
  left join lateral (
    select
      (record.payload ->> 'date')::date as published_date,
      record.payload ->> 'url' as source_url
    from raw.raw_records as record
    where record.record_type = 'querido_diario_gazette'
      and record.source_record_key = artifact.metadata ->> 'source_record_key'
    order by record.collected_at desc
    limit 1
  ) as gazette on true
  where latest.decision = 'approved'
  order by latest.reviewed_at desc, result.id
  limit page_size;
end;
$function$;

revoke all on function api.get_approved_gazette_acts(integer) from public;
grant execute on function api.get_approved_gazette_acts(integer)
  to anon, authenticated;

comment on function api.get_approved_gazette_acts(integer) is
  'Atos aprovados com resumo assistido revisado, quando existente.';
