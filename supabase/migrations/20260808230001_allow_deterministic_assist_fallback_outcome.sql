-- O fallback determinístico é uma etapa auditável da cascata assistida.
-- Desde a introdução desse fallback, o worker registra
-- `fallback_succeeded`, mas a restrição original antecede esse estado e
-- rejeita o diagnóstico depois de a publicação já ter sido concluída.
-- Mantemos todos os desfechos históricos e acrescentamos somente o estado
-- produzido pelo código vigente.

alter table audit.assist_diagnostics
  drop constraint if exists assist_diagnostics_outcome_check;

alter table audit.assist_diagnostics
  add constraint assist_diagnostics_outcome_check check (
    outcome in (
      'succeeded',
      'quota_exhausted',
      'transient',
      'contract',
      'missing_key',
      'exhausted',
      'unexpected',
      'fallback_succeeded'
    )
  );

comment on constraint assist_diagnostics_outcome_check
  on audit.assist_diagnostics is
  'Desfechos da cascata assistida, incluindo fallback determinístico.';
