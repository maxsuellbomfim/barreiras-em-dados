begin;

-- Revisões de agente (automated:agent/commitment-link-review/1.0.0, ADR 0099)
-- caíam no "else human" e apareceriam como revisão humana em /licitacoes.
-- Qualquer revisor automatizado passa a sair como "automated".
do $patch$
declare
  definition text := pg_get_functiondef('api.get_public_commitment_contract_links(text[])'::regprocedure);
  patched text;
begin
  patched := replace(
    definition,
    $x$        else 'human'$x$,
    $x$        when review.reviewer_subject like 'automated:%'
        then 'automated'
        else 'human'$x$
  );
  if patched = definition then
    raise exception 'ramo else human não encontrado';
  end if;
  execute patched;
end;
$patch$;

notify pgrst, 'reload schema';

commit;
