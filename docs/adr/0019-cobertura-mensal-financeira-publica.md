# ADR 0019 — Cobertura mensal financeira explícita

## Status

Aceito — primeira projeção pública.

## Decisão

Expor `api.get_public_finance_coverage` como uma grade mensal da Prefeitura a
partir de 2021 até o mês atual. Cada competência informa separadamente a
presença de relatório validado de receita e de despesa, com os estados:

- `complete`: há as duas fontes;
- `revenue_only` ou `expense_only`: uma fonte ainda falta;
- `needs_review`: há múltiplos relatórios na competência;
- `missing`: nenhum documento validado foi publicado.

A projeção não transforma ausência em zero e não soma linhas hierárquicas.
Valores continuam sendo exibidos apenas nas projeções financeiras validadas.

## Consequências

- O portal consegue dizer claramente onde a série ainda está incompleta.
- O cidadão pode diferenciar “não encontrado” de “zero”.
- O inventário é recalculado a cada consulta, sem apagar históricos.
- O período inicial de 2021 é uma expectativa metodológica pública, não uma
  afirmação de que todas as fontes municipais já estavam disponíveis naquele
  ano.

## Próxima etapa

Adicionar filtros por ano e fonte no painel administrativo e iniciar o
cruzamento determinístico entre compras públicas, contratos e fornecedores.
