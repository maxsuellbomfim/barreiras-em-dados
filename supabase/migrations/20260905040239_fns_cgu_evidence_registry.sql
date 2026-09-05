begin;

-- Separate evidence from decisions and from financial records. Only privileged
-- operators can append either relation. No collector/browser approval grant.
create table source.fns_cgu_evidence (
  reconciliation_key text primary key check (reconciliation_key ~ '^[0-9a-f]{64}$'),
  version_id bigint generated always as identity unique,
  payment_artifact_id uuid not null references raw.raw_artifacts(id),
  order_artifact_id uuid not null references raw.raw_artifacts(id),
  cgu_raw_record_id uuid not null references raw.raw_records(id),
  payment_sha256 text not null check (payment_sha256 ~ '^[0-9a-f]{64}$'),
  order_sha256 text not null check (order_sha256 ~ '^[0-9a-f]{64}$'),
  cgu_archive_sha256 text not null check (cgu_archive_sha256 ~ '^[0-9a-f]{64}$'),
  document_code text not null check (document_code ~ '^257001[0-9]{9}OB[0-9]{6}$'),
  amendment_code text not null check (amendment_code ~ '^[0-9]{4}5041[0-9]{4}$'),
  amendment_year smallint not null check (amendment_year between 2000 and 2100),
  document_date date not null check (document_date between date '2021-01-01' and date '2100-12-31'),
  paid_amount numeric(20,2) not null check (paid_amount > 0),
  source_row_number integer not null check (source_row_number > 0),
  proposal_number text not null check (proposal_number ~ '^[0-9]{17}$'),
  cgu_author_name text not null check (cgu_author_name = 'COM. DA SAUDE'),
  fns_author_name text not null check (fns_author_name = 'COMISSÃO DA SAÚDE'),
  requester_name text check (
    requester_name = btrim(requester_name)
    and length(requester_name) between 2 and 120
    and requester_name !~ '[0-9<>[:cntrl:]]'
  ),
  requester_source_code text check (requester_source_code ~ '^[0-9]{4}$'),
  created_at timestamptz not null default clock_timestamp(),
  check (payment_artifact_id <> order_artifact_id),
  check ((requester_name is null) = (requester_source_code is null)),
  check (left(amendment_code,4) = amendment_year::text),
  check (substring(document_code from 12 for 4) = extract(year from document_date)::integer::text),
  check (amendment_year <= extract(year from document_date))
);

create index fns_cgu_evidence_document_version_idx
  on source.fns_cgu_evidence(document_code, version_id desc);
create index fns_cgu_evidence_payment_idx on source.fns_cgu_evidence(payment_artifact_id);
create index fns_cgu_evidence_order_idx on source.fns_cgu_evidence(order_artifact_id);
create index fns_cgu_evidence_record_idx on source.fns_cgu_evidence(cgu_raw_record_id);

create table source.fns_cgu_decisions (
  id bigint generated always as identity primary key,
  reconciliation_key text not null references source.fns_cgu_evidence(reconciliation_key),
  decision text not null check (decision in ('approved','rejected','revoked')),
  reviewer_ref text not null check (reviewer_ref ~ '^[a-zA-Z0-9:_.-]{3,100}$'),
  review_note text not null check (length(btrim(review_note)) between 20 and 2000),
  database_role text not null default current_user,
  decided_at timestamptz not null default clock_timestamp()
);
create index fns_cgu_decisions_latest_idx
  on source.fns_cgu_decisions(reconciliation_key, id desc);

alter table source.fns_cgu_evidence enable row level security;
alter table source.fns_cgu_decisions enable row level security;
revoke all on source.fns_cgu_evidence, source.fns_cgu_decisions
  from public, anon, authenticated, service_role;
revoke all on sequence source.fns_cgu_evidence_version_id_seq,
  source.fns_cgu_decisions_id_seq from public, anon, authenticated, service_role;

create trigger reject_mutation before update or delete on source.fns_cgu_evidence
  for each row execute function audit.reject_mutation();
create trigger reject_mutation before update or delete on source.fns_cgu_decisions
  for each row execute function audit.reject_mutation();

