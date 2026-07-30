# ADR 0005 — Análise determinística e publicação humana

- Estado: Aceita
- Data: 2026-07-30

## Contexto

Análises financeiras e sinais sobre pessoas podem produzir dano reputacional.
Modelos generativos não fornecem repetibilidade suficiente para cálculos ou
decisão editorial.

## Decisão

Totais, reconciliações e anomalias serão código determinístico versionado,
testado e executado sobre snapshot identificável. IA pode criar candidato ou
explicação, sempre registrada como sugestão. Nenhum achado/análise é publicado
sem revisão humana; conteúdo reputacional exige revisão reforçada.

## Consequências

- resultados reproduzíveis;
- separação estrutural entre achado e insight publicado;
- mais custo editorial e lançamento mais lento;
- menor risco de converter correlação em acusação.

## Alternativas

- Score automático de pessoas: rejeitada.
- LLM como juiz/cálculo: rejeitada.
