-- Etapa 1C, fatia 3: projeção pública somente de atos aprovados.
-- A RPC expõe apenas candidatos com decisão editorial 'approved', com o
-- trecho de sustentação, a data e o link do documento oficial e o hash do
-- artefato — nada de pendentes, rejeitados ou esquema interno.

create or replace function api.get_approved_gazette_acts(
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
    review.reviewed_at,
    artifact.sha256,
    result.extractor_version,
    'approved-gazette-acts/1.0.0'::text
  from raw.extraction_results as result
  join editorial.editorial_reviews as review
    on review.target_type = 'raw.extraction_results'
    and review.target_id = result.id
    and review.decision = 'approved'
  join raw.extraction_jobs as job
    on job.id = result.extraction_job_id
  join raw.raw_artifacts as artifact
    on artifact.id = job.raw_artifact_id
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
  order by review.reviewed_at desc, result.id
  limit page_size;
end;
$function$;

revoke all on function api.get_approved_gazette_acts(integer) from public;
grant execute on function api.get_approved_gazette_acts(integer)
  to anon, authenticated;

comment on function api.get_approved_gazette_acts(integer) is
  'Atos de pessoal aprovados por revisão humana, com evidência verificável.';
