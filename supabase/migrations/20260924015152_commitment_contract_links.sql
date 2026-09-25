begin;

-- ADR 0086. Decisões da regra determinística empenho -> contrato municipal.
-- Append-only: cada registro bruto de empenho recebe no máximo uma decisão
-- por versão da regra; nova versão gera novas linhas, nunca reescreve as
-- anteriores. Tabela interna: nada aqui é projeção pública.
create table finance.commitment_contract_links (
  id uuid primary key default gen_random_uuid(),
  commitment_raw_record_id uuid not null references raw.raw_records(id),
  commitment_key text not null check (commitment_key ~ '^[OE]-[0-9]+$'),
  state text not null check (
    state in ('ligado', 'citacao_sem_confirmacao', 'sem_citacao', 'fora_do_escopo')
  ),
  reason text not null default '' check (
    reason in (
      '', 'extra_orcamentario', 'numero_ilegivel', 'multiplas_citacoes',
      'nenhum_contrato', 'varios_contratos', 'favorecido_divergente'
    )
  ),
  cited_excerpt text not null default '',
  contract_raw_record_id uuid references raw.raw_records(id),
  contract_portal_id text,
  rule_version text not null check (
    rule_version ~ '^commitment-contract-link/[0-9]+\.[0-9]+\.[0-9]+$'
  ),
  decided_at timestamptz not null default now(),
  unique (commitment_raw_record_id, rule_version),
  check ((state = 'ligado') = (contract_raw_record_id is not null)),
  check ((state = 'ligado') = (contract_portal_id is not null)),
  check ((state = 'citacao_sem_confirmacao') = (reason not in ('', 'extra_orcamentario'))),
  check ((state = 'fora_do_escopo') = (reason = 'extra_orcamentario'))
);

create index commitment_contract_links_contract_idx
  on finance.commitment_contract_links (contract_raw_record_id);

alter table finance.commitment_contract_links enable row level security;
alter table finance.commitment_contract_links force row level security;
revoke all on finance.commitment_contract_links from anon, authenticated;

-- O comando de reconciliação roda com a identidade dos coletores: lê para
-- saber o que já foi decidido e só insere; atualização e exclusão ficam
-- barradas pelo gatilho abaixo.
grant select, insert on finance.commitment_contract_links to collector_worker;

create policy collector_worker_commitment_contract_links_select
  on finance.commitment_contract_links
  for select to collector_worker
  using (true);

create policy collector_worker_commitment_contract_links_insert
  on finance.commitment_contract_links
  for insert to collector_worker
  with check (true);

create trigger reject_mutation
before update or delete on finance.commitment_contract_links
for each row execute function audit.reject_mutation();

comment on table finance.commitment_contract_links is
  'Decisões versionadas da ligação empenho -> contrato municipal (ADR 0086); sem publicação.';

commit;
