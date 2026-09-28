begin;

-- O limite de 2 conexões foi definido quando esta identidade servia só ao
-- coletor do Querido Diário. Hoje ela é compartilhada por ~15 workflows e
-- pelas tarefas locais (Farmácia Popular, TCM-BA); a Farmácia sozinha usa
-- duas conexões. Em 28/09 o banco recusou 22 conexões ("too many connections
-- for role") entre 10h e 12h UTC e a Farmácia de 2026 falhava todo dia.
-- 8 continua bem abaixo das 60 conexões do banco. Decisão do titular.
alter role collector_querido_diario connection limit 8;

commit;
