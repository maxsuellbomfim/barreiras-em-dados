# ADR 0079 — Divergências aritméticas internas em balancetes de despesa

## Status

Aceita em 23 de agosto de 2026.

## Contexto

Há balancetes oficiais em que o `Total` geral impresso difere da soma das
linhas por alguns centavos. A auditoria de dezembro/2023 também encontrou uma
diferença de R$ 0,07 entre as linhas e o subtotal de uma única unidade, enquanto
as outras 299 combinações entre 25 unidades e 12 colunas fecharam exatamente.
Tratar esses casos documentados como falha do parser impede a publicação de
campos independentes; substituir o valor oficial apagaria uma divergência da
própria fonte.

## Decisão

O relatório só é publicável quando os subtotais oficiais cobrem exatamente as
unidades presentes nas linhas e as divergências de subtotal somam, em valor
absoluto, no máximo R$ 0,10 em todo o documento. Cada divergência aceita é
preservada individualmente em `evidence.source_conflicts`, com unidade, campo,
dois valores, diferença, evidências e hash. Acima desse limite conservador, o
relatório permanece bloqueado. Diferenças entre a soma das linhas e o `Total`
geral também são preservadas, nunca corrigidas.

O portal exibirá a divergência em linguagem simples. Os campos que fecharam
continuam publicados; o valor divergente não é corrigido, estimado nem usado
para acusação automática. Sem subtotais oficiais completos, qualquer diferença
continua bloqueando a publicação.

## Consequências

- divergências documentais deixam de ser confundidas com erro de coleta;
- o cidadão consegue conferir o valor geral e a soma comprovada;
- correções futuras da Prefeitura geram nova versão auditável;
- uma divergência é informação de qualidade da fonte, não prova de ilegalidade.

Em dezembro/2023, as 1.897 linhas somam R$ 332.401.153,73 em anulações; os 25
subtotais por unidade somam R$ 332.401.153,66; e o `Total` geral impresso informa
R$ 332.401.153,70. A unidade `030850` é a única divergente: subtotal de
R$ 141.419.262,90 e linhas de R$ 141.419.262,97. Esses três valores permanecem
identificáveis e conferíveis no documento de hash
`a859b6df74487fbef5291c7d88b6c59aec218cabc2a1f604a37485b955a65d31`.
