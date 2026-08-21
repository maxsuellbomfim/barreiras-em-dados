begin;

create or replace function hr.verify_payroll_report_aggregate_lineage()
returns trigger
language plpgsql
security definer
set search_path = ''
as $function$
declare
  origin_record raw.raw_records%rowtype;
  source_document raw.raw_artifacts%rowtype;
  source_year text;
  source_month text;
begin
  select * into origin_record
  from raw.raw_records
  where id = new.origin_raw_record_id;

  select * into source_document
  from raw.raw_artifacts
  where id = new.source_document_artifact_id;

  if origin_record.id is null
    or origin_record.record_type <> 'municipal_transparency_servidores'
    or not (
      origin_record.payload ->> 'tipo' = '1'
      or (
        coalesce(trim(origin_record.payload ->> 'tipo'), '') = ''
        and regexp_replace(
          translate(
            lower(trim(coalesce(origin_record.payload ->> 'titulo', ''))),
            'áàâãäéèêëíìîïóòôõöúùûüç',
            'aaaaaeeeeiiiiooooouuuuc'
          ),
          '[[:space:]]+',
          ' ',
          'g'
        ) = 'relacao de servidores'
      )
    ) then
    raise exception 'payroll aggregate requires an official municipal staff catalog record'
      using errcode = '23514';
  end if;

  source_year := origin_record.payload ->> 'ano_ref';
  source_month := origin_record.payload ->> 'mes_ref';
  if source_year is null or source_year !~ '^[0-9]{4}$'
    or source_month is null or source_month !~ '^(?:[1-9]|1[0-2])$'
    or make_date(source_year::integer, source_month::integer, 1)
      <> new.reference_month then
    raise exception 'payroll aggregate reference month differs from official catalog'
      using errcode = '23514';
  end if;

  if source_document.id is null
    or source_document.artifact_kind <> 'document'
    or source_document.metadata ->> 'schema_name'
      <> 'municipal-transparency-document'
    or source_document.metadata ->> 'source_record_key'
      is distinct from origin_record.source_record_key
    or source_document.source_url
      is distinct from origin_record.payload ->> 'url' then
    raise exception 'payroll aggregate document does not match official catalog evidence'
      using errcode = '23514';
  end if;

  return new;
end;
$function$;

revoke all on function hr.verify_payroll_report_aggregate_lineage() from public;

comment on function hr.verify_payroll_report_aggregate_lineage() is
  'Valida competência, documento e natureza da folha; aceita tipo 1 ou o título histórico exato Relação de Servidores quando a fonte omitiu o tipo.';

commit;
