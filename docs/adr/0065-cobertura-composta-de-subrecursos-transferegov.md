# ADR 0065 — Cobertura composta de subrecursos do Transferegov

## Contexto

A coleta anual do Transferegov parte das propostas destinadas a Barreiras e
percorre relações dependentes: distribuições de recursos, parcerias, empenhos,
documentos hábeis e ordens de pagamento. O sistema preservava páginas de todos
esses endpoints, mas concluía uma partição controlada somente para propostas.
O painel podia, portanto, classificar um subrecurso já consultado como “nunca
atualizado”. Copiar o estado da proposta para todos os filhos também seria
incorreto, pois cada endpoint possui contagem e resposta próprias.

## Decisão

1. A execução abre uma partição anual para propostas e uma para cada endpoint
   dependente antes da primeira autenticação ou requisição externa.
2. A operação mantém contagens separadas por endpoint, além do total agregado
   usado por compatibilidade.
3. Cada partição dependente recebe `complete` quando possui registros e `empty`
   quando a travessia integral foi bem-sucedida e a contagem oficial é zero.
4. A partição de propostas é concluída por último. Uma exceção antes disso é
   propagada a todos os controles ainda abertos e nenhuma ausência é publicada
   como comprovada.
5. Uma resposta sem propostas permite fechar os filhos como vazios apenas
   porque esses recursos exigem identificadores parentais validados da mesma
   consulta anual.
6. Ordens bancárias não recebem endpoint artificial: são registros derivados
   de campos presentes nas ordens de pagamento e permanecem vinculadas à mesma
   evidência bruta.

## Consequências

- O painel diferencia subrecurso consultado sem resultado de subrecurso ainda
  não consultado.
- Falhas parciais permanecem visíveis e não são mascaradas pelo sucesso da
  consulta de propostas.
- A próxima execução idempotente de 2021 ao ano atual preencherá as partições
  históricas sem reescrever artefatos já preservados.
- Contagens e estados continuam determinísticos; nenhuma IA decide cobertura
  ou ausência de transferências.
