begin;

-- ADR 0087. Publica as ligações empenho -> contrato confirmadas pela regra
-- determinística (estado 'ligado'), com rótulo de publicação automática e
-- retirada auditada por editorial.editorial_reviews (decision 'withdrawn').
-- Só a versão mais recente de cada empenho entra; do histórico sai apenas o
-- trecho que cita o contrato; valores ficam como texto literal da fonte e
-- nada é somado.
create index commitment_contract_links_portal_idx
  on finance.commitment_contract_links (contract_portal_id)
  where state = 'ligado';

create function api.get_public_commitment_contract_links(
  contract_ids text[]
)
returns table (
  link_id uuid,
  contract_portal_id text,
  commitment_key text,
  commitment_number text,
  issue_date_text text,
  public_body text,
  creditor_name text,
  note_type text,
  amount_text text,
  cited_excerpt text,
  rule_version text,
  review_mode text,
  grid_artifact_sha256 text,
  grid_retrieved_at timestamptz,
  source_page_url text,
  methodology_version text
)
language plpgsql
stable
security definer
set search_path = ''
as $function$
begin
  if contract_ids is null
     or cardinality(contract_ids) < 1
     or cardinality(contract_ids) > 200 then
    raise exception 'contract_ids deve ter entre 1 e 200 ids'
      using errcode = '22023';
  end if;

  return query
  select
    link.id,
    link.contract_portal_id,
    link.commitment_key,
    record.payload ->> 'field1082410',
    record.payload ->> 'field1082407',
    record.payload ->> 'field1082413',
    record.payload ->> 'field1144629',
    record.payload ->> 'field1082409',
    record.payload ->> 'field1082412',
    link.cited_excerpt,
    link.rule_version,
    'automated'::text,
    artifact.sha256,
    artifact.retrieved_at,
    'https://portaldatransparencia.barreiras.ba.gov.br/despesas-geral'::text,
    'commitment-contract-links/1.0.0'::text
  from finance.commitment_contract_links as link
  join raw.raw_records as record
    on record.id = link.commitment_raw_record_id
  join raw.raw_artifacts as artifact
    on artifact.id = record.raw_artifact_id
  where link.state = 'ligado'
    and link.rule_version = 'commitment-contract-link/1.0.0'
    and link.contract_portal_id = any(contract_ids)
    and not exists (
      select 1
      from raw.raw_records as newer
      where newer.record_type = 'municipal_commitment_webrun'
        and newer.source_record_key = record.source_record_key
        and (newer.collected_at, newer.id) > (record.collected_at, record.id)
    )
    and coalesce(
      (
        select review.decision
        from editorial.editorial_reviews as review
        where review.target_type = 'finance.commitment_contract_links'
          and review.target_id = link.id
        order by review.reviewed_at desc, review.id desc
        limit 1
      ),
      'approved'
    ) <> 'withdrawn'
  order by
    link.contract_portal_id,
    to_date(record.payload ->> 'field1082407', 'DD/MM/YYYY') desc,
    link.commitment_key
  limit 2000;
end;
$function$;

revoke all on function api.get_public_commitment_contract_links(text[]) from public;
grant execute on function api.get_public_commitment_contract_links(text[])
  to anon, authenticated;

comment on function api.get_public_commitment_contract_links(text[]) is
  'Empenhos ligados a contratos municipais pela regra commitment-contract-link/1.0.0 (ADR 0086/0087): publicação automática rotulada, retirada auditada, valores em texto da fonte, sem somas.';

commit;
