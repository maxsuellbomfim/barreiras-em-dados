begin;

create index contract_citation_snapshot_record_idx
  on finance.contract_citation_snapshot (commitment_raw_record_id);

commit;
