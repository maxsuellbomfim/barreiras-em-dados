-- Finanças: memória de trabalho para as RPCs mais usadas (página inicial e
-- /financas). A deduplicação de versões de receita ordena ~25 mil linhas e,
-- com o work_mem padrão, transbordava para arquivo temporário (3,5 MB). Com
-- cache frio, isso e a leitura das tabelas levavam o fechamento mensal a
-- ~2,4 s, perto do statement_timeout de 3 s do papel anon; quando estourava,
-- o cartão "entrou/saiu" sumia da página inicial. Nenhuma regra muda.

alter function api.get_public_monthly_finance_closures_calculated(integer, smallint)
  set work_mem = '16MB';

alter function api.get_public_revenues(integer, smallint)
  set work_mem = '16MB';

alter function api.get_public_finance_coverage_calculated(integer, smallint, smallint)
  set work_mem = '16MB';
