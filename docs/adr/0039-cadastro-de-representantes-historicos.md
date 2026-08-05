# ADR 0039 — Cadastro separado de representantes históricos

Data: 05/08/2026. Status: proposto.

## Contexto

Atos e indicações antigos citam vereadores que não aparecem na lista eleitoral
da legislatura atual. A ausência no conjunto atual não prova que a autoria esteja
errada. Misturar esses nomes aos perfis em exercício produz vínculos falsos e
torna a fila de revisão difícil de interpretar.

## Decisão

- Criar um registro próprio para representantes históricos, separado do cadastro
  de candidatos e vereadores atuais.
- Permitir período de mandato, situação histórica, fonte, registro bruto e nota
  de evidência por pessoa.
- Guardar aliases históricos em tabela própria, com fonte e trilha de aprovação.
- Sugestões de alias podem apontar para um registro histórico, mas só depois de
  revisão e evidência suficiente.
- A função pública retorna somente registros com `editorial_status = approved`.
- Linhas `draft` e `source_pending` permanecem fora do site até a coleta de uma
  fonte oficial verificável.
- Nenhum nome é rejeitado apenas porque não está na lista eleitoral atual.

## Consequências

- A página pública poderá separar “em exercício” de “histórico” sem apagar atos
  antigos.
- A revisão humana continua necessária para ligar variantes a uma pessoa.
- O próximo coletor deverá pesquisar legislaturas e páginas históricas da Câmara,
  preservando cada resposta bruta e o período coberto.
