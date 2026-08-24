begin;

drop function api.get_public_siconfi_annual_totals(
  integer, smallint, smallint
);

create function api.get_public_siconfi_annual_totals(
  page_size integer default 70,
  fiscal_year_from smallint default 2021,
  fiscal_year_to smallint default null
)
returns table (
  total_id uuid,
  fiscal_year smallint,
  metric_key text,
  amount text,
  currency text,
  official_annex text,
  official_label text,
  official_column_label text,
  official_account_code text,
  official_account_label text,
  source_url text,
  source_artifact_sha256 text,
  source_retrieved_at timestamptz,
  methodology_version text
)
language plpgsql
stable
security definer
set search_path = ''
as $function$
declare
  effective_year_to smallint := coalesce(
    fiscal_year_to,
    extract(year from current_date)::smallint
  );
begin
  if page_size < 1 or page_size > 140 then
    raise exception 'page_size deve estar entre 1 e 140'
      using errcode = '22023';
  end if;

  if fiscal_year_from < 1988
     or fiscal_year_from > effective_year_to
     or effective_year_to > 2200 then
    raise exception 'intervalo fiscal inválido'
      using errcode = '22023';
  end if;

  return query
  select
    total.id,
    total.fiscal_year,
    total.metric_key,
    total.amount::text,
    total.currency::text,
    total.official_annex,
    total.official_label,
    total.official_column_label,
    total.official_account_code,
    total.official_account_label,
    artifact.source_url,
    artifact.sha256,
    artifact.retrieved_at,
    total.methodology_version
  from finance.siconfi_annual_totals as total
  join raw.raw_artifacts as artifact on artifact.id = total.source_artifact_id
  where total.validation_status = 'validated'
    and total.fiscal_year between fiscal_year_from and effective_year_to
    and not exists (
      select 1
      from finance.siconfi_annual_totals as successor
      where successor.supersedes_id = total.id
    )
    and exists (
      select 1
      from evidence.evidence_items as evidence_item
      where evidence_item.target_type = 'finance.siconfi_annual_totals'
        and evidence_item.target_id = total.id
        and evidence_item.raw_record_id = total.origin_raw_record_id
        and evidence_item.raw_artifact_id = total.source_artifact_id
        and evidence_item.is_primary
    )
  order by total.fiscal_year desc, total.metric_key
  limit page_size;
end;
$function$;

revoke all on function api.get_public_siconfi_annual_totals(
  integer, smallint, smallint
) from public;
grant execute on function api.get_public_siconfi_annual_totals(
  integer, smallint, smallint
) to anon, authenticated;

comment on function api.get_public_siconfi_annual_totals(
  integer, smallint, smallint
) is
  'Publica valores literais como texto decimal exato; não calcula saldo, superávit, déficit nem receita líquida.';

notify pgrst, 'reload schema';

commit;
