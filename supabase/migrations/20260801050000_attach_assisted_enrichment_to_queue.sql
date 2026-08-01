-- Fila 1.3.0: cada candidato carrega a última sugestão assistida (ADR 0011)
-- e as linhas de enriquecimento não aparecem como cartões próprios.

-- A assinatura de retorno muda (nova coluna), então a função é recriada e
-- as permissões são reaplicadas explicitamente.
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
  select
    result.id,
    result.candidate_type,
    result.extractor_version,
    result.validation_status,
    result.created_at,
    result.result_payload,
    assisted.result_payload,
    artifact.sha256,
    'extraction-review-queue/1.3.0'::text
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
  where result.validation_status = 'needs_review'
    and result.candidate_type <> 'assisted_enrichment'
    and coalesce(api.latest_review_decision(result.id), 'none')
      not in ('approved', 'rejected')
  order by result.created_at asc, result.id asc
  limit page_size;
end;
$function$;

revoke all on function api.get_extraction_review_queue(integer)
  from public, anon;
grant execute on function api.get_extraction_review_queue(integer)
  to authenticated;
