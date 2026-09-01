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
declarado no documento. Essa prova validou o parser antes do replay.

## Gate de produção

O replay só será considerado concluído quando:

1. o workflow terminar verde sem `needs_review`;
2. cada mês de 2022 tiver exatamente um relatório de receita e um de despesa;
3. `api.get_public_monthly_finance_closures` retornar `operational` para as doze
   competências;
4. cada linha pública mantiver vínculo ao PDF preservado e à origem bruta.

## Resultado em produção

O replay controlado foi concluído em 1º de setembro de 2026, sempre com limite
de um artefato por execução. Os doze workflows terminaram com
`published_rows=281`, `needs_review=0` e saída bem-sucedida:

| Competência | Execução do GitHub Actions | Receita declarada |
| --- | ---: | ---: |
| 2022-01 | 33541307984 | R$ 48.233.949,09 |
| 2022-02 | 33541114177 | R$ 65.755.170,88 |
| 2022-03 | 33540867846 | R$ 50.207.357,68 |
| 2022-04 | 33540679014 | R$ 61.705.688,20 |
| 2022-05 | 33540442623 | R$ 62.945.245,13 |
| 2022-06 | 33540223451 | R$ 62.885.032,19 |
| 2022-07 | 33540032287 | R$ 58.230.262,58 |
| 2022-08 | 33539807070 | R$ 57.288.400,64 |
| 2022-09 | 33539639877 | R$ 53.313.495,36 |
| 2022-10 | 33539437855 | R$ 62.707.941,23 |
| 2022-11 | 33539215962 | R$ 62.930.602,35 |
| 2022-12 | 33538754184 | R$ 66.774.647,14 |

A consulta pública a `api.get_public_monthly_finance_closures` retornou doze
competências, sem divergências: todas em `operational`, com exatamente um
relatório de receita, 281 rubricas de receita e um relatório de despesa. Os
totais acima coincidem com a prova local anterior ao replay.

O detalhe público de dezembro confirmou também a linhagem: um documento de
receita e um de despesa, ambos com URL oficial, SHA-256 do artefato normalizado
e SHA-256 do artefato bruto de origem. A metodologia pública permaneceu
`monthly-finance-closure/1.1.0` e a metodologia de evidência,
`public-monthly-finance-detail/1.0.0`.

**Gate final: aprovado (12/12).**
