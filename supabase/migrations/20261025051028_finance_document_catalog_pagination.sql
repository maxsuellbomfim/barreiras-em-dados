begin;

-- Separate endpoint: existing limited calendars keep their explicit scope.
-- Version selection precedes year filtering; totals cover the entire recorte.
create or replace function api.get_public_finance_document_page(
  page_size integer default 25,
  page_number integer default 1,
  year_filter integer default null,
  resource_filter text default null
)
returns table(total_count bigint, available_years integer[], items jsonb)
language plpgsql stable security definer set search_path = ''
as $function$
declare
  resources constant text[] := array[
    'balancetes','pdc-contas-anuais','pdc-receita-tributaria',
    'pdc-recursos-extraordinarios','pdc-resumo-execucao-da-receita',
    'pdc-resumo-execucao-da-despesa','pdc-transferencia',
    'pdc-emendas-parlamentares-receitas','pdc-convenios-transferencias-realizadas',
    'pdc-obras-pdc','rreo','rgf'
  ];
begin
  if page_size is null or page_size not between 1 and 50
     or page_number is null or page_number not between 1 and 100000
     or (year_filter is not null and year_filter not between 1900 and 2100)
     or (resource_filter is not null and not resource_filter = any(resources)) then
    raise exception 'Filtro ou pagina invalida' using errcode = '22023';
  end if;
  return query
  with ranked as (
    select r.*,
      split_part(r.record_type,'municipal_transparency_',2) as resource,
      row_number() over (
        partition by r.record_type,coalesce(r.source_record_key,r.id::text)
        order by r.created_at desc,r.id desc
      ) as version_rank
    from raw.raw_records r
    where r.record_type = any(
      array(select 'municipal_transparency_' || unnest(resources))
    )
      and (resource_filter is null or r.record_type = 'municipal_transparency_' || resource_filter)
  ), catalog as materialized (
    select r.*,
      case when coalesce(r.payload->>'ano',r.payload->>'ano_ref') ~ '^[0-9]{4}$'
        then coalesce(r.payload->>'ano',r.payload->>'ano_ref')::integer end as year
    from ranked r
    join raw.raw_artifacts a on a.id=r.raw_artifact_id
    where r.version_rank=1 and r.payload->>'url' ~ '^https://'
  ), filtered as materialized (
    select c.* from catalog c where year_filter is null or c.year=year_filter
  ), page as materialized (
    select f.* from filtered f order by f.created_at desc,f.id desc
    limit page_size offset (page_number::bigint-1)*page_size
  ), documents as (
    select p.created_at,p.id,
      jsonb_build_object(
        'document_id',p.id,'source_resource',p.resource,
        'title',left(coalesce(nullif(btrim(p.payload->>'titulo'),''),
          nullif(btrim(p.payload->>'informacoes'),''),
          nullif(btrim(p.payload->>'descricao'),''),'Documento financeiro oficial'),500),
        'reference_date',p.payload->>'data','fiscal_year',p.year,
        'reference_month',case when coalesce(p.payload->>'mes',p.payload->>'mes_ref') ~ '^[0-9]{1,2}$'
          then coalesce(p.payload->>'mes',p.payload->>'mes_ref')::integer end,
        'description',null, -- Only compact catalog metadata; original stays at source.
        'document_url',p.payload->>'url','api_source_url',a.source_url,
        'artifact_sha256',a.sha256,'collected_at',a.retrieved_at,
        'source_status','api_response_preserved',
        'methodology_version','public-finance-documents/1.6.0',
        'document_artifact_sha256',d.sha256,'document_preserved',d.id is not null
      ) as item
    from page p join raw.raw_artifacts a on a.id=p.raw_artifact_id
    left join lateral (
      select child.id,child.sha256 from raw.raw_artifacts child
      where child.source_endpoint_id=a.source_endpoint_id
        and child.artifact_kind='document'
        and child.metadata->>'schema_name'='municipal-transparency-document'
        and child.metadata->>'source_record_key'=p.source_record_key
        and child.source_url=p.payload->>'url'
      order by child.created_at desc,child.id desc limit 1
    ) d on true
  )
  select (select count(*) from filtered),
    coalesce((select array_agg(distinct c.year order by c.year desc)
      from catalog c where c.year between 1900 and 2100),'{}'::integer[]),
    coalesce((select jsonb_agg(d.item order by d.created_at desc,d.id desc)
      from documents d),'[]'::jsonb);
end;
$function$;

revoke all on function api.get_public_finance_document_page(integer,integer,integer,text) from public;
grant execute on function api.get_public_finance_document_page(integer,integer,integer,text) to anon,authenticated;
comment on function api.get_public_finance_document_page(integer,integer,integer,text) is
  'Paginas de referencias financeiras preservadas, por ano e familia. Total nao comprova integralidade do portal oficial nem quantidade de PDFs distintos.';
notify pgrst,'reload schema';
commit;
