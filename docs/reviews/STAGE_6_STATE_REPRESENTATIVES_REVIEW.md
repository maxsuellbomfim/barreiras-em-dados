# Revisão da projeção de deputados estaduais

Data: 2026-08-02

## Escopo

A coleta já existente da Assembleia Legislativa da Bahia (ALBA) agora possui
uma projeção pública em `api.get_state_representatives` e é exibida em
`/representantes`.

Cada registro usa o identificador oficial da ALBA como chave e publica somente
nome, URL oficial do perfil e data da coleta. O CPF e outros dados pessoais não
entram na projeção.

## Limites explícitos

- A listagem estadual não é apresentada como representação exclusiva de
  Barreiras.
- Vínculo territorial, votos no município, emendas e atuação parlamentar ainda
  exigem coletores e fontes próprias.
- Falha ou ausência de coleta aparece como indisponibilidade ou preparação;
  nunca como zero, ausência de mandato ou avaliação da pessoa.
- O parser exige URL oficial da ALBA e identificador numérico estável.

## Verificações previstas

- validar migration e seed;
- executar `pnpm --filter @barreiras-em-dados/web typecheck`;
- executar `pnpm --filter @barreiras-em-dados/web build`;
- executar `npm test` e `git diff --check`.
