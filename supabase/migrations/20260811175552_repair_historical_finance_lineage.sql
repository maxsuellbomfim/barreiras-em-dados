begin;

-- Uma correção de proveniência é versionada separadamente dos valores.
-- Isso preserva cada linha financeira original sem duplicar dezenas de milhares
-- de valores que não mudaram.
create table finance.document_lineage_versions (
  id uuid primary key default gen_random_uuid(),
  document_artifact_id uuid not null references raw.raw_artifacts(id),
  normalized_origin_raw_record_id uuid not null references raw.raw_records(id),
  effective_raw_record_id uuid not null references raw.raw_records(id),
  supersedes_id uuid references finance.document_lineage_versions(id),
  version integer not null check (version > 0),
  lineage_status text not null check (
    lineage_status in ('original', 'corrected')
  ),
  source_record_key text not null check (
    length(btrim(source_record_key)) > 0
  ),
  source_url text not null check (source_url ~ '^https://'),
  document_artifact_sha256 text not null check (
    document_artifact_sha256 ~ '^[0-9a-f]{64}$'
  ),
  methodology_version text not null default 'finance-lineage-repair/1.0.0',
  created_at timestamptz not null default statement_timestamp(),
  unique (document_artifact_id, normalized_origin_raw_record_id, version),
  check (
    (
      version = 1
      and supersedes_id is null
      and lineage_status = 'original'
      and effective_raw_record_id = normalized_origin_raw_record_id
    )
    or (
      version > 1
      and supersedes_id is not null
      and lineage_status = 'corrected'
      and effective_raw_record_id <> normalized_origin_raw_record_id
    )
  )
);

create index document_lineage_versions_document_idx
  on finance.document_lineage_versions (document_artifact_id);
create index document_lineage_versions_normalized_origin_idx
  on finance.document_lineage_versions (normalized_origin_raw_record_id);
create index document_lineage_versions_effective_origin_idx
  on finance.document_lineage_versions (effective_raw_record_id);
create index document_lineage_versions_supersedes_idx
  on finance.document_lineage_versions (supersedes_id);
create index document_lineage_versions_lookup_idx
  on finance.document_lineage_versions (
    document_artifact_id,
    normalized_origin_raw_record_id,
    version desc
  );

alter table finance.document_lineage_versions enable row level security;
alter table finance.document_lineage_versions force row level security;

grant select, insert on finance.document_lineage_versions to collector_worker;

create policy collector_worker_document_lineage_versions_select
  on finance.document_lineage_versions
  for select to collector_worker
  using (true);

create policy collector_worker_document_lineage_versions_insert
  on finance.document_lineage_versions
  for insert to collector_worker
  with check (true);

create trigger reject_mutation
before update or delete on finance.document_lineage_versions
for each row execute function audit.reject_mutation();

comment on table finance.document_lineage_versions is
  'Versoes append-only da relacao entre uma origem normalizada e o registro bruto que efetivamente originou o PDF oficial.';

create table audit.finance_lineage_repairs (
  id uuid primary key default gen_random_uuid(),
  original_lineage_version_id uuid not null
    references finance.document_lineage_versions(id),
  corrected_lineage_version_id uuid not null
    references finance.document_lineage_versions(id),
  original_raw_record_id uuid not null references raw.raw_records(id),
  corrected_raw_record_id uuid not null references raw.raw_records(id),
  document_artifact_id uuid not null references raw.raw_artifacts(id),
  document_source_record_key text not null,
  document_artifact_sha256 text not null check (
    document_artifact_sha256 ~ '^[0-9a-f]{64}$'
  ),
  affected_revenue_count integer not null check (affected_revenue_count >= 0),
  affected_expense_report_count integer not null check (
    affected_expense_report_count >= 0
  ),
  affected_expense_line_count integer not null check (
    affected_expense_line_count >= 0
  ),
  repair_methodology text not null default 'finance-lineage-repair/1.0.0',
  created_at timestamptz not null default statement_timestamp(),
  unique (original_raw_record_id, document_artifact_id),
  unique (original_lineage_version_id),
  unique (corrected_lineage_version_id),
  check (original_lineage_version_id <> corrected_lineage_version_id),
  check (original_raw_record_id <> corrected_raw_record_id),
  check (length(btrim(document_source_record_key)) > 0),
  check (
    affected_revenue_count > 0
    or affected_expense_report_count > 0
  )
);

