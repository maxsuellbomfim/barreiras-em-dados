-- Projeta os metadados estruturados do catálogo oficial sem substituir o
-- resumo assistido por IA. O catálogo é a fonte da edição, título, resumo e data.

drop function if exists api.get_edition_digests(integer);

create function api.get_edition_digests(
  page_size integer default 20
)
returns table (
  digest_id uuid,
  edition integer,
  edition_year integer,
  edition_date date,
  official_title text,
  official_summary text,
  official_date date,
  official_publication_url text,
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
      (result.result_payload ->> 'year')::int as digest_year,
      coalesce(catalog.published_on, direct_date.digest_date) as digest_date,
      catalog.title,
      catalog.summary,
      catalog.published_on,
      catalog.publication_url,
      result.result_payload -> 'items',
      result.result_payload -> 'stats',
      artifact.source_url,
      artifact.sha256,
      latest.reviewed_at,
      case
        when latest.reviewer_subject like 'automated:%' then 'automated'
        else 'human'
      end,
      'edition-digests/1.2.0'::text
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
    left join lateral (
      select
        case
          when record.payload ->> 'date' ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
          then (record.payload ->> 'date')::date
        end as published_on,
        record.payload ->> 'title' as title,
        record.payload ->> 'summary' as summary,
        record.payload ->> 'publication_url' as publication_url
      from raw.raw_records as record
      where record.record_type = 'barreiras_diario_publication'
        and (record.payload ->> 'edition')::int =
            (result.result_payload ->> 'edition')::int
        and (record.payload ->> 'date') like
            ((result.result_payload ->> 'year') || '-%')
      order by record.collected_at desc, record.id desc
      limit 1
    ) as catalog on true
    left join lateral (
      select coalesce(
        case
          when result.result_payload ->> 'date' ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
          then (result.result_payload ->> 'date')::date
        end,
        (
          select min((record.payload ->> 'date')::date)
          from raw.raw_records as record
          where record.record_type = 'querido_diario_gazette'
            and record.source_record_key = artifact.metadata ->> 'source_record_key'
            and record.payload ->> 'date' ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
        )
      ) as digest_date
    ) as direct_date on true
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
  'Resumo de edições com metadados oficiais do catálogo da Prefeitura e âncoras verificáveis.';

