begin;
alter table source.fns_pharmacy_documents add column register_page integer
  check(register_page between 1 and 500);
alter table source.fns_pharmacy_documents drop constraint fns_pharmacy_documents_register_row_check;
alter table source.fns_pharmacy_documents add constraint fns_pharmacy_documents_register_row_check
  check(register_row between 1 and 1001);

create or replace function source.pharmacy_document_matches(d source.fns_pharmacy_documents)
returns boolean language sql stable security invoker set search_path='' as $$
  select exists (
    select 1 from source.fns_pharmacy_snapshots s
    join raw.raw_artifacts p on p.id=s.payment_artifact_id
    join raw.raw_artifacts x on x.id=s.register_artifact_id
    join raw.raw_records r on r.id=d.raw_record_id and r.raw_artifact_id=p.id
    where s.id=d.snapshot_id
      and p.sha256=s.payment_sha256 and x.sha256=s.register_sha256
      and p.byte_size>0 and x.byte_size>0 and p.http_status=200
      and p.content_type='application/json'
      and p.source_url ~ '^https://consultafns[.]saude[.]gov[.]br/recursos/consulta-detalhada/detalhe-pagamento[?]'
      and (
        (x.content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
          and (x.http_status is null or x.http_status=200)
          and x.source_url ~ '^https://infoms[.]saude[.]gov[.]br/tempcontent/[^#[:space:]]+[.]xlsx([?][^#[:space:]]*)?$'
          and d.register_page is null and d.register_row>=2
          and not (r.payload ? 'register_page'))
        or (x.content_type='application/pdf' and x.http_status=200
          and x.source_url ~ '^https://www[.]gov[.]br/saude/pt-br/composicao/sectics/farmacia-popular/(renovacao-de-estabelecimentos-participantes|renovacao-de-credenciamento)/empresas-credenciadas-para-realizar-a-renovacao-2025/@@download/file$'
          and d.register_page between 1 and 500
          and r.payload->>'register_page'=d.register_page::text)
      )
      and extract(year from d.document_date)=s.payment_year
      and r.record_type='fns_pharmacy_payment'
      and r.payload->>'document_key'=d.document_key
      and r.payload->>'document_date'=d.document_date::text
      and r.payload->>'net'=d.net_amount::text
      and r.payload->>'source_row'=d.source_row::text
      and r.payload->>'register_row'=d.register_row::text
      and r.payload->>'register_sha256'=s.register_sha256
      and r.payload->>'establishment'=s.establishment
  );
$$;
comment on column source.fns_pharmacy_documents.register_page is
  'Private 1-based PDF page; null for XLSX. register_row is a 1-based data row within that PDF page, or the XLSX sheet row. Not historical accreditation.';
notify pgrst,'reload schema';
commit;