create index finance_lineage_repairs_original_record_idx
  on audit.finance_lineage_repairs (original_raw_record_id);
create index finance_lineage_repairs_corrected_record_idx
  on audit.finance_lineage_repairs (corrected_raw_record_id);
create index finance_lineage_repairs_document_idx
  on audit.finance_lineage_repairs (document_artifact_id, created_at desc);

alter table audit.finance_lineage_repairs enable row level security;
alter table audit.finance_lineage_repairs force row level security;

grant usage on schema audit to collector_worker;
grant select, insert on audit.finance_lineage_repairs to collector_worker;

create policy collector_worker_finance_lineage_repairs_select
  on audit.finance_lineage_repairs
  for select to collector_worker
  using (true);

create policy collector_worker_finance_lineage_repairs_insert
  on audit.finance_lineage_repairs
  for insert to collector_worker
  with check (true);

create trigger reject_mutation
before update or delete on audit.finance_lineage_repairs
for each row execute function audit.reject_mutation();

comment on table audit.finance_lineage_repairs is
  'Trilha append-only das correcoes de origem financeira, com impacto agregado e conflito de evidencias.';

create or replace function finance.has_direct_document_lineage(
  origin_record_id uuid,
  document_artifact_id uuid
)
returns boolean
language sql
stable
security definer
set search_path = ''
as $function$
  select exists (
    select 1
    from raw.raw_records as origin
    join raw.raw_artifacts as source_artifact
      on source_artifact.id = origin.raw_artifact_id
    join raw.raw_artifacts as document
      on document.id = document_artifact_id
     and document.parent_artifact_id = source_artifact.id
     and document.artifact_kind = 'document'
     and document.metadata ->> 'schema_name'
       = 'municipal-transparency-document'
     and document.metadata ->> 'source_record_key'
       = origin.source_record_key
     and document.source_url = origin.payload ->> 'url'
    where origin.id = origin_record_id
      and origin.source_record_key is not null
  );
$function$;

revoke all on function finance.has_direct_document_lineage(uuid, uuid)
  from public, anon, authenticated;

create or replace function finance.resolve_document_origin(
  origin_record_id uuid,
  document_artifact_id uuid
)
returns uuid
language sql
stable
security definer
set search_path = ''
as $function$
  select case
    when finance.has_direct_document_lineage(
      origin_record_id,
      document_artifact_id
    ) then origin_record_id
    else (
      select lineage.effective_raw_record_id
      from finance.document_lineage_versions as lineage
      where lineage.document_artifact_id = document_artifact_id
        and lineage.normalized_origin_raw_record_id = origin_record_id
        and lineage.lineage_status = 'corrected'
        and finance.has_direct_document_lineage(
          lineage.effective_raw_record_id,
          document_artifact_id
        )
      order by lineage.version desc, lineage.created_at desc, lineage.id desc
      limit 1
    )
  end;
$function$;

revoke all on function finance.resolve_document_origin(uuid, uuid)
  from public, anon, authenticated;

-- Mantem o contrato usado por todas as projecoes publicas. "Exata" passa a
-- significar direta ou reconciliada por uma versao append-only comprovada.
create or replace function finance.has_exact_document_lineage(
  origin_record_id uuid,
  document_artifact_id uuid
)
returns boolean
language sql
stable
security definer
set search_path = ''
as $function$
  select finance.resolve_document_origin(
    origin_record_id,
    document_artifact_id
  ) is not null;
$function$;

revoke all on function finance.has_exact_document_lineage(uuid, uuid)
  from public, anon, authenticated;

comment on function finance.has_direct_document_lineage(uuid, uuid) is
  'Confirma chave e URL identicas entre o registro bruto informado e o PDF.';
comment on function finance.resolve_document_origin(uuid, uuid) is
  'Retorna a origem direta ou a origem efetiva da versao de linhagem corrigida.';
