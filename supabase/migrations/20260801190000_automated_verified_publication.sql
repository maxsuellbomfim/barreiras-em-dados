-- ADR 0012: publicação automática verificada por código, revisão por exceção.
-- Quem decide não é a IA: é o verificador determinístico do worker, que só
-- aceita valores presentes literalmente no trecho oficial. A decisão entra na
-- MESMA trilha de editorial_reviews (auditável e reversível por withdraw) com
-- reviewer_subject 'automated:...', e o site rotula o modo de revisão.

create or replace function editorial.record_automated_review(
  candidate_result_id uuid,
  review_rationale text,
  verification jsonb
)
returns uuid
language plpgsql
volatile
security definer
set search_path = ''
as $function$
declare
  normalized_rationale text;
  review_id uuid;
begin
  normalized_rationale := btrim(coalesce(review_rationale, ''));
  if length(normalized_rationale) < 5 then
    raise exception 'a justificativa é obrigatória (mínimo 5 caracteres)'
      using errcode = '22023';
  end if;
  if verification is null or not (verification ? 'verifier') then
    raise exception 'a verificação deve declarar o verificador versionado'
      using errcode = '22023';
  end if;

  if not exists (
    select 1
    from raw.extraction_results as result
    where result.id = candidate_result_id
      and result.validation_status = 'needs_review'
      and result.candidate_type <> 'assisted_enrichment'
  ) then
    raise exception 'candidato não encontrado na fila de revisão'
      using errcode = '02000';
  end if;

  if exists (
    select 1
    from editorial.editorial_reviews as review
    where review.target_type = 'raw.extraction_results'
      and review.target_id = candidate_result_id
      and review.decision in ('approved', 'rejected')
  ) then
    raise exception 'este candidato já recebeu uma decisão final'
      using errcode = '23505';
  end if;

  insert into editorial.editorial_reviews (
    target_type,
    target_id,
    reviewer_subject,
    review_type,
    decision,
    rationale,
    checklist
  )
  values (
    'raw.extraction_results',
    candidate_result_id,
    'automated:gazette-act-verifier',
    'editorial',
    'approved',
    normalized_rationale,
    jsonb_build_object(
      'action', 'automated-verified-publication/1.0.0',
      'verification', verification
    )
  )
  returning id into review_id;

  insert into audit.audit_events (
    actor_type,
    actor_subject,
    action,
    target_type,
    target_id,
    after_state,
    metadata
  )
  values (
    'worker',
    'automated:gazette-act-verifier',
    'extraction_candidate_auto_published',
    'raw.extraction_results',
    candidate_result_id::text,
    jsonb_build_object('decision', 'approved'),
    jsonb_build_object(
      'editorial_review_id', review_id,
      'verifier', verification ->> 'verifier'
    )
  );

  return review_id;
end;
$function$;

revoke all on function
  editorial.record_automated_review(uuid, text, jsonb)
  from public, anon, authenticated;
grant execute on function
  editorial.record_automated_review(uuid, text, jsonb)
  to collector_worker;

comment on function
  editorial.record_automated_review(uuid, text, jsonb) is
  'Publicação automática ADR 0012: aprovação verificada por código, '
  'auditada e reversível; exclusiva do worker.';

-- Atos aprovados 1.3.0: modo de revisão explícito e campos verificados da
-- publicação automática (o checklist da decisão carrega os valores aceitos;
-- para decisão humana permanece o payload determinístico).

drop function if exists api.get_approved_gazette_acts(integer);

create function api.get_approved_gazette_acts(
  page_size integer default 50
)
returns table (
  act_id uuid,
  act_type text,
  person_name text,
  position_title text,
  position_symbol text,
  organization text,
  gazette_date date,
  gazette_url text,
  excerpt text,
  assisted_summary text,
  assisted_provider text,
  approved_at timestamptz,
  artifact_sha256 text,
  extractor_version text,
  review_mode text,
  methodology_version text
)
language plpgsql
stable
security definer
set search_path = ''
as $function$
begin
  if page_size < 1 or page_size > 200 then
    raise exception 'page_size deve estar entre 1 e 200'
      using errcode = '22023';
  end if;

  return query
  select
    result.id,
    result.candidate_type,
    coalesce(
      latest.checklist #>> '{verification,fields,person_name,value}',
      result.result_payload #>> '{fields,person_name,value}'
    ),
    coalesce(
      latest.checklist #>> '{verification,fields,position,value}',
      result.result_payload #>> '{fields,position,value}'
    ),
    coalesce(
      latest.checklist #>> '{verification,fields,position_symbol,value}',
      result.result_payload #>> '{fields,position_symbol,value}'
    ),
    coalesce(
      latest.checklist #>> '{verification,fields,organization,value}',
      result.result_payload #>> '{fields,organization,value}'
    ),
    gazette.published_date,
    coalesce(
      gazette.source_url,
      case
        when artifact.metadata ->> 'schema_name' = 'gazette-direct-edition'
        then artifact.source_url
      end
    ),
    result.result_payload ->> 'excerpt',
    reviewed_assist.summary,
    reviewed_assist.provider,
    latest.reviewed_at,
    artifact.sha256,
    result.extractor_version,
    case
      when latest.reviewer_subject like 'automated:%' then 'automated'
      else 'human'
    end,
    'approved-gazette-acts/1.3.0'::text
  from raw.extraction_results as result
  join raw.extraction_jobs as job
    on job.id = result.extraction_job_id
  join raw.raw_artifacts as artifact
    on artifact.id = job.raw_artifact_id
  join lateral (
    select
      review.decision,
      review.reviewed_at,
      review.reviewer_subject,
      review.checklist
    from editorial.editorial_reviews as review
    where review.target_type = 'raw.extraction_results'
      and review.target_id = result.id
    order by review.created_at desc, review.id desc
    limit 1
  ) as latest on true
  left join lateral (
    select
      enrichment.result_payload ->> 'summary' as summary,
      enrichment.result_payload ->> 'provider' as provider
    from raw.extraction_results as enrichment
    where enrichment.supersedes_id = result.id
      and enrichment.candidate_type = 'assisted_enrichment'
      and enrichment.created_at <= latest.reviewed_at
      and enrichment.result_payload ->> 'summary' is not null
    order by enrichment.created_at desc, enrichment.id desc
    limit 1
  ) as reviewed_assist on true
  left join lateral (
    select
      (record.payload ->> 'date')::date as published_date,
      record.payload ->> 'url' as source_url
    from raw.raw_records as record
    where record.record_type = 'querido_diario_gazette'
      and record.source_record_key = artifact.metadata ->> 'source_record_key'
    order by record.collected_at desc
    limit 1
  ) as gazette on true
  where latest.decision = 'approved'
  order by latest.reviewed_at desc, result.id
  limit page_size;
end;
$function$;

revoke all on function api.get_approved_gazette_acts(integer) from public;
grant execute on function api.get_approved_gazette_acts(integer)
  to anon, authenticated;

comment on function api.get_approved_gazette_acts(integer) is
  'Atos aprovados com modo de revisão explícito (pessoa ou código, ADR 0012).';
