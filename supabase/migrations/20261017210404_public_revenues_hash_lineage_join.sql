begin;

-- Receitas públicas sem filtro de ano: o planejador escolhia merge join com a
-- projeção de linhagem só por origin_raw_record_id e descartava 619 mil pares
-- no filtro (0,7–2,0 s em 17/10/2026). Com hash join nas duas chaves: 0,32 s.
-- ponytail: ajuste de plano por função; trocar por instantâneo se a tabela
-- crescer a ponto de o hash não bastar. Mesmo resultado (md5 idêntico).
alter function api.get_public_revenues(integer, smallint)
  set enable_mergejoin to off;

commit;
