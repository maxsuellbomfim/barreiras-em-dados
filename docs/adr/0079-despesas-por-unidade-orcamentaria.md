# ADR 0079 — Despesas por unidade orçamentária literal

## Status

Aceita em 23 de agosto de 2026.

## Contexto

Os demonstrativos municipais de execução da despesa identificam, antes das
linhas contábeis, a unidade orçamentária responsável. Uma auditoria dos PDFs
oficiais de dezembro de 2022, dezembro de 2024 e julho de 2026 confirmou 25,
27 e 29 unidades, respectivamente. Os códigos e a estrutura administrativa
mudam entre exercícios; uma lista fixa de secretarias produziria associações
históricas incorretas.

## Decisão

Persistir em `finance.expense_line_budget_units` a atribuição literal e
versionada de cada linha ao código e nome de unidade encontrados no mesmo PDF.
Toda atribuição conserva o registro bruto, o artefato, a versão metodológica e
uma evidência própria. Um gatilho rejeita linhagem que não coincida com a linha
e o relatório de despesa.

A RPC `api.get_public_expense_budget_unit_summary(uuid)` agrega empenho,
liquidação e pagamento somente para o relatório vigente, validado e publicado.
Percentuais são liberados apenas quando todas as linhas têm uma unidade, cada
código possui um único nome literal no relatório e a soma paga coincide
exatamente com o total do documento.

O layout de 2023 e 2024 pode concatenar `Fonte` e `Fonte TC` no texto extraído.
O parser 1.2.0 aceita o token literal de oito dígitos e exige reconciliação
exata das 12 colunas das linhas contra o total declarado. Uma correção de
parser nunca sobrescreve o resultado antigo: cria uma nova versão do relatório,
aponta `supersedes_id` para a anterior e preserva a mesma linhagem documental.

A visão anual agrupa pelo código apenas dentro do mesmo exercício. Mudança
material de nome para o mesmo código bloqueia o ranking até reconciliação.
Mês sem atribuição integral fica sem valor; `R$ 0,00` só aparece quando um
relatório integralmente reconciliado comprova que a unidade não ocorreu.

## Consequências

O portal pode responder qual órgão, secretaria, fundo ou gabinete executou os
pagamentos, sem inferir pela descrição da despesa. Unidade orçamentária não
significa que o titular gastou pessoalmente o valor, não prova entrega e não
avalia a qualidade da política pública.

O catálogo observado contém 55 demonstrativos entre 2022 e 2026. A ausência de
2021 nessa fonte permanece uma lacuna explícita e não será preenchida por
estimativa.

## Verificação

- parser testado com cabeçalho obrigatório antes de cada linha;
- quatro PDFs oficiais representativos de 2023 a 2026 reconciliados coluna a
  coluna com o total declarado;
- replay idempotente rejeita divergência com atribuição já publicada;
- teste PGlite cobre RLS, privilégios, linhagem e reconciliação da RPC;
- agregação anual usa centavos inteiros e conserva PDF e SHA-256 por mês;
- testes Node, Python, migrations, typecheck e build web.
