# ADR 0084 — Persistência filha dos PDFs do TCM-BA

## Status

Aceita em 28/08/2026.

## Contexto

O catálogo mensal informa milhares de documentos, mas não contém os bytes dos
PDFs. Um download isolado por posição é inseguro: a listagem pode mudar entre a
catalogação e a abertura do documento, e o JSF exige um POST preparatório e um
GET na mesma sessão.

## Decisão

O download só parte de uma competência com cobertura `complete`, contagem
positiva e execução bem-sucedida. Antes de selecionar qualquer item, o coletor
exige posições contínuas, chaves oficiais únicas e concordância entre registros
brutos e `observed_records`.

Cada documento mantém a cadeia imutável:

```text
artefato HTML/XML do catálogo
  -> XML preparatório do botão de download
  -> PDF oficial
```

O XML e o PDF são gravados no bucket privado por SHA-256, relidos e comparados
em tamanho e hash antes do registro no PostgreSQL. O lote é sequencial, limitado
a cinco PDFs e a 30 requisições por minuto. A partição documental permanece
`partial` enquanto houver pendências e só se torna `complete` após a preservação
de todos os documentos esperados.

## Consequências

- drift de total, posição ou metadados bloqueia o documento;
- replay reutiliza objetos idênticos sem apagar tentativas anteriores;
- falha no meio do lote preserva a evidência já obtida e permite retomada;
- o comando não extrai valores nem autoriza publicação financeira;
- automação em massa depende primeiro de um piloto auditado no banco e Storage.