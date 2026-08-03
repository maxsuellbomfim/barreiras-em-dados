# ADR 0028 — Evidências por vínculo PNCP

## Status

Proposto para revisão no PR desta etapa.

## Contexto

O resumo de execução financeira informa quando existem registros normalizados,
mas o cidadão precisa conferir a origem de cada vínculo. Uma contagem sem URL,
data e hash não é suficiente para auditoria independente.

## Decisão

Para cada contratação, contrato, empenho, liquidação ou pagamento vinculado,
o resumo público poderá retornar até 20 evidências com:

- tipo do registro e identificador técnico do registro bruto;
- URL HTTPS da fonte oficial;
- hash SHA-256 do artefato preservado;
- data de coleta;
- versão do coletor e do parser.

A resposta não inclui cabeçalhos sensíveis, cookies, tokens, chaves ou caminhos
internos do armazenamento. O limite de 20 reduz o tamanho da resposta; o acervo
bruto continua imutável e completo.

## Consequências

- A página de compras oferece uma trilha de auditoria por vínculo.
- Hashes permitem verificar se o artefato preservado mudou.
- Ausência de evidência continua sendo um estado explícito, não uma prova de
  ausência do gasto.
- O contrato do resumo passa a `pncp-execution-links/1.1.0`.

## Próximo passo

Adicionar visualização do documento preservado quando existir objeto público no
Storage, mantendo a fonte oficial como referência primária.
