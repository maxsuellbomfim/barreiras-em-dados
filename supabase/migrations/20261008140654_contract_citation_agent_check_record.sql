begin;

-- contract-citation-agent-check/1.0.0 (ADR 0096, emenda de 08/10/2026): a
-- amostra pode ser conferida por agente que lê a lista de contratos do portal
-- ao vivo (scripts/check-contract-citations.mjs). A decisão é calculada aqui,
-- por código, a partir da evidência: qualquer caso presente na lista bloqueia a
-- publicação. O registro leva o rótulo do ADR 0091 ("conferência automática
-- por agente, não revisão humana"); decisão humana posterior prevalece.

create function finance.record_contract_citation_agent_check(p_evidence jsonb)
returns table (decision text, reviewed_at timestamptz, checked_cases integer)
language plpgsql
volatile
set search_path = ''
as $function$
declare
  cases jsonb := p_evidence -> 'cases';
  outcomes text[];
  verdict text;
  checked integer;
begin
  if p_evidence ->> 'check_version' <> 'contract-citation-agent-check/1.0.0'
    or jsonb_typeof(cases) <> 'array'
    or (p_evidence ->> 'portal_contracts')::integer < 1000
    or (p_evidence ->> 'read_at')::timestamptz is null then
    raise exception 'evidência da conferência inválida' using errcode = '22023';
  end if;

  select array_agg(item ->> 'outcome'), count(*)::integer
  into outcomes, checked
  from jsonb_array_elements(cases) as item;

  if checked < 20
    or not (outcomes <@ array['ausente_da_lista', 'presente_exato',
      'presente_como_aditivo', 'presente_com_outro_sufixo'])
    or not exists (
      select 1 from jsonb_array_elements(cases) as item
      where item ->> 'cited_number' in ('338/2020', '308/2023')) then
    raise exception 'amostra da conferência incompleta' using errcode = '22023';
  end if;

  -- Qualquer caso presente na lista é defeito da regra, não do portal.
  verdict := case
    when outcomes <@ array['ausente_da_lista'] then 'approved'
    else 'changes_requested'
  end;

  return query
  insert into editorial.editorial_reviews as review (
    target_type,
    target_id,
    reviewer_subject,
    review_type,
    decision,
    rationale,
    checklist
  )
  values (
    'finance.contract_citation_comparison',
    md5('contract-citation-comparison/1.0.0')::uuid,
    'automated:contract-citation-agent-check/1.0.0',
    'editorial',
    verdict,
    format('Conferência automática por agente, não revisão humana: %s caso(s) procurados '
      || 'na lista de contratos do portal lida em %s (%s contratos); resultados %s.',
      checked, p_evidence ->> 'read_at', p_evidence ->> 'portal_contracts',
      p_evidence -> 'counts'),
    jsonb_build_object(
      'methodology_version', 'contract-citation-comparison/1.0.0',
      'label', 'conferência automática por agente, não revisão humana',
      'adr', '0096',
      'evidence', p_evidence)
  )
  returning review.decision, review.reviewed_at, checked;
end;
$function$;

revoke all on function finance.record_contract_citation_agent_check(jsonb)
  from public, anon, authenticated;

comment on function finance.record_contract_citation_agent_check(jsonb) is
  'Grava a conferência automática por agente da amostra do ADR 0096 (scripts/check-contract-citations.mjs); a decisão é calculada por código a partir da evidência.';

commit;
