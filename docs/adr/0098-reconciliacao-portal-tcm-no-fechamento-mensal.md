# ADR 0098 — Reconciliação entre portal e TCM-BA no fechamento mensal

## Status

Aceita em 13/10/2026.

## Contexto

A extração dos demonstrativos analíticos do TCM-BA chegou a 2022. A partir
daí, cada competência passa a ter dois demonstrativos oficiais publicados:

- o do portal de transparência da Prefeitura (`public-expense-pdf`,
  `public-revenue-pdf`);
- o da prestação de contas mensal ao TCM-BA (`tcm-ba-analytical-expense`,
  `tcm-ba-analytical-revenue`).

O fechamento mensal `monthly-finance-closure/1.1.0` e a cobertura
`finance-coverage/1.1.0` contavam documentos. Com duas fontes, janeiro e
fevereiro de 2022 passaram a "revisão necessária", saíram do sitemap e tiveram
a receita somada em dobro (R$ 96 mi em vez de R$ 48,2 mi em janeiro). Com o
avanço do TCM-BA, todos os meses de 2022 em diante cairiam no mesmo estado,
contrariando o gate de `docs/reviews/MUNICIPAL_REVENUE_2022_RECONCILIATION.md`:
um relatório de receita e um de despesa por competência.

Medição em 13/10/2026:

| Competência | Fonte | Receita declarada | Pago | Empenhado | Liquidado |
| --- | --- | ---: | ---: | ---: | ---: |
| 2022-01 | portal | 48.233.949,09 | 23.514.399,12 | 339.330.577,65 | 25.933.266,48 |
| 2022-01 | TCM-BA | 48.233.949,09 | 22.178.075,21 | 323.842.754,38 | 24.596.942,57 |
| 2022-02 | portal | 65.755.170,88 | 41.073.995,54 | 32.402.291,68 | 41.292.924,90 |
| 2022-02 | TCM-BA | 65.755.170,88 | 39.759.885,72 | 32.336.582,08 | 39.930.034,46 |

A receita coincide ao centavo. Na despesa, a diferença em janeiro é exatamente
a da unidade 010101 (Câmara Municipal de Barreiras) no demonstrativo do
portal: R$ 1.336.323,91 pagos e liquidados e R$ 15.487.823,27 empenhados. O
portal publica a despesa consolidada do município (Executivo e Legislativo); a
prestação ao TCM-BA, só a do Executivo.

## Decisão

`monthly-finance-closure/1.2.0`:

1. **Receita:** relatórios da mesma competência com o mesmo total declarado
   são o mesmo demonstrativo e contam uma vez.
2. **Despesa:** com um demonstrativo do portal e um do TCM-BA, vale o do
   portal (consolidado) quando o portal sem o órgão 01 (Legislativo, pela
   alocação vigente de cada linha à unidade orçamentária) confere ao centavo
   com o TCM-BA em pago, empenhado e liquidado. Se não conferir, a competência
   segue em revisão.
3. Demonstrativos da mesma fonte com os mesmos três totais contam uma vez.
4. **Escopo explícito:** a nota de cada mês diz se os pagamentos são
   consolidados (incluem a Câmara) ou só do Executivo. Este é o caso dos meses
   que só têm a prestação ao TCM-BA, como 2021 inteiro e abril de 2023.

`finance-coverage/1.2.0` conta os demonstrativos já reconciliados pelo
fechamento, em vez de documentos.

O detalhe mensal continua listando todos os documentos como evidência: os do
portal e os do TCM-BA.

## Consequências

- 2022-01 e 2022-02 voltaram a `operational`, com a receita contada uma vez.
  Nenhuma outra competência mudou de valor ou de estado; só ganhou a nota de
  escopo (comparação com a 1.1.0 em produção, mês a mês).
- A série tem dois escopos e diz qual é em cada mês. Somar meses de 2021 (só
  Executivo) com meses de 2022+ (consolidado) exige descontar a Câmara.
- Uma divergência que não seja explicada pelo Legislativo continua visível
  como revisão necessária. Nenhum valor é escolhido sem a conferência.
