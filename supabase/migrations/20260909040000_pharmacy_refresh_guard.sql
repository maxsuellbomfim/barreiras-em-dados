begin;
-- Trusted worker must first re-read original bytes and run assess_refresh.
-- No web/collector grants here: this guard is not an acquisition validator.
create function source.approve_pharmacy_refresh(p_previous bigint,p_next bigint)
returns bigint language plpgsql security invoker set search_path='' as $$
declare old source.fns_pharmacy_snapshots; fresh source.fns_pharmacy_snapshots;
  last_decision text; decision_id bigint;
begin
  -- Serialize snapshot creation and all approval/revocation writers, including
  -- manual inserts that do not use an advisory lock. Reads remain unblocked.
  lock table source.fns_pharmacy_snapshots,source.fns_pharmacy_decisions
    in share row exclusive mode;
  select * into old from source.fns_pharmacy_snapshots where id=p_previous for update;
  select * into fresh from source.fns_pharmacy_snapshots where id=p_next for update;
  if old.id is null or fresh.id is null or p_next<=p_previous
    or old.scope_key<>fresh.scope_key or old.payment_year<>fresh.payment_year
    or old.establishment<>fresh.establishment or old.register_sha256<>fresh.register_sha256
  then raise exception 'Pharmacy refresh scope mismatch'; end if;
  if (select max(id) from source.fns_pharmacy_snapshots where scope_key=old.scope_key)<>p_next
    or (select max(id) from source.fns_pharmacy_snapshots where scope_key=old.scope_key and id<p_next)<>p_previous
  then raise exception 'Pharmacy refresh baseline superseded'; end if;
  select decision into last_decision from source.fns_pharmacy_decisions
    where snapshot_id=p_previous order by id desc limit 1;
  if last_decision is distinct from 'approved' then
    raise exception 'Pharmacy refresh baseline not approved'; end if;
  if old.expected_documents<>(select count(*) from source.fns_pharmacy_documents where snapshot_id=p_previous)
    or fresh.expected_documents<>(select count(*) from source.fns_pharmacy_documents where snapshot_id=p_next)
    or exists(select 1 from source.fns_pharmacy_documents d where d.snapshot_id in(p_previous,p_next)
      and not source.pharmacy_document_matches(d))
  then raise exception 'Pharmacy refresh evidence mismatch'; end if;
  if exists(select 1 from source.fns_pharmacy_documents d where d.snapshot_id=p_previous
    and not exists(select 1 from source.fns_pharmacy_documents n where n.snapshot_id=p_next
      and n.document_key=d.document_key and n.document_date=d.document_date and n.net_amount=d.net_amount))
  then raise exception 'Pharmacy refresh changed or removed document'; end if;
  if exists(select 1 from source.fns_pharmacy_documents n
    join source.fns_pharmacy_documents other on other.document_key=n.document_key
    join source.fns_pharmacy_snapshots s on s.id=other.snapshot_id
    where n.snapshot_id=p_next and s.scope_key<>fresh.scope_key
      and s.id=(select max(x.id) from source.fns_pharmacy_snapshots x where x.scope_key=s.scope_key))
  then raise exception 'Pharmacy refresh duplicate scope'; end if;
  select id,decision into decision_id,last_decision from source.fns_pharmacy_decisions
    where snapshot_id=p_next order by id desc limit 1;
  if decision_id is not null then
    if last_decision='approved' and exists(select 1 from source.fns_pharmacy_decisions
      where id=decision_id and reviewer_ref='worker:pharmacy-refresh-v1') then return decision_id; end if;
    raise exception 'Pharmacy refresh already reviewed';
  end if;
  insert into source.fns_pharmacy_decisions(snapshot_id,decision,reviewer_ref,review_note)
    values(p_next,'approved','worker:pharmacy-refresh-v1',
      'Atualizacao incremental: identidade e documentos anteriores preservados. Leitura dos originais exigida no worker; nao comprova credenciamento historico nem execucao.')
    returning id into decision_id;
  return decision_id;
end;
$$;
revoke all on function source.approve_pharmacy_refresh(bigint,bigint)
  from public,anon,authenticated,service_role;
commit;
