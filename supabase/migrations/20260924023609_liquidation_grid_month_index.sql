begin;

-- Sem este índice parcial, achar as poucas grades de liquidação varre todo
-- raw.raw_artifacts (3,9 s medidos, acima do timeout de 3 s do papel anon).
create index raw_artifacts_liquidation_grid_month_idx
  on raw.raw_artifacts (
    (metadata -> 'cursor' ->> 'month'),
    retrieved_at desc,
    id desc
  )
  where metadata ->> 'schema_name' = 'municipal-liquidations-webrun-grid';

commit;
