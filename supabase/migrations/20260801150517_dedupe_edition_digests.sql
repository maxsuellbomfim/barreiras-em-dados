-- Resumos por edição agora também cobrem as edições históricas do Querido
-- Diário. A mesma edição pode existir nas duas fontes; a projeção pública
-- entrega um resumo por número de edição (o publicado mais recentemente).

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
  select *
  from (
    select distinct on ((result.result_payload ->> 'edition')::int)
      result.id,
      (result.result_payload ->> 'edition')::int as digest_edition,
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
    order by
      (result.result_payload ->> 'edition')::int desc,
      latest.reviewed_at desc
  ) as deduped
  limit page_size;
end;
$function$;

revoke all on function api.get_edition_digests(integer) from public;
grant execute on function api.get_edition_digests(integer)
  to anon, authenticated;

comment on function api.get_edition_digests(integer) is
  'Resumos por edição (fonte direta e QD), um por número de edição.';
