# ADR 0064 — Isolamento de falhas por modalidade no PNCP

## Contexto

A API de consulta do PNCP recebe uma modalidade por requisição. Em uma mesma
janela, algumas modalidades podem responder `204` corretamente enquanto outra
fica indisponível até o timeout. O comportamento anterior interrompia toda a
coleta na primeira falha e o cursor retroativo considerava execuções auxiliares
de páginas como se comprovassem a cobertura integral do período.

## Decisão

1. Cada modalidade é coletada de forma isolada.
2. Uma falha preserva as páginas válidas das demais modalidades e classifica a
   janela como `partial`.
3. Após duas modalidades consecutivas indisponíveis, as restantes são adiadas
   sem novas chamadas; falhas e adiamentos ficam separados no checkpoint.
4. Cada requisição da coleta controlada usa no máximo duas tentativas. O retry
   continua com backoff e nunca converte timeout em ausência de registros.
5. O cursor retroativo considera somente partições `complete` ou `empty`
   vinculadas a uma execução controlada `succeeded`.
6. Uma partição parcial é reprocessada de forma idempotente até que todas as
   modalidades tenham cobertura classificada.
7. Os subrecursos de itens/resultados e contratos/empenhos são independentes no
   workflow. Se o comando de itens terminar com falha não controlada, contratos
   e a normalização ainda serão executados; ao final, o workflow permanece com
   falha explícita para não esconder a interrupção.
8. Dentro do backlog de itens, uma contratação ou resultado indisponível é
   adiado individualmente. Os demais controles continuam, o checkpoint volta ao
   início do backlog para não pular o controle falho e a partição fica `partial`.

## Consequências

- Uma degradação localizada do PNCP não descarta dados oficiais já recebidos.
- O workflow pode terminar sem erro de processo enquanto o painel mantém a
  cobertura parcial visível e rastreável.
- O retroativo não pula intervalos incompletos por causa de uma resposta de
  página registrada como sucesso.
- Falhas persistentes continuam observáveis por modalidade; `partial` não
  significa cobertura completa nem ausência de contratações.
- Uma indisponibilidade de itens não impede a atualização de contratos e
  empenhos já acessíveis, mas também não produz um falso selo verde.
- Repetições decorrentes da retomada são seguras por idempotência; nenhum
  controle adiado é tratado como comprovadamente vazio.
