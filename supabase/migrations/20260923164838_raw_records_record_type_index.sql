begin;

-- raw.raw_records só tinha índices por tipo parciais (exigindo
-- source_record_key não nulo ou listas fechadas de tipos). RPCs públicas que
-- filtram apenas pelo tipo — sanções, contratos e processos municipais,
-- entre outras — faziam varredura completa dos ~250 mil registros (~200 MB)
-- para devolver poucas centenas de linhas, levando 1,2-2 s e estourando o
-- statement timeout de 3 s a frio. A ordem por data acompanha a escolha do
-- registro mais recente feita por essas projeções.

create index if not exists raw_records_record_type_recent_idx
  on raw.raw_records (record_type, created_at desc, id desc);

analyze raw.raw_records;

commit;
