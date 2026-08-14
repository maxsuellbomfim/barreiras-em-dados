# ADR 0063 — Prazos operacionais de atualização das fontes

## Status

Aceito em 13/08/2026.

## Contexto

O painel administrativo já separava a tentativa mais recente da última
atualização válida, mas ainda não possuía um critério documentado para decidir
quando uma fonte estava atrasada. Aplicar o mesmo prazo a fontes diárias,
semanais, eleitorais e orçamentárias criaria alarmes falsos.

## Decisão

Cada endpoint passa a declarar uma política versionada:

- `scheduled`: possui intervalo esperado e tolerância operacional;
- `publication_driven`: muda quando há nova publicação oficial e não recebe
  alerta contínuo;
- `manual`: ainda não possui rotina programada e não recebe alerta contínuo.

O prazo é contado desde a última partição `complete` ou `empty` vinculada a uma
execução bem-sucedida. Uma tentativa posterior com falha não renova o prazo e
também não apaga a atualização válida anterior.

Rotinas diárias recebem 24 horas de intervalo e 24 horas de tolerância. Rotinas
semanais recebem 168 horas de intervalo e 48 horas de tolerância. Os valores
seguem os agendamentos versionados em `.github/workflows`; uma alteração de
cadência exige nova versão da política.

A RPC `api.get_collection_health_v3` calcula os estados `current`, `overdue`,
`never_updated` e `not_monitored`. Ela permanece `SECURITY DEFINER`, mas valida
`api.is_active_reviewer()`, remove `EXECUTE` de `public` e `anon` e concede a
chamada somente a `authenticated`.

## Consequências

- A equipe distingue falha recente, dado válido antigo e atraso persistente.
- Fontes eleitorais, anuais ou sob demanda não são acusadas de atraso por um
  relógio arbitrário.
- “Atrasada” é um diagnóstico operacional interno, não uma avaliação da
  qualidade, intenção ou legalidade da fonte pública.
- Endpoints programados sem nenhuma conclusão válida aparecem como “nenhuma
  atualização válida registrada” e exigem atenção.
