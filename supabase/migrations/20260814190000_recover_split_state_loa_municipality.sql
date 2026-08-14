begin;

-- O texto embutido do Anexo I da LOA 2026 pode anexar a coluna Municipio ao
-- fim do objeto e ate separar letras de "Barreiras". A versao 1.2.0 recupera
-- essas linhas sem alterar nem apagar as extracoes 1.1.0 ja preservadas.

create index if not exists extraction_results_bahia_state_loa_v12_valid_idx
  on raw.extraction_results (created_at desc, id desc)
  where candidate_type = 'bahia_state_loa_authorized_amendment'
    and extractor_version = 'bahia-state-loa-barreiras/1.2.0'
    and validator_version = 'bahia-state-loa-deterministic/1.0.0'
    and validation_status = 'valid';

create or replace view territory.bahia_state_loa_amendments
with (security_barrier = true)
as
with eligible as (
  select
    result.id as origin_extraction_result_id,
    job.id as origin_extraction_job_id,
    artifact.id as origin_raw_artifact_id,
    result.result_payload as payload,
    result.created_at,
    row_number() over (
      partition by
        result.result_payload ->> 'source_artifact_sha256',
        result.result_payload ->> 'evidence_sha256'
      order by
        case result.extractor_version
          when 'bahia-state-loa-barreiras/1.2.0' then 2
          else 1
        end desc,
        result.created_at desc,
        result.id desc
    ) as version_rank
  from raw.extraction_results as result
  join raw.extraction_jobs as job
    on job.id = result.extraction_job_id
   and job.status = 'succeeded'
  join raw.raw_artifacts as artifact
    on artifact.id = job.raw_artifact_id
   and artifact.sha256 = result.result_payload ->> 'source_artifact_sha256'
   and artifact.source_url = result.result_payload ->> 'source_url'
  where result.candidate_type = 'bahia_state_loa_authorized_amendment'
    and result.extractor_version in (
      'bahia-state-loa-barreiras/1.1.0',
      'bahia-state-loa-barreiras/1.2.0'
    )
    and result.validator_version = 'bahia-state-loa-deterministic/1.0.0'
    and result.validation_status = 'valid'
    and result.validation_errors = '[]'::jsonb
    and result.result_payload ->> 'financial_stage' = 'authorized'
    and lower(btrim(result.result_payload ->> 'municipality')) = 'barreiras'
    and result.result_payload ->> 'fiscal_year' ~ '^[0-9]{4}$'
    and (result.result_payload ->> 'fiscal_year')::integer between 2022 and 2100
    and result.result_payload ->> 'authorized_amount'
      ~ '^[0-9]{1,18}(?:[.][0-9]{1,2})?$'
    and (result.result_payload ->> 'authorized_amount')::numeric >= 0
    and nullif(btrim(result.result_payload ->> 'amendment_number'), '') is not null
    and nullif(btrim(result.result_payload ->> 'author_name'), '') is not null
    and nullif(btrim(result.result_payload ->> 'official_description'), '') is not null
    and nullif(btrim(result.result_payload ->> 'evidence_text'), '') is not null
    and result.result_payload ->> 'page_number' ~ '^[1-9][0-9]*$'
    and result.result_payload ->> 'source_url' like 'https://%'
    and result.result_payload ->> 'source_artifact_sha256' ~ '^[0-9a-f]{64}$'
    and result.result_payload ->> 'evidence_sha256' ~ '^[0-9a-f]{64}$'
)
select
  eligible.origin_extraction_result_id,
  eligible.origin_extraction_job_id,
  eligible.origin_raw_artifact_id,
  (eligible.payload ->> 'fiscal_year')::smallint as fiscal_year,
  btrim(eligible.payload ->> 'amendment_number') as amendment_number,
  nullif(btrim(eligible.payload ->> 'author_external_code'), '')
    as author_external_code,
  btrim(eligible.payload ->> 'author_name') as author_name,
  regexp_replace(
    regexp_replace(
      translate(
        lower(btrim(eligible.payload ->> 'author_name')),
        'áàãâäéèêëíìîïóòõôöúùûüç',
        'aaaaaeeeeiiiiooooouuuuc'
      ),
      '(^|[^[:alnum:]])jr[.]?([^[:alnum:]]|$)',
      '\1junior\2',
      'g'
    ),
    '[^[:alnum:]]+',
    ' ',
    'g'
  ) as author_key,
  (eligible.payload ->> 'authorized_amount')::numeric(20,2)
    as authorized_amount,
  btrim(eligible.payload ->> 'official_description') as official_description,
  nullif(btrim(eligible.payload ->> 'annex_code'), '') as annex_code,
  nullif(btrim(eligible.payload ->> 'budget_unit_code'), '')
    as budget_unit_code,
  nullif(btrim(eligible.payload ->> 'agency_code'), '') as agency_code,
  nullif(btrim(eligible.payload ->> 'action_code'), '') as action_code,
  (eligible.payload ->> 'page_number')::integer as page_number,
  btrim(eligible.payload ->> 'evidence_text') as evidence_text,
  'authorized'::text as financial_stage,
  eligible.payload ->> 'source_url' as source_url,
  eligible.payload ->> 'source_artifact_sha256' as source_artifact_sha256,
  eligible.payload ->> 'evidence_sha256' as evidence_sha256,
  eligible.created_at
from eligible
where eligible.version_rank = 1;

revoke all on territory.bahia_state_loa_amendments from public;
revoke all on territory.bahia_state_loa_amendments from anon, authenticated;

comment on view territory.bahia_state_loa_amendments is
  'Emendas autorizadas para Barreiras nas LOAs da Bahia; aceita a extracao corrigida 1.2.0 e preserva a 1.1.0 ate o reprocessamento.';

notify pgrst, 'reload schema';

commit;
