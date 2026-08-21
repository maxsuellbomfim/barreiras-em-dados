begin;

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
  assisted_summary text,
  assisted_provider text,
  approved_at timestamptz,
  artifact_sha256 text,
  extractor_version text,
  review_mode text,
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
  with latest_reviews as materialized (
    select distinct on (review.target_id)
      review.target_id,
      review.decision,
      review.reviewed_at,
      review.reviewer_subject,
      review.checklist
    from editorial.editorial_reviews as review
    where review.target_type = 'raw.extraction_results'
    order by review.target_id, review.created_at desc, review.id desc
  ),
  approved_results as materialized (
    select
      result.*,
      review.reviewed_at,
      review.reviewer_subject,
      review.checklist as review_checklist
    from raw.extraction_results as result
    join latest_reviews as review on review.target_id = result.id
    where review.decision = 'approved'
      and result.candidate_type in ('nomeacao', 'exoneracao')
  ),
  reviewed_assists as materialized (
    select distinct on (result.id)
      result.id as act_id,
      enrichment.result_payload ->> 'summary' as summary,
      enrichment.result_payload ->> 'provider' as provider
    from approved_results as result
    join raw.extraction_results as enrichment
      on enrichment.supersedes_id = result.id
     and enrichment.candidate_type = 'assisted_enrichment'
     and enrichment.created_at <= result.reviewed_at
     and enrichment.result_payload ->> 'summary' is not null
    order by result.id, enrichment.created_at desc, enrichment.id desc
  ),
  latest_gazettes as materialized (
    select distinct on (record.source_record_key)
      record.source_record_key,
      (record.payload ->> 'date')::date as published_date,
      record.payload ->> 'url' as source_url
    from raw.raw_records as record
    where record.record_type = 'querido_diario_gazette'
      and record.source_record_key is not null
    order by record.source_record_key, record.collected_at desc
  ),
  deduped as (
    select distinct on (
      result.candidate_type,
      coalesce(
        result.review_checklist #>> '{verification,fields,act_number,value}',
        result.result_payload #>> '{fields,act_number,value}',
        result.id::text
      ),
      coalesce(
        result.review_checklist #>> '{verification,fields,act_date,value}',
        result.result_payload #>> '{fields,act_date,value}',
        ''
      ),
      coalesce(
        result.review_checklist #>> '{verification,fields,person_name,value}',
        result.result_payload #>> '{fields,person_name,value}',
        ''
      )
    )
      result.id as act_id,
      result.candidate_type as act_type,
      coalesce(
        result.review_checklist #>> '{verification,fields,person_name,value}',
        result.result_payload #>> '{fields,person_name,value}'
      ) as person_name,
      coalesce(
        result.review_checklist #>> '{verification,fields,position,value}',
        result.result_payload #>> '{fields,position,value}'
      ) as position_title,
      coalesce(
        result.review_checklist #>> '{verification,fields,position_symbol,value}',
        result.result_payload #>> '{fields,position_symbol,value}'
      ) as position_symbol,
      coalesce(
        result.review_checklist #>> '{verification,fields,organization,value}',
        result.result_payload #>> '{fields,organization,value}'
      ) as organization,
      coalesce(
        gazette.published_date,
        case
          when coalesce(
            result.review_checklist #>> '{verification,fields,act_date,value}',
            result.result_payload #>> '{fields,act_date,value}'
          ) ~ '^\d{4}-\d{2}-\d{2}$'
          then coalesce(
            result.review_checklist #>> '{verification,fields,act_date,value}',
            result.result_payload #>> '{fields,act_date,value}'
          )::date
        end
      ) as gazette_date,
      coalesce(
        gazette.source_url,
        case
          when artifact.metadata ->> 'schema_name' = 'gazette-direct-edition'
          then artifact.source_url
        end
      ) as gazette_url,
      result.result_payload ->> 'excerpt' as excerpt,
      assist.summary as assisted_summary,
      assist.provider as assisted_provider,
      result.reviewed_at as approved_at,
      artifact.sha256 as artifact_sha256,
      result.extractor_version,
      case
        when result.reviewer_subject like 'automated:%' then 'automated'
        else 'human'
      end as review_mode
    from approved_results as result
    join raw.extraction_jobs as job on job.id = result.extraction_job_id
    join raw.raw_artifacts as artifact on artifact.id = job.raw_artifact_id
    left join reviewed_assists as assist on assist.act_id = result.id
    left join latest_gazettes as gazette
      on gazette.source_record_key = artifact.metadata ->> 'source_record_key'
    order by
      result.candidate_type,
      coalesce(
        result.review_checklist #>> '{verification,fields,act_number,value}',
        result.result_payload #>> '{fields,act_number,value}',
        result.id::text
      ),
      coalesce(
        result.review_checklist #>> '{verification,fields,act_date,value}',
        result.result_payload #>> '{fields,act_date,value}',
        ''
      ),
      coalesce(
        result.review_checklist #>> '{verification,fields,person_name,value}',
        result.result_payload #>> '{fields,person_name,value}',
        ''
      ),
      result.reviewed_at desc
  )
  select
    deduped.act_id,
    deduped.act_type,
    deduped.person_name,
    deduped.position_title,
    deduped.position_symbol,
    deduped.organization,
    deduped.gazette_date,
    deduped.gazette_url,
    deduped.excerpt,
    deduped.assisted_summary,
    deduped.assisted_provider,
    deduped.approved_at,
    deduped.artifact_sha256,
    deduped.extractor_version,
    deduped.review_mode,
    'approved-gazette-acts/1.6.0'::text
  from deduped
  order by deduped.approved_at desc, deduped.act_id
  limit page_size;
end;
$function$;

revoke all on function api.get_approved_gazette_acts(integer) from public;
grant execute on function api.get_approved_gazette_acts(integer)
  to anon, authenticated;

comment on function api.get_approved_gazette_acts(integer) is
  'Somente atos de pessoal aprovados, um por (tipo, portaria, data, pessoa), com revisão e evidência resolvidas em conjunto.';

commit;