comment on function finance.has_exact_document_lineage(uuid, uuid) is
  'Confirma uma linhagem direta ou reconciliada por versao append-only auditavel.';

create or replace function finance.repair_historical_document_lineage()
returns table (
  repaired_lineages integer,
  affected_revenues integer,
  affected_expense_reports integer,
  affected_expense_lines integer,
  conflicts_recorded integer
)
language plpgsql
volatile
security definer
set search_path = ''
as $function$
declare
  candidate record;
  original_lineage_id uuid;
  corrected_lineage_id uuid;
  first_evidence_id uuid;
  second_evidence_id uuid;
  current_revenue_count integer;
  current_report_count integer;
  current_line_count integer;
begin
  repaired_lineages := 0;
  affected_revenues := 0;
  affected_expense_reports := 0;
  affected_expense_lines := 0;
  conflicts_recorded := 0;

  for candidate in
    with normalized_lineages as (
      select
        revenue.origin_raw_record_id,
        revenue.source_document_artifact_id as document_artifact_id
      from finance.revenues as revenue
      where revenue.source_document_artifact_id is not null
      union
      select
        report.origin_raw_record_id,
        report.source_document_artifact_id
      from finance.expense_reports as report
    )
    select
      normalized.origin_raw_record_id,
      normalized.document_artifact_id,
      original.source_record_key as original_source_record_key,
      exact_record.id as exact_raw_record_id,
      exact_record.source_record_key as exact_source_record_key,
      document.sha256 as document_sha256,
      document.source_url as document_source_url
    from normalized_lineages as normalized
    join raw.raw_records as original
      on original.id = normalized.origin_raw_record_id
    join raw.raw_artifacts as document
      on document.id = normalized.document_artifact_id
     and document.artifact_kind = 'document'
     and document.metadata ->> 'schema_name'
       = 'municipal-transparency-document'
    join raw.raw_artifacts as parent
      on parent.id = document.parent_artifact_id
    join lateral (
      select record.*
      from raw.raw_records as record
      where record.raw_artifact_id = parent.id
        and record.source_record_key
          = document.metadata ->> 'source_record_key'
        and record.payload ->> 'url' = document.source_url
      order by record.created_at desc, record.id desc
      limit 1
    ) as exact_record on true
    where not finance.has_direct_document_lineage(
      normalized.origin_raw_record_id,
      normalized.document_artifact_id
    )
      and not exists (
        select 1
        from audit.finance_lineage_repairs as repair
        where repair.original_raw_record_id = normalized.origin_raw_record_id
          and repair.document_artifact_id = normalized.document_artifact_id
      )
    order by normalized.document_artifact_id, normalized.origin_raw_record_id
  loop
    select count(*)::integer
    into current_revenue_count
    from finance.revenues as revenue
    where revenue.origin_raw_record_id = candidate.origin_raw_record_id
      and revenue.source_document_artifact_id = candidate.document_artifact_id;

    select count(*)::integer
    into current_report_count
    from finance.expense_reports as report
    where report.origin_raw_record_id = candidate.origin_raw_record_id
      and report.source_document_artifact_id = candidate.document_artifact_id;

    select count(*)::integer
    into current_line_count
    from finance.expense_lines as line
    join finance.expense_reports as report on report.id = line.report_id
    where report.origin_raw_record_id = candidate.origin_raw_record_id
      and report.source_document_artifact_id = candidate.document_artifact_id;

    insert into finance.document_lineage_versions (
      document_artifact_id,
      normalized_origin_raw_record_id,
      effective_raw_record_id,
      version,
      lineage_status,
      source_record_key,
      source_url,
      document_artifact_sha256
    ) values (
      candidate.document_artifact_id,
      candidate.origin_raw_record_id,
      candidate.origin_raw_record_id,
      1,
      'original',
      candidate.original_source_record_key,
      candidate.document_source_url,
      candidate.document_sha256
    ) returning id into original_lineage_id;

    insert into finance.document_lineage_versions (
      document_artifact_id,
      normalized_origin_raw_record_id,
      effective_raw_record_id,
      supersedes_id,
      version,
      lineage_status,
      source_record_key,
      source_url,
      document_artifact_sha256
    ) values (
      candidate.document_artifact_id,
      candidate.origin_raw_record_id,
      candidate.exact_raw_record_id,
      original_lineage_id,
      2,
      'corrected',
      candidate.exact_source_record_key,
      candidate.document_source_url,
      candidate.document_sha256
    ) returning id into corrected_lineage_id;

    insert into audit.finance_lineage_repairs (
      original_lineage_version_id,
      corrected_lineage_version_id,
      original_raw_record_id,
      corrected_raw_record_id,
      document_artifact_id,
      document_source_record_key,
      document_artifact_sha256,
      affected_revenue_count,
      affected_expense_report_count,
      affected_expense_line_count
    ) values (
      original_lineage_id,
      corrected_lineage_id,
      candidate.origin_raw_record_id,
      candidate.exact_raw_record_id,
      candidate.document_artifact_id,
      candidate.exact_source_record_key,
      candidate.document_sha256,
      current_revenue_count,
      current_report_count,
      current_line_count
    );

    insert into evidence.evidence_items (
      target_type,
      target_id,
      raw_artifact_id,
      raw_record_id,
      evidence_kind,
      source_url,
      locator,
      content_sha256,
      parser_version,
      is_primary
    ) values (
      'finance.document_lineage_version',
      original_lineage_id,
      candidate.document_artifact_id,
      candidate.origin_raw_record_id,
      'document',
      candidate.document_source_url,
      jsonb_build_object(
        'lineage_status', 'original',
        'source_record_key', candidate.original_source_record_key
      ),
      candidate.document_sha256,
      'finance-lineage-repair/1.0.0',
      false
    ) returning id into first_evidence_id;

    insert into evidence.evidence_items (
      target_type,
      target_id,
      raw_artifact_id,
      raw_record_id,
      evidence_kind,
      source_url,
      locator,
      content_sha256,
      parser_version,
      is_primary
    ) values (
      'finance.document_lineage_version',
      corrected_lineage_id,
      candidate.document_artifact_id,
      candidate.exact_raw_record_id,
      'document',
      candidate.document_source_url,
      jsonb_build_object(
        'lineage_status', 'corrected',
        'source_record_key', candidate.exact_source_record_key
      ),
      candidate.document_sha256,
      'finance-lineage-repair/1.0.0',
      true
    ) returning id into second_evidence_id;

    insert into evidence.source_conflicts (
      target_type,
      target_id,
      field_name,
      first_evidence_item_id,
      second_evidence_item_id,
      first_value,
      second_value,
      status,
      resolution,
      resolved_at
    ) values (
      'finance.document_lineage_version',
      corrected_lineage_id,
      'origin_raw_record_id',
      first_evidence_id,
      second_evidence_id,
      jsonb_build_object(
        'raw_record_id', candidate.origin_raw_record_id,
        'source_record_key', candidate.original_source_record_key
      ),
      jsonb_build_object(
        'raw_record_id', candidate.exact_raw_record_id,
        'source_record_key', candidate.exact_source_record_key
      ),
      'resolved',
      'Versao de linhagem corrigida pela igualdade entre artefato pai, chave do registro e URL HTTPS do PDF; valores normalizados preservados.',
      statement_timestamp()
    );

    repaired_lineages := repaired_lineages + 1;
    affected_revenues := affected_revenues + current_revenue_count;
    affected_expense_reports :=
      affected_expense_reports + current_report_count;
    affected_expense_lines := affected_expense_lines + current_line_count;
    conflicts_recorded := conflicts_recorded + 1;
  end loop;

  return next;
end;
$function$;

revoke all on function finance.repair_historical_document_lineage()
  from public, anon, authenticated;
grant execute on function finance.repair_historical_document_lineage()
  to collector_worker;

comment on function finance.repair_historical_document_lineage() is
  'Versiona a linhagem uma vez por registro e PDF, sem duplicar os valores financeiros inalterados.';

-- Backfill transacional e idempotente do acervo já preservado.
select * from finance.repair_historical_document_lineage();

commit;
