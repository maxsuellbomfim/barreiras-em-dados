# Revisão do vínculo territorial por votação

Data: 2026-08-02

Atualização técnica: 2026-08-04

## Cobertura dos pleitos

- 2024: prefeito e vereadores de Barreiras.
- 2022: deputados estaduais e federais que receberam votos no município.
- O pacote nacional de 2022 mede 556.082.886 bytes; o coletor mantém limite
  de 640 MiB para preservar o recorte da Bahia sem guardar a base nacional.
- A coleta de um ano pode ser repetida idempotentemente e o workflow passa a
  sinalizar falha do TSE, em vez de mascará-la como sucesso.

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
