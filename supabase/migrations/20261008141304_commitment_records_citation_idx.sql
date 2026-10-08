begin;

-- Tentativa de acelerar a comparação do ADR 0096 (7 mil leituras do bruto por
-- id). Não bastou: o planejador não faz varredura só por índice quando o
-- filtro referencia a coluna payload inteira. Removido na migration seguinte
-- (instantâneo); fica registrado porque foi aplicado em produção.
create index if not exists raw_records_commitment_citation_idx
  on raw.raw_records (
    id,
    (payload ->> 'field1082407'),
    (payload ->> 'field1082413'),
    (payload ->> 'field1144629')
  )
  where record_type = 'municipal_commitment_webrun';

commit;
