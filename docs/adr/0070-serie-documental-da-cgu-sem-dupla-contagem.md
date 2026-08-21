# ADR 0070 — Série documental da CGU sem dupla contagem

## Contexto

O arquivo agregado de emendas parlamentares da CGU comprova execução
regionalizada em Barreiras até 2023 no retrato auditado, mas não contém linhas
municipais de 2024 em diante. A CGU mantém outra fonte oficial, anual e
detalhada por documento, que contém empenhos, liquidações e pagamentos mais
recentes.

Usar somente o agregado deixaria a página desatualizada. Somar as duas fontes
criaria risco de dupla contagem, pois elas descrevem etapas sobrepostas da mesma
execução orçamentária.

## Decisão

- Preservar os ZIPs anuais **Emendas Parlamentares por Documento** de 2021 até
  o exercício corrente em armazenamento privado e imutável por hash.
- Selecionar Barreiras exclusivamente pelo código IBGE `2903201` publicado na
  linha.
- Registrar ano da emenda e ano/data do documento em campos diferentes.
- Manter empenho, liquidação e pagamento como estágios mutuamente distintos.
- Descartar somente duplicatas exatas; preservar parcelas diferentes do mesmo
  documento.
- Produzir ranking determinístico próprio, somando empenhos e pagamentos em
  colunas separadas.
- Nunca somar a série documental ao agregado da CGU ou ao Transferegov.
- Publicar favorecido nominal, mas não expor o identificador pessoal ou
  empresarial contido no arquivo bruto.

## Consequências

- A execução federal posterior a 2023 passa a ser atualizável sem inventar
  continuidade no arquivo agregado.
- O cidadão consegue conferir cada movimentação e sua fonte oficial.
- O ano da movimentação não será confundido com o ano de autoria da emenda.
- Valores ausentes continuam significando "não encontrados nesta fonte", não
  zero.
- A nova visão informa execução financeira documental; não prova entrega do
  objeto, regularidade ou mérito político.
