# Reconciliação das receitas municipais de 2022

Data da validação: 1º de setembro de 2026.

## Lacuna comprovada

Os doze PDFs de Execução da Receita de 2022 estavam preservados, mas nenhuma
competência aparecia na projeção pública normalizada. As despesas dos mesmos
meses já estavam publicadas. Por isso os fechamentos mensais de 2022 apareciam
como incompletos apesar de as duas famílias documentais existirem.

## Causa

O layout histórico é o **Demonstrativo de Receita Orçamentária Analítico por
Fonte**. Nele:

- o código de três dígitos da fonte é extraído colado ao último valor da linha;
- um mesmo código de receita aparece em mais de uma fonte;
- o publicador anterior rejeitava essas repetições e depois excluía para sempre
  qualquer artefato que já tivesse uma tentativa falha;
- mesmo com falhas, o comando terminava com código de sucesso.

## Correção

- O parser separa o código da fonte do valor monetário sem ponto flutuante.
- Parcelas com o mesmo código e a mesma descrição são somadas por campo. Uma
  descrição divergente continua bloqueando a publicação.
- A metodologia passou a `public-revenue-pdf/1.2.0` e o job a
  `financial_revenue_publication/1.2.0`, preservando o histórico da tentativa
  antiga.
- Falhas voltam a ser tentadas até o limite de `raw.extraction_jobs`; depois
  seguem para `dead_lettered`.
- Qualquer documento que ainda precise de revisão faz o workflow falhar, em vez
  de produzir um selo verde sem publicação.

## Prova anterior à publicação

Os doze PDFs oficiais públicos, de janeiro a dezembro de 2022, foram baixados
novamente e processados localmente com a mesma extração usada no worker. Todos
passaram. Cada competência gerou 281 códigos agregados e manteve o total mensal
declarado no documento. Essa prova valida o parser; a publicação em produção
ainda deve ser confirmada pelos RPCs públicos após o replay do workflow.

## Gate de produção

O replay só será considerado concluído quando:

1. o workflow terminar verde sem `needs_review`;
2. cada mês de 2022 tiver exatamente um relatório de receita e um de despesa;
3. `api.get_public_monthly_finance_closures` retornar `operational` para as doze
   competências;
4. cada linha pública mantiver vínculo ao PDF preservado e à origem bruta.

