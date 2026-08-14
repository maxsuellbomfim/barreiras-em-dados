# ADR 0068 — Cobertura observada e vínculo de emendas no perfil

## Status

Aceita em 14 de agosto de 2026.

## Contexto

O ranking por legislatura mostrava os valores encontrados, mas não informava
quantos registros tinham objeto, beneficiário, execução conciliada e evidência.
Os cards dos representantes também exibiam um resumo acumulado sem deixar a
legislatura explícita. Isso podia misturar períodos políticos ou levar o leitor
a interpretar uma lacuna da fonte como valor zero.

## Decisão

Publicar uma projeção agregada de cobertura por esfera e legislatura. Cada campo
recebe estado explícito de disponibilidade na fonte; campo não publicado fica
nulo. Nenhum identificador privado é retornado.

Vincular o resumo no card apenas por crosswalk oficial aprovado, com igualdade
exata de esfera e ID externo e com a data atual dentro do período da
legislatura. Nome, apelido ou similaridade textual não participam dessa decisão.
O card usa somente o top 10 já publicado para a legislatura e liga à página de
evidências da autoria.

## Consequências

- o cidadão vê o tamanho e os limites do recorte junto ao ranking;
- ausência de campo não é convertida em zero;
- troca de Casa legislativa não transfere emendas históricas para o cargo atual;
- cards fora do top 10 não recebem uma mensagem negativa ou conclusão sobre
  atuação parlamentar;
- totais e contagens continuam calculados deterministicamente no PostgreSQL;
- a função pública expõe somente agregados, com `SECURITY DEFINER`,
  `search_path` vazio, revogação de `public` e concessão explícita a
  `anon` e `authenticated`.
