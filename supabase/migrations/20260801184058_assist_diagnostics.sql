-- Observabilidade da cascata de IA (ADR 0011).
-- A cascata degrada por design: provedor indisponível vira estado explícito
-- e o passo termina com sucesso. O efeito colateral é que "nada foi
-- sugerido" ficava indistinguível de "tudo correu bem" sem abrir o log do
-- Actions. Esta tabela registra o resultado de cada tentativa, por
-- provedor, para que a causa seja diagnosticável direto do banco.

create table audit.assist_diagnostics (
  id uuid primary key default gen_random_uuid(),
  occurred_at timestamptz not null default statement_timestamp(),
  command text not null check (length(btrim(command)) between 1 and 120),
  provider text not null check (length(btrim(provider)) between 1 and 60),
  model text,
  outcome text not null check (
    outcome in ('succeeded', 'quota_exhausted', 'transient', 'contract',
                'missing_key', 'exhausted', 'unexpected')
  ),
  http_status smallint,
  detail text check (detail is null or length(detail) <= 500),
  metadata jsonb not null default '{}'::jsonb
);

create index assist_diagnostics_occurred_at_idx
  on audit.assist_diagnostics (occurred_at desc);

alter table audit.assist_diagnostics enable row level security;
alter table audit.assist_diagnostics force row level security;

revoke all on table audit.assist_diagnostics
  from public, anon, authenticated;

grant usage on schema audit to collector_worker;
grant insert, select on table audit.assist_diagnostics to collector_worker;

comment on table audit.assist_diagnostics is
  'Resultado por tentativa da cascata assistida; sem conteúdo de prompt '
  'nem credencial — apenas provedor, modelo, desfecho e status.';
