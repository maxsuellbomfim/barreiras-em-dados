# ADR 0017 — Fechamento mensal e inventário financeiro

## Status

Aceito

## Contexto

O portal já preserva PDFs financeiros e publica algumas linhas de receita e
relatórios de despesa, mas a população precisa de uma unidade de leitura mais
simples: um mês com cobertura, entradas, pagamentos e resultado operacional.
O painel administrativo também não mostrava quais documentos estavam apenas
preservados, quais falharam e quais já haviam sido publicados.

## Decisão

1. Exibir um fechamento mensal único em `api.get_public_monthly_finance_closures`.
2. Calcular a receita no nível do total declarado por documento, sem somar
   linhas hierárquicas que representam subtotais da mesma demonstração.
3. Calcular pagamentos a partir do relatório de despesa validado, sem somar
   empenho, liquidação e pagamento entre si.
4. Publicar a diferença apenas como **diferença operacional**. Ela não será
   chamada de superávit ou déficit fiscal enquanto não houver base comparável de
   todas as receitas, despesas, estornos e transferências.
5. Expor no admin `api.get_finance_ingestion_inventory`, restrito a revisores,
   com status, último erro, hash, fonte e quantidade de linhas publicadas.
6. Reservar a camada de comentários da IA para uma etapa posterior. A IA pode
   explicar números já calculados, mas não define totais nem altera o status de
   cobertura.

## Consequências

- O cidadão vê o mês como uma unidade, com detalhes técnicos em sanfona.
- Meses incompletos ou com múltiplos relatórios ficam marcados como parciais ou
  aguardando reconciliação.
- O admin passa a explicar por que um PDF ainda não aparece como dado público.
- Dívidas e empréstimos serão adicionados em uma entidade própria, com saldo,
  finalidade, contrato e evidência; não serão inferidos de um RGF isolado.
