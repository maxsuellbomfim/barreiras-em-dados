-- Publica linhas financeiras somente depois da validação determinística.
-- Magnitudes ficam não negativas no banco; a direção devolve deduções assinadas.

alter table finance.revenues
  add column if not exists source_document_artifact_id uuid
    references raw.raw_artifacts(id),
  add column if not exists accumulated_amount numeric(20,2)
    check (accumulated_amount is null or accumulated_amount >= 0),
  add column if not exists difference_more numeric(20,2)
    check (difference_more is null or difference_more >= 0),
  add column if not exists difference_less numeric(20,2)
    check (difference_less is null or difference_less >= 0),
  add column if not exists collection_direction text not null default 'credit'
    check (collection_direction in ('credit', 'deduction')),
  add column if not exists methodology_version text not null
    default 'public-revenue-pdf/1.0.0',
  add column if not exists validation_status text not null default 'needs_review'
    check (validation_status in (
      'extracted', 'validated', 'needs_source', 'needs_review', 'superseded'
    )),
  add column if not exists published_at timestamptz;

alter table finance.revenues
  add constraint revenues_validated_requires_publication check (
    validation_status <> 'validated' or published_at is not null
  );

create index if not exists revenues_publication_status_idx
  on finance.revenues (public_body_id, fiscal_year, validation_status, revenue_date desc);

create index if not exists revenues_source_document_idx
  on finance.revenues (source_document_artifact_id);

create unique index if not exists revenues_external_version_idx
  on finance.revenues (public_body_id, external_id, version)
  where external_id is not null;

drop function if exists api.get_public_revenues(integer, smallint);

create function api.get_public_revenues(
  page_size integer default 100,
  fiscal_year_filter smallint default null
)
returns table (
  revenue_id uuid,
  external_id text,
  fiscal_year smallint,
  revenue_date date,
  revenue_code text,
  description text,
  collected_amount numeric,
  accumulated_amount numeric,
  collection_direction text,
  currency text,
  public_body_name text,
  source_url text,
  document_source_url text,
  artifact_sha256 text,
  document_artifact_sha256 text,
  collected_at timestamptz,
  methodology_version text,
  validation_status text
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

  if fiscal_year_filter is not null
     and (fiscal_year_filter < 1900 or fiscal_year_filter > 2200) then
    raise exception 'fiscal_year_filter fora do intervalo permitido'
      using errcode = '22023';
  end if;

  return query
  with ranked as (
    select
      revenue.*,
      row_number() over (
        partition by revenue.public_body_id,
          coalesce(revenue.external_id, revenue.id::text)
        order by revenue.version desc, revenue.created_at desc, revenue.id desc
      ) as current_row
    from finance.revenues as revenue
    where revenue.validation_status = 'validated'
      and revenue.published_at is not null
      and (
        fiscal_year_filter is null
        or revenue.fiscal_year = fiscal_year_filter
      )
  )
  select
    revenue.id,
    revenue.external_id,
    revenue.fiscal_year,
    revenue.revenue_date,
    revenue.revenue_code,
    revenue.description,
    case
      when revenue.collection_direction = 'deduction'
      then -revenue.collected_amount
      else revenue.collected_amount
    end,
    case
      when revenue.collection_direction = 'deduction'
      then -revenue.accumulated_amount
      else revenue.accumulated_amount
    end,
    revenue.collection_direction,
    revenue.currency::text,
    body.name,
    source_artifact.source_url,
    document.source_url,
    source_artifact.sha256,
    document.sha256,
    source_artifact.retrieved_at,
    revenue.methodology_version,
    revenue.validation_status
  from ranked as revenue
  join org.public_bodies as body
    on body.id = revenue.public_body_id
  join raw.raw_records as origin
    on origin.id = revenue.origin_raw_record_id
  join raw.raw_artifacts as source_artifact
    on source_artifact.id = origin.raw_artifact_id
  join raw.raw_artifacts as document
    on document.id = revenue.source_document_artifact_id
   and document.artifact_kind = 'document'
  where revenue.current_row = 1
  order by revenue.revenue_date desc nulls last, revenue.created_at desc,
    revenue.id desc
  limit page_size;
end;
$function$;

revoke all on function api.get_public_revenues(integer, smallint) from public;
grant execute on function api.get_public_revenues(integer, smallint)
  to anon, authenticated;

comment on function api.get_public_revenues(integer, smallint) is
  'Receitas validadas com direção contábil, PDF preservado e proveniência completa.';
