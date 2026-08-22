begin;

grant execute on function api.get_public_payroll_regime_breakdown(date)
  to collector_worker;

comment on function api.get_public_payroll_regime_breakdown(date) is
  'Detalhamento mensal agregado por regime/vínculo. A role técnica recebe apenas execução desta projeção sanitizada para confirmar a completude do próprio lote.';

commit;
