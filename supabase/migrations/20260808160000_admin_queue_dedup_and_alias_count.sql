-- Corrige duas projeções administrativas sem apagar o acervo bruto:
-- (1) a fila de atos deduplicava só dentro do mesmo artefato;
-- (2) a contagem de aliases era multiplicada pelo cross join de candidatos.

drop function if exists api.get_extraction_review_queue(integer);

create function api.get_extraction_review_queue(
  page_size integer default 20
)
returns table (
  result_id uuid,
  candidate_type text,
  extractor_version text,
  validation_status text,
  result_created_at timestamptz,
  result_payload jsonb,
  assisted_payload jsonb,
  artifact_sha256 text,
  artifact_source_url text,
  queue_reason text,
  methodology_version text
)
language plpgsql
stable
security definer
set search_path = ''
as $function$
begin
  if page_size < 1 or page_size > 100 then
    raise exception 'page_size deve estar entre 1 e 100'
      using errcode = '22023';
  end if;
  if not api.is_active_reviewer() then
    raise exception 'acesso restrito a revisores ativos'
      using errcode = '42501';
  end if;

  return query
  with candidate_rows as materialized (
    select
      result.id,
      result.candidate_type,
      result.extractor_version,
      result.validation_status,
      result.created_at,
      result.result_payload,
      assisted.result_payload as assisted_payload,
      artifact.sha256 as artifact_sha256,
      artifact.source_url as artifact_source_url,
      coalesce(
        result.result_payload #>> '{fields,act_number,value}',
        result.id::text
      ) as act_number_key,
      coalesce(
        result.result_payload #>> '{fields,act_date,value}',
        ''
      ) as act_date_key,
      latest.decision as latest_decision
    from raw.extraction_results as result
    join raw.extraction_jobs as job
      on job.id = result.extraction_job_id
    join raw.raw_artifacts as artifact
      on artifact.id = job.raw_artifact_id
    left join lateral (
      select enrichment.result_payload
      from raw.extraction_results as enrichment
      where enrichment.supersedes_id = result.id
        and enrichment.candidate_type = 'assisted_enrichment'
      order by enrichment.created_at desc, enrichment.id desc
      limit 1
    ) as assisted on true
    left join lateral (
      select review.decision
      from editorial.editorial_reviews as review
      where review.target_type = 'raw.extraction_results'
        and review.target_id = result.id
      order by review.created_at desc, review.id desc
      limit 1
    ) as latest on true
    where result.validation_status = 'needs_review'
      and result.candidate_type <> 'assisted_enrichment'
      and result.candidate_type <> 'edition_digest'
  ),
  deduped as (
    select distinct on (
      candidate.candidate_type,
      candidate.act_number_key,
      candidate.act_date_key
    )
      candidate.*
    from candidate_rows as candidate
    where (
      candidate.latest_decision is null
      or candidate.latest_decision = 'withdrawn'
    )
      and not exists (
        select 1
        from candidate_rows as resolved
        where resolved.candidate_type = candidate.candidate_type
          and resolved.act_number_key = candidate.act_number_key
          and resolved.act_date_key = candidate.act_date_key
          and resolved.latest_decision in ('approved', 'rejected')
      )
    -- Prefere a versão mais recente do parser quando o mesmo ato foi
    -- preservado novamente em outro artefato ou edição.
    order by
      candidate.candidate_type,
      candidate.act_number_key,
      candidate.act_date_key,
      candidate.created_at desc,
      candidate.id desc
  )
  select
    deduped.id,
    deduped.candidate_type,
    deduped.extractor_version,
    deduped.validation_status,
    deduped.created_at,
    deduped.result_payload,
    deduped.assisted_payload,
    deduped.artifact_sha256,
    deduped.artifact_source_url,
    case
      when nullif(btrim(deduped.result_payload ->> 'excerpt'), '') is null
        then 'missing_source_excerpt'::text
      when deduped.assisted_payload is null
        then 'ai_assistance_pending'::text
      else 'needs_human_verification'::text
    end,
    'extraction-review-queue/1.7.0'::text
  from deduped
  order by deduped.created_at, deduped.id
  limit page_size;
end;
$function$;

revoke all on function api.get_extraction_review_queue(integer)
  from public, anon;
grant execute on function api.get_extraction_review_queue(integer)
  to authenticated;

comment on function api.get_extraction_review_queue(integer) is
  'Fila interna deduplicada por ato, com sugestão assistida e motivo; '
  'não publica nem decide candidatos.';
