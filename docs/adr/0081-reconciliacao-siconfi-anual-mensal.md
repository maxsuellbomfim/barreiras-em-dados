# ADR 0081 — Reconciliação SICONFI anual × relatórios mensais

## Status

Aceito em 24 de agosto de 2026.

## Contexto

O Barreiras 360 publica tanto fechamentos mensais extraídos dos relatórios da
Prefeitura quanto os totais anuais da DCA no SICONFI. Os números podem diferir
por ajustes de encerramento, atualização posterior, restos a pagar ou cobertura
mensal incompleta. Exibir as séries sem explicar se elas conferem transfere ao
cidadão uma tarefa contábil difícil e pode induzir conclusões incorretas.

## Decisão

A projeção pública compara deterministicamente somente despesa empenhada,
liquidada e paga. Para cada exercício e estágio, o banco conta os meses com
valor, soma apenas quando os 12 meses estão presentes e classifica o resultado
como:

- `matched_exact`: soma mensal e DCA anual idênticas;
- `source_difference`: 12 meses presentes, mas os totais oficiais diferem;
- `incomplete_months`: cobertura menor que 12; nenhum total parcial é exibido
  como comparável.

Valores saem da RPC como texto decimal exato. A receita bruta anual não é
comparada automaticamente à receita mensal porque as fontes podem usar bases e
deduções diferentes. IA não participa da soma, comparação ou classificação.

## Consequências

- O cidadão vê se os relatórios mensais fecham com a declaração anual.
- Uma diferença fica documentada e verificável, mas nunca é chamada de déficit,
  erro ou irregularidade automaticamente.
- Anos incompletos informam os meses ausentes em vez de apresentar soma parcial.
- A interface destaca o último exercício e recolhe a conferência histórica por
  ano; meses ausentes aparecem por nome, e não somente por número.
- A página detalhada do exercício reúne DCA, meses e diferenças. Se a DCA ou a
  conferência não estiver disponível, publica a ausência expressamente e nunca
  a converte em zero ou concordância implícita.
- A interface explica que ajustes de encerramento são hipótese possível, não
  conclusão sobre a causa da diferença.
