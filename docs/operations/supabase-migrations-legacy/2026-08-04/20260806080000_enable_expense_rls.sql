begin;

alter table finance.expense_reports enable row level security;
alter table finance.expense_lines enable row level security;

comment on table finance.expense_reports is
  'Relatorios de despesas preservados; acesso interno protegido por RLS e leitura publica somente pela API curada.';

comment on table finance.expense_lines is
  'Linhas de despesas preservadas; acesso interno protegido por RLS e leitura publica somente pela API curada.';

commit;
