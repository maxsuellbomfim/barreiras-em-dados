-- A IA assistida e a publicação verificada precisam saber quais candidatos
-- já receberam decisão — leitura de editorial.editorial_reviews. Sem este
-- grant, todo passo assistido morria com
-- "permission denied for schema editorial" e derrubava, junto, a publicação
-- automática e o resumo por edição.
--
-- Privilégio mínimo: USAGE no schema e SELECT apenas nesta tabela. A role
-- continua sem poder escrever decisões diretamente — publicar segue
-- exclusivo da função editorial.record_automated_review (security definer).

grant usage on schema editorial to collector_worker;
grant select on table editorial.editorial_reviews to collector_worker;

comment on table editorial.editorial_reviews is
  'Decisões editoriais (humanas e automáticas). Worker lê para saber o que '
  'já foi decidido; escrita só por funções security definer.';
