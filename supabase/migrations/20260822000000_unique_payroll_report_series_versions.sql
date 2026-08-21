begin;

-- A cadeia append-only precisa de uma única versão por órgão, espécie e mês,
-- inclusive quando dois workers tentam publicar a primeira versão ao mesmo
-- tempo. O publicador também serializa a série com advisory lock.
create unique index payroll_report_aggregates_series_version_unique_idx
on hr.payroll_report_aggregates (
  public_body_id, report_kind, reference_month, version
);

notify pgrst, 'reload schema';

commit;
