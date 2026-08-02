# Revisão do vínculo territorial por votação

Data: 2026-08-02

## Escopo

O recorte municipal já preservado pelo coletor do TSE agora possui uma
projeção pública em `api.get_tse_barreiras_votes`. A página
`/representantes` exibe candidaturas com votação registrada em Barreiras por
ano, turno, cargo, partido, número, situação, zonas somadas e votos.

## Regras determinísticas

- A chave é o identificador oficial da candidatura (`sq_candidato`) combinado
  com pleito e turno; nome nunca é chave.
- O coletor soma votos das zonas por código de candidatura antes da
  persistência.
- A projeção mostra somente o recorte municipal agregado, não a base eleitoral
  nacional integral.
- Valores de votos e zonas são validados como inteiros não negativos.
- O número exibido é votação registrada, não nota de desempenho, patrimônio,
  culpa ou prova de irregularidade.

## Limitações

- A fatia inicial usa o recorte de votação nominal, não o cadastro completo de
  candidatos nem bens e contas eleitorais.
- O vínculo eleitoral não significa que a pessoa represente exclusivamente
  Barreiras depois da eleição.
- Ausência de coleta é apresentada como indisponibilidade ou preparação.

## Verificações previstas

- migration/seed reaplicáveis;
- `pnpm --filter @barreiras-em-dados/web typecheck`;
- `pnpm --filter @barreiras-em-dados/web build`;
- `npm test` e `git diff --check`.
