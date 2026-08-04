# ADR 0037 — Aliases de representantes com revisão humana

## Contexto

Autoria legislativa chega de fontes municipais como texto livre. Caixa alta,
nome de urna, apelido, coautoria, grafias diferentes e homônimos podem aparecer
para a mesma pessoa — ou para pessoas diferentes. Uma comparação textual direta
não é uma identidade civil.

## Decisão

O Barreiras 360 manterá três camadas separadas:

1. o nome publicado pela Câmara, preservado sem alteração;
2. uma sugestão assistida por IA, limitada aos representantes oficiais já
   identificados e registrada em `political.representative_alias_suggestions`;
3. um alias aceito por revisor ativo, com evidência e auditoria, em
   `political.representative_aliases`.

A IA pode classificar `match`, `ambiguous` ou `no_match`, mas não pode criar ID,
aceitar a sugestão, alterar a autoria da fonte ou publicar uma associação. O
prompt é fechado: somente IDs fornecidos pelo banco podem ser escolhidos. A
revisão aceita exige justificativa e preserva os registros anteriores.

## Consequências

- Casos de Barreiras podem ser analisados em lote sem transformar semelhança em
  prova.
- A fila de revisão fica auditável por provedor, modelo, prompt, evidência e
  decisão.
- Até que um alias seja aceito, o portal continua exibindo e filtrando o texto
  original, sem consolidar grafias.
- A tabela de aliases poderá alimentar uma projeção pública futura somente por
  IDs oficiais e após revisão.

