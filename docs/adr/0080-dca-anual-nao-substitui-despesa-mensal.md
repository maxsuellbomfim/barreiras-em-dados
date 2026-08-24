# ADR 0080 — DCA anual não substitui despesa mensal municipal

- Status: aceito
- Data: 2026-08-24

## Contexto

O catálogo municipal de `pdc-resumo-execucao-da-despesa` observado contém
documentos de 2022 a 2026, mas não 2021. O módulo legado informa dados desde
2017; contudo, sua exportação JSON para 2021 respondeu erro interno da própria
fonte. Ao mesmo tempo, o SICONFI publica a Declaração das Contas Anuais (DCA) de
Barreiras para 2021 em formato estruturado e oficial.

Misturar essas granularidades produziria uma falsa continuidade: a DCA fecha o
exercício, enquanto os relatórios municipais sustentam competências e linhas de
execução mensal.

## Decisão

1. Coletar a DCA de `id_ente=2903201` desde 2021, preservando integralmente cada
   página JSON, URL, horários, SHA-256, versões, paginação e linhas literais.
2. Manter valores monetários como decimais textuais e aceitar sinais negativos
   publicados pela fonte, sem cálculo durante a aquisição.
3. Tratar a ausência/exportação quebrada de 2021 no portal municipal como
   `blocked`, não como zero nem como cobertura vazia.
4. Não preencher meses de 2021 com rateio, interpolação ou totais anuais da DCA.
5. Somente publicar totais anuais derivados após definir chaves literais por
   anexo, coluna e conta, com reconciliação e rótulo explícito “anual”.

## Consequências

- O acervo ganha uma fonte oficial adicional para auditoria anual de 2021.
- A população não verá um total anual apresentado como gasto de um mês.
- Divergências entre DCA e relatórios municipais poderão ser registradas como
  conflitos de fonte, sem escolher silenciosamente um vencedor.
- A lacuna mensal de 2021 permanece visível até que uma fonte municipal íntegra
  seja encontrada e validada.
