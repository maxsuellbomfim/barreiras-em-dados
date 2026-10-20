begin;

-- Reconferência automática das contestações (ADR 0099). Cada mudança de
-- estado vira evento append-only; a linha principal guarda só o estado atual.
create table editorial.public_contestation_events (
  id uuid primary key default gen_random_uuid(),
  contestation_id uuid not null references editorial.public_contestations (id),
  status text not null
    check (status in ('received', 'under_review', 'upheld', 'rejected', 'withdrawn')),
  note text not null check (length(btrim(note)) between 5 and 2000),
  actor text not null check (actor ~ '^automated:[a-z0-9:/._-]+$'),
  created_at timestamptz not null default clock_timestamp()
);

create index public_contestation_events_contestation_idx
  on editorial.public_contestation_events (contestation_id, created_at);

alter table editorial.public_contestation_events enable row level security;
revoke all on editorial.public_contestation_events from public, anon, authenticated;

create or replace function editorial.reject_contestation_event_change()
returns trigger
language plpgsql
set search_path = ''
as $function$
begin
  raise exception 'eventos de contestação são append-only' using errcode = '55000';
end;
$function$;

create trigger public_contestation_events_append_only
  before update or delete on editorial.public_contestation_events
  for each row execute function editorial.reject_contestation_event_change();

create or replace function editorial.record_contestation_decision(
  p_protocol text,
  p_status text,
  p_note text,
  p_actor text
)
returns void
language plpgsql
security definer
set search_path = ''
as $function$
declare
  target editorial.public_contestations;
begin
  select * into target from editorial.public_contestations
  where protocol = upper(btrim(p_protocol))
  for update;
  if target.id is null then
    raise exception 'protocolo inexistente' using errcode = 'P0002';
  end if;
  if target.status in ('upheld', 'rejected', 'withdrawn') then
    raise exception 'contestação já encerrada' using errcode = '55000';
  end if;

  insert into editorial.public_contestation_events (contestation_id, status, note, actor)
  values (target.id, p_status, btrim(p_note), p_actor);

  update editorial.public_contestations
  set status = p_status,
      resolution_note = btrim(p_note),
      resolved_at = case when p_status in ('upheld', 'rejected', 'withdrawn')
        then statement_timestamp() end,
      updated_at = statement_timestamp()
  where id = target.id;
end;
$function$;

-- Camada de código: reexecuta a regra e confere o caso contra o cadastro mais
-- recente. Se não se sustenta, retira o indício por nova revisão e encerra a
-- contestação como procedente. Se se sustenta, a contestação fica em nova
-- conferência para o agente avaliar o que foi alegado.
create or replace function editorial.recheck_public_contestations()
returns integer
language plpgsql
security definer
set search_path = ''
as $function$
declare
  actor constant text := 'automated:contestation-recheck/1.0.0';
  item record;
  finding_id uuid;
  holds boolean;
  handled integer := 0;
begin
  if not exists (
    select 1 from editorial.public_contestations where status = 'received'
  ) then
    return 0;
  end if;

  perform analysis.refresh_supplier_opening_signals();

  for item in
    select protocol, target_path from editorial.public_contestations
    where status = 'received'
    order by created_at
  loop
    finding_id := substring(
      item.target_path
      from '^/indicios\?indicio=([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$'
    )::uuid;

    holds := null;
    if finding_id is not null then
      select
        latest.opened_on is not null
        and latest.legal_nature in ('2046', '2054', '2062', '2305')
        and (finding.deterministic_output ->> 'contract_start')::date
          - latest.opened_on between 0 and 180
        and (finding.deterministic_output ->> 'contract_value')::numeric >= 100000
      into holds
      from analysis.anomaly_findings as finding
      join analysis.anomaly_rules as rule
        on rule.id = finding.anomaly_rule_id and rule.slug = 'supplier-recent-opening'
      left join lateral (
        select
          case when record.payload ->> 'data_inicio_atividade'
              ~ '^(19|20)[0-9]{2}(0[1-9]|1[0-2])(0[1-9]|[12][0-9]|3[01])$'
            then to_date(record.payload ->> 'data_inicio_atividade', 'YYYYMMDD') end as opened_on,
          record.payload ->> 'natureza_juridica' as legal_nature
        from raw.raw_records as record
        where record.record_type = 'receita_cnpj_registry'
          and record.payload ->> 'cnpj' = finding.deterministic_inputs ->> 'supplier_cnpj'
        order by record.created_at desc, record.id desc
        limit 1
      ) as latest on true
      where finding.id = finding_id;
    end if;

    if holds is false then
      insert into editorial.editorial_reviews (
        target_type, target_id, reviewer_subject, review_type, decision, rationale, checklist
      ) values (
        'analysis.anomaly_finding', finding_id, actor, 'data_quality', 'withdrawn',
        'Retirado após contestação ' || item.protocol
          || ': o cadastro mais recente da Receita não sustenta mais a regra.',
        jsonb_build_object('contestation', item.protocol, 'check', 'receita_latest')
      );
      perform editorial.record_contestation_decision(
        item.protocol, 'upheld',
        'Reconferência por código: o cadastro mais recente da Receita Federal não sustenta mais o indício. Ele foi retirado da página por nova versão; o histórico foi preservado.',
        actor
      );
    elsif holds is true then
      perform editorial.record_contestation_decision(
        item.protocol, 'under_review',
        'Reconferência por código: a regra foi reexecutada e o cadastro da Receita e o contrato continuam sustentando o indício. Aguarda a conferência do agente sobre o que foi alegado.',
        actor
      );
    else
      perform editorial.record_contestation_decision(
        item.protocol, 'under_review',
        'Recebida. Aguarda conferência do agente contra a fonte oficial da página contestada.',
        actor
      );
    end if;
    handled := handled + 1;
  end loop;

  return handled;
end;
$function$;

revoke all on function editorial.record_contestation_decision(text, text, text, text) from public, anon, authenticated;
revoke all on function editorial.recheck_public_contestations() from public, anon, authenticated;

-- A cada 15 minutos (00, 15, 30, 45: fora da janela :17-:23 da sonda).
do $schedule$
begin
  if exists (select 1 from pg_extension where extname = 'pg_cron') then
    perform cron.schedule('barreiras-contestation-recheck', '*/15 * * * *',
      'select editorial.recheck_public_contestations()');
  end if;
end;
$schedule$;

commit;
