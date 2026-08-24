# ADR 0082 — Catálogo mensal do TCM-BA antes dos PDFs

## Status

Aceito em 24 de agosto de 2026.

## Contexto

O e-TCM publica milhares de documentos por competência em uma interface JSF
com estado de sessão e paginação própria. Baixar todo o acervo antes de conhecer
o universo criaria custo, risco de repetição e cobertura impossível de auditar.
Além disso, o nome de um PDF não demonstra seu conteúdo nem autoriza publicar
um valor financeiro.

## Decisão

O Barreiras 360 coleta primeiro o catálogo mensal completo. Cada resposta HTML
é preservada por hash e vinculada aos registros brutos de submissão e documento.
A partição só recebe estado `complete` quando a contagem informada pela fonte e
a quantidade integralmente percorrida forem iguais; ausência comprovada recebe
`empty`, e qualquer divergência recebe falha.

O workflow permanece manual e exige competência inicial e final explícitas.
Nenhum registro desse estágio possui projeção pública financeira. O download de
PDFs será uma etapa posterior, priorizada por famílias documentais, idempotente
e ligada ao item exato do catálogo.

## Consequências

- o backfill pode ser retomado por competência sem baixar arquivos repetidos;
- períodos vazios são distintos de períodos não coletados;
- todo documento conhecido tem origem e página de catálogo verificáveis;
- valores só serão publicados após preservação do PDF, extração determinística
  e reconciliação;
- falhas HTTP finais ainda dependem do registro sanitizado do controle central
  até que respostas malsucedidas tenham corredor bruto próprio.
