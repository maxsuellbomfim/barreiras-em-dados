# ADR 0051 — Resultado operacional dinâmico na página de finanças

## Status

Aceito

## Contexto

A página pública de finanças exibia uma mensagem fixa de que ainda não havia classificação do resultado, mesmo quando já existia um fechamento mensal operacional. Isso confundia o leitor e não diferenciava uma diferença operacional positiva ou negativa.

## Decisão

O cabeçalho público passa a ser derivado do fechamento mensal mais recente. A interface informa se faltam dados, se há reconciliação pendente ou se os pagamentos ficaram acima/abaixo da receita declarada. A diferença recebe a mesma sinalização visual já usada para valores positivos e negativos.

## Limites

Esse resultado continua sendo estritamente operacional: receita declarada menos pagamentos do mesmo período. Não é chamado de superávit, déficit fiscal ou saldo bancário e não substitui a integração futura de dívidas, restos a pagar e empréstimos.

## Consequências

- O cidadão vê o estado real do último fechamento sem interpretar ausência de dados como zero.
- O texto explicativo permanece determinístico e não depende de IA para calcular valores.
- A regra é coberta por contrato de interface e mantém a metodologia pública.
