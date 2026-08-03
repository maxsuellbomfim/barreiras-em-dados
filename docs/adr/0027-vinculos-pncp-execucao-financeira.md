# ADR 0027 — Vínculos determinísticos do PNCP à execução financeira

## Status

Proposto para revisão no PR desta etapa.

## Contexto

O PNCP informa a contratação e seus resultados. Contratos, empenhos,
liquidações e pagamentos são armazenados em entidades normalizadas separadas.
Um texto parecido ou um valor semelhante não é evidência suficiente para ligar
esses registros.

## Decisão

O portal exibirá um resumo de execução somente quando
`procurement.procurements.external_id` for exatamente igual ao
`numeroControlePNCP` da contratação. A função pública `get_pncp_execution_summary`
agrega apenas versões atuais (registros que não foram sucedidos) e calcula
valores líquidos de cancelamentos e reversões por código determinístico.

Quando a contratação ainda não estiver normalizada, ou não houver execução
ligada, o portal exibirá estado explícito. Isso não será interpretado como
ausência de despesa, quitação ou irregularidade.

## Consequências

- Contratações passam a mostrar contratos, empenhos, liquidações e pagamentos
  relacionados quando a chave oficial existir.
- O resumo não substitui os documentos originais nem cria associação por IA.
- A cobertura pode permanecer vazia enquanto os normalizadores dessas entidades
  não tiverem registros; essa ausência será visível ao cidadão.
- A versão do contrato público passa a `pncp-procurements/1.4.0` e a do resumo
  a `pncp-execution-links/1.0.0`.

## Próximo passo

Adicionar links de evidência para os documentos brutos de cada entidade e medir
separadamente cobertura de contrato, empenho, liquidação e pagamento.