-- These checks bind the candidate to registered originals. They do not replace
-- the importer reading/hashing private Storage bytes and rerunning the parser.
create function source.fns_cgu_artifacts_match(e source.fns_cgu_evidence)
returns boolean language sql stable security invoker set search_path = '' as $$
  select exists (
    select 1 from raw.raw_artifacts p
    join raw.raw_artifacts o on o.id = e.order_artifact_id
    join raw.raw_records r on r.id = e.cgu_raw_record_id
    join raw.raw_artifacts c on c.id = r.raw_artifact_id
    where p.id = e.payment_artifact_id
      and p.sha256 = e.payment_sha256 and o.sha256 = e.order_sha256
      and c.sha256 = e.cgu_archive_sha256
      and p.artifact_kind = 'http_response' and o.artifact_kind = 'http_response'
      and c.artifact_kind = 'archive'
      and p.content_type = 'application/json' and o.content_type = 'application/json'
      and p.http_status between 200 and 299 and o.http_status between 200 and 299
      and c.http_status between 200 and 299
      and p.byte_size > 0 and o.byte_size > 0 and c.byte_size > 0
      and p.source_url ~ '^https://consultafns[.]saude[.]gov[.]br/recursos/consulta-detalhada/detalhe-pagamento[?]'
      and o.source_url ~ '^https://consultafns[.]saude[.]gov[.]br/recursos/consulta-detalhada/detalhe-ordem-bancaria[?]'
      and c.source_url = 'https://dadosabertos-download.cgu.gov.br/PortalDaTransparencia/saida/emendas-parlamentares-documentos/'
        || extract(year from e.document_date)::integer::text || '_EmendasParlamentaresPorDocumento.zip'
      and r.record_type = 'cgu_federal_amendment_document'
      and r.payload->>'document_code' = e.document_code
      and r.payload->>'amendment_code' = e.amendment_code
      and r.payload->>'amendment_year' = e.amendment_year::text
      and r.payload->>'document_date' = e.document_date::text
      and (r.payload->>'paid_amount')::numeric = e.paid_amount
      and r.payload->>'author_name' = e.cgu_author_name
      and r.payload->>'expense_stage' = 'payment'
      and r.payload->>'municipality_ibge' = '2903201'
      and r.payload->>'beneficiary_code' = '08595187000125'
      and r.payload->>'source_row_number' = e.source_row_number::text
  );
$$;
revoke all on function source.fns_cgu_artifacts_match(source.fns_cgu_evidence)
  from public, anon, authenticated, service_role;

create function source.validate_fns_cgu_evidence()
returns trigger language plpgsql security invoker set search_path = '' as $$
begin
  if not source.fns_cgu_artifacts_match(new) then
    raise exception 'FNS evidence does not match registered originals' using errcode = '23514';
  end if;
  return new;
end;
$$;
revoke all on function source.validate_fns_cgu_evidence()
  from public, anon, authenticated, service_role;
create trigger validate_fns_cgu_evidence before insert on source.fns_cgu_evidence
  for each row execute function source.validate_fns_cgu_evidence();

-- Explicit, minimized public read boundary over private evidence/decisions.
-- No public write RPC, private IDs, banking fields, review notes or new amounts.
create function api.get_public_fns_cgu_links(document_codes text[])
returns table (
  document_code text, cgu_archive_sha256 text, requester_name text,
  fns_author_name text, payment_sha256 text, order_sha256 text,
  source_url text, reviewed_at timestamptz, methodology_version text
)
language plpgsql stable security definer set search_path = '' as $$
begin
  if document_codes is null or cardinality(document_codes) > 50
    or exists (select 1 from unnest(document_codes) x
      where x is null or x !~ '^[0-9]{15}OB[0-9]{6}$') then
    raise exception 'Invalid document scope (maximum 50)' using errcode = '22023';
  end if;
  return query
  with latest_evidence as materialized (
    select distinct on (e.document_code) e.*
    from source.fns_cgu_evidence e where e.document_code = any(document_codes)
    order by e.document_code, e.version_id desc
  ), current_documents as materialized (
    select d.*, count(*) over (partition by d.document_code, d.artifact_sha256) n
    from territory.cgu_federal_amendment_documents d
    where d.document_code = any(document_codes)
  )
  select e.document_code, e.cgu_archive_sha256, e.requester_name,
    e.fns_author_name, e.payment_sha256, e.order_sha256,
    'https://consultafns.saude.gov.br/#/detalhada'::text, decision.decided_at,
    'fns-cgu-reviewed-links/1.0.0'::text
  from latest_evidence e
  join lateral (
    select v.decision, v.decided_at from source.fns_cgu_decisions v
    where v.reconciliation_key = e.reconciliation_key order by v.id desc limit 1
  ) decision on decision.decision = 'approved'
  join current_documents d on d.raw_record_id = e.cgu_raw_record_id
    and d.document_code = e.document_code and d.artifact_sha256 = e.cgu_archive_sha256
    and d.amendment_code = e.amendment_code and d.amendment_year = e.amendment_year
    and d.document_date = e.document_date and d.paid_amount = e.paid_amount
    and d.author_name = e.cgu_author_name and d.author_kind = 'commission'
    and d.expense_stage = 'payment' and d.source_row_number = e.source_row_number
    and d.n = 1
  where e.requester_name is not null and source.fns_cgu_artifacts_match(e)
  order by e.document_code;
end;
$$;
revoke all on function api.get_public_fns_cgu_links(text[])
  from public, anon, authenticated, service_role;
grant execute on function api.get_public_fns_cgu_links(text[]) to anon, authenticated;

comment on table source.fns_cgu_evidence is
  'Immutable private candidates, bound to registered raw artifacts. Importer must verify Storage bytes; this table does not authorize publication.';
comment on table source.fns_cgu_decisions is
  'Append-only operator decisions. Approval applies only to one evidence version, never to a person or a financial ranking.';

notify pgrst, 'reload schema';
commit;
