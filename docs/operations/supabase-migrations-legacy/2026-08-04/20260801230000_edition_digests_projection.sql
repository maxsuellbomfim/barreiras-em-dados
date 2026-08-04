-- ADR 0013: resumo por edição ancorado no texto oficial.
-- A projeção pública entrega somente resumos aprovados (a publicação
-- automática registra a aprovação com o verificador de âncoras); a fila de
-- revisão humana deixa de exibir resumos de edição como cartões próprios.

create or replace function api.get_edition_digests(
  page_size integer default 20
)
returns table (
  digest_id uuid,
  edition integer,
  edition_year integer,
  items jsonb,
  stats jsonb,
  gazette_url text,
  artifact_sha256 text,
  published_at timestamptz,
  review_mode text,
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

  return query
  select
    result.id,
    (result.result_payload ->> 'edition')::int,
    (result.result_payload ->> 'year')::int,
    result.result_payload -> 'items',
    result.result_payload -> 'stats',
    artifact.source_url,
    artifact.sha256,
    latest.reviewed_at,
    case
      when latest.reviewer_subject like 'automated:%' then 'automated'
      else 'human'
    end,
    'edition-digests/1.0.0'::text
  from raw.extraction_results as result
  join raw.extraction_jobs as job
    on job.id = result.extraction_job_id
  join raw.raw_artifacts as artifact
    on artifact.id = job.raw_artifact_id
  join lateral (
    select review.decision, review.reviewed_at, review.reviewer_subject
    from editorial.editorial_reviews as review
    where review.target_type = 'raw.extraction_results'
      and review.target_id = result.id
    order by review.created_at desc, review.id desc
    limit 1
  ) as latest on true
  where result.candidate_type = 'edition_digest'
    and latest.decision = 'approved'
  order by (result.result_payload ->> 'edition')::int desc
  limit page_size;
end;
$function$;

revoke all on function api.get_edition_digests(integer) from public;
grant execute on function api.get_edition_digests(integer)
  to anon, authenticated;

comment on function api.get_edition_digests(integer) is
  'Resumos por edição com itens ancorados no texto oficial (ADR 0013).';

-- Fila 1.4.0: resumos de edição não são cartões de revisão individual; a
-- reversão deles vive no histórico, como qualquer publicação automática.

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
    'extraction-review-queue/1.4.0'::text
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
    and result.candidate_type <> 'edition_digest'
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

comment on function api.get_extraction_review_queue(integer) is
  'Fila interna de candidatos needs_review sem decisão final; sem resumos '
  'de edição, que são revertíveis pelo histórico.';
