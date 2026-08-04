-- O publicador de receitas usa a mesma identidade técnica do coletor.
-- Concede apenas o mínimo necessário e mantém as tabelas internas fora da
-- API pública; RLS continua habilitado como segunda barreira.

grant usage on schema org, finance, evidence to collector_worker;

grant select on org.public_bodies to collector_worker;
grant insert (
  origin_raw_record_id,
  ibge_code,
  official_code,
  name,
  body_type,
  jurisdiction,
  state_code,
  active_from
) on org.public_bodies to collector_worker;

grant select, insert on finance.revenues to collector_worker;
grant insert on evidence.evidence_items to collector_worker;

create policy collector_worker_public_bodies_select
  on org.public_bodies
  for select to collector_worker
  using (true);

create policy collector_worker_public_bodies_insert
  on org.public_bodies
  for insert to collector_worker
  with check (true);

create policy collector_worker_finance_revenues_select
  on finance.revenues
  for select to collector_worker
  using (true);

create policy collector_worker_finance_revenues_insert
  on finance.revenues
  for insert to collector_worker
  with check (true);

create policy collector_worker_evidence_items_insert
  on evidence.evidence_items
  for insert to collector_worker
  with check (true);
