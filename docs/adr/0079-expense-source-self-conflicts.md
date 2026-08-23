# ADR 0079 — Divergências aritméticas internas em balancetes de despesa

## Status

Aceita em 23 de agosto de 2026.

## Contexto

Há balancetes oficiais em que cada linha fecha exatamente com o subtotal da sua
unidade orçamentária, mas o `Total` geral impresso difere da soma desses
subtotais por alguns centavos. Tratar isso como falha do parser impede a
publicação de campos independentes que foram reconciliados; substituir o valor
oficial apagaria uma divergência da própria fonte.

## Decisão

O relatório só é publicável quando todas as doze colunas de cada unidade fecham
exatamente com o respectivo `Total da Unidade`. Se essa prova existir, uma
diferença entre a soma das linhas e o `Total` geral será preservada em
`evidence.source_conflicts`, com os dois valores, diferença, evidências e hash.

O portal exibirá a divergência em linguagem simples. Os campos que fecharam
continuam publicados; o valor divergente não é corrigido, estimado nem usado
para acusação automática. Sem subtotais oficiais completos, qualquer diferença
continua bloqueando a publicação.

## Consequências

- divergências documentais deixam de ser confundidas com erro de coleta;
- o cidadão consegue conferir o valor geral e a soma comprovada;
- correções futuras da Prefeitura geram nova versão auditável;
- uma divergência é informação de qualidade da fonte, não prova de ilegalidade.
