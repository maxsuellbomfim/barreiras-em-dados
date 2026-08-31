begin;

-- A mesma role tecnica recebeu politicas permissivas separadas para conflitos
-- de obrigacoes publicas e demonstrativos de despesas. O PostgreSQL combina
-- politicas permissivas com OR; consolidar os predicados mantem o acesso
-- efetivo e evita que futuras regras sejam avaliadas em paralelo por engano.

drop policy if exists collector_worker_source_conflicts_select
on evidence.source_conflicts;
drop policy if exists collector_worker_source_conflicts_insert
on evidence.source_conflicts;
drop policy if exists collector_worker_expense_report_conflicts_select
on evidence.source_conflicts;
drop policy if exists collector_worker_expense_report_conflicts_insert
on evidence.source_conflicts;

create policy collector_worker_source_conflicts_select
on evidence.source_conflicts
for select to collector_worker
using (
  (
    target_type = 'finance.public_obligations'
    and field_name = 'payments_prior_amount'
  )
  or
  (
    target_type = 'finance.expense_reports'
    and (
      field_name in (
        'total_fixed_amount', 'total_additions_amount',
        'total_reductions_amount', 'total_updated_amount',
        'total_committed_period_amount', 'total_committed_to_date_amount',
        'total_liquidated_period_amount', 'total_liquidated_to_date_amount',
        'total_paid_period_amount', 'total_paid_to_date_amount',
        'total_unpaid_committed_amount', 'total_balance_amount'
      )
      or field_name ~ '^budget_unit_subtotal:[0-9]{6,8}:[a-z_]+_amount$'
    )
  )
);

create policy collector_worker_source_conflicts_insert
on evidence.source_conflicts
for insert to collector_worker
with check (
  (
    target_type = 'finance.public_obligations'
    and field_name = 'payments_prior_amount'
    and status = 'open'
  )
  or
  (
    target_type = 'finance.expense_reports'
    and status = 'open'
    and (
      field_name in (
        'total_fixed_amount', 'total_additions_amount',
        'total_reductions_amount', 'total_updated_amount',
        'total_committed_period_amount', 'total_committed_to_date_amount',
        'total_liquidated_period_amount', 'total_liquidated_to_date_amount',
        'total_paid_period_amount', 'total_paid_to_date_amount',
        'total_unpaid_committed_amount', 'total_balance_amount'
      )
      or (
        field_name = concat(
          'budget_unit_subtotal:',
          first_value ->> 'budget_unit_code',
          ':',
          first_value ->> 'field_name'
        )
        and first_value ->> 'scope' = 'budget_unit_subtotal'
        and second_value ->> 'scope' = 'budget_unit_subtotal'
        and first_value ->> 'budget_unit_code' ~ '^[0-9]{6,8}$'
        and first_value ->> 'budget_unit_code'
          = second_value ->> 'budget_unit_code'
        and first_value ->> 'budget_unit_name'
          = second_value ->> 'budget_unit_name'
        and nullif(first_value ->> 'budget_unit_name', '') is not null
        and first_value ->> 'field_name' ~ '^[a-z_]+_amount$'
        and first_value ->> 'field_name' = second_value ->> 'field_name'
        and second_value ->> 'difference_amount'
          ~ '^-?[0-9]+([.][0-9]{1,2})?$'
        and abs((second_value ->> 'difference_amount')::numeric) <= 0.10
      )
    )
  )
);

comment on policy collector_worker_source_conflicts_select
on evidence.source_conflicts is
  'Leitura tecnica limitada aos conflitos financeiros explicitamente suportados.';

comment on policy collector_worker_source_conflicts_insert
on evidence.source_conflicts is
  'Insercao tecnica limitada a conflitos financeiros abertos e validados por tipo.';

commit;
