-- Etapa 1C, fatia 4: histórico de decisões e reversão com rastro.
-- Decisão não é editada: reverter cria uma linha 'withdrawn' com
-- justificativa e devolve o candidato à fila. A decisão vigente de um
-- candidato passa a ser a ÚLTIMA linha registrada — na fila, no histórico e
-- na projeção pública.

create or replace function api.latest_review_decision(
  candidate_result_id uuid
)
returns text
language sql
stable
security definer
set search_path = ''
as $function$
  select review.decision
  from editorial.editorial_reviews as review
  where review.target_type = 'raw.extraction_results'
    and review.target_id = candidate_result_id
  order by review.created_at desc, review.id desc
  limit 1;
$function$;

revoke all on function api.latest_review_decision(uuid) from public, anon;
grant execute on function api.latest_review_decision(uuid) to authenticated;

-- Fila: sem decisão registrada ou com a última decisão revertida.
create or replace function api.get_extraction_review_queue(
  page_size integer default 20
)
returns table (
  result_id uuid,
  candidate_type text,
  extractor_version text,
  validation_status text,
  result_created_at timestamptz,
  result_payload jsonb,
  artifact_sha256 text,
  methodology_version text
)
language plpgsql
stable
security definer
set search_path = ''
as $function$
begin
  if page_size < 1 or page_size > 100 then
    raise exception 'page_size deve estar entre 1 e 100'
      using errcode = '22023';
  end if;
  if not api.is_active_reviewer() then
    raise exception 'acesso restrito a revisores ativos'
      using errcode = '42501';
  end if;

  return query
  select
    result.id,
    result.candidate_type,
    result.extractor_version,
    result.validation_status,
    result.created_at,
    result.result_payload,
    artifact.sha256,
    'extraction-review-queue/1.2.0'::text
  from raw.extraction_results as result
  join raw.extraction_jobs as job
    on job.id = result.extraction_job_id
  join raw.raw_artifacts as artifact
    on artifact.id = job.raw_artifact_id
  where result.validation_status = 'needs_review'
    and coalesce(api.latest_review_decision(result.id), 'none')
      not in ('approved', 'rejected')
  order by result.created_at asc, result.id asc
  limit page_size;
end;
$function$;

-- Decidir: permitido quando não há decisão vigente (nunca decidido ou
-- revertido); bloqueado quando a última decisão é final.
create or replace function api.review_extraction_candidate(
  candidate_result_id uuid,
  review_decision text,
  review_rationale text
)
returns uuid
language plpgsql
volatile
security definer
set search_path = ''
as $function$
declare
  reviewer_uid uuid;
  normalized_rationale text;
  review_id uuid;
begin
  reviewer_uid := (select auth.uid());
  if not api.is_active_reviewer() then
    raise exception 'acesso restrito a revisores ativos'
      using errcode = '42501';
  end if;
  if review_decision not in ('approved', 'rejected') then
    raise exception 'decisão deve ser approved ou rejected'
      using errcode = '22023';
  end if;
  normalized_rationale := btrim(coalesce(review_rationale, ''));
  if length(normalized_rationale) < 5 then
    raise exception 'a justificativa é obrigatória (mínimo 5 caracteres)'
      using errcode = '22023';
  end if;

  if not exists (
    select 1
    from raw.extraction_results as result
    where result.id = candidate_result_id
      and result.validation_status = 'needs_review'
  ) then
    raise exception 'candidato não encontrado na fila de revisão'
      using errcode = '02000';
  end if;

  if coalesce(api.latest_review_decision(candidate_result_id), 'none')
      in ('approved', 'rejected') then
    raise exception
      'este candidato já tem decisão vigente; reverta antes de decidir'
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
    reviewer_uid::text,
    'editorial',
    review_decision,
    normalized_rationale,
    jsonb_build_object(
      'queue', 'extraction-review-queue/1.2.0',
      'action', 'extraction-candidate-review/1.1.0'
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
    'reviewer',
    reviewer_uid::text,
    'extraction_candidate_reviewed',
    'raw.extraction_results',
    candidate_result_id::text,
    jsonb_build_object('decision', review_decision),
    jsonb_build_object('editorial_review_id', review_id)
  );

  return review_id;
end;
$function$;

-- Reverter: cria 'withdrawn' com justificativa; o candidato volta à fila.
create or replace function api.withdraw_extraction_review(
  candidate_result_id uuid,
  review_rationale text
)
returns uuid
language plpgsql
volatile
security definer
set search_path = ''
as $function$
declare
  reviewer_uid uuid;
  normalized_rationale text;
  review_id uuid;
begin
  reviewer_uid := (select auth.uid());
  if not api.is_active_reviewer() then
    raise exception 'acesso restrito a revisores ativos'
      using errcode = '42501';
  end if;
  normalized_rationale := btrim(coalesce(review_rationale, ''));
  if length(normalized_rationale) < 5 then
    raise exception 'a justificativa é obrigatória (mínimo 5 caracteres)'
      using errcode = '22023';
  end if;
  if coalesce(api.latest_review_decision(candidate_result_id), 'none')
      not in ('approved', 'rejected') then
    raise exception 'não há decisão vigente para reverter'
      using errcode = '02000';
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
    reviewer_uid::text,
    'editorial',
    'withdrawn',
    normalized_rationale,
    jsonb_build_object(
      'action', 'extraction-review-withdrawal/1.0.0'
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
    'reviewer',
    reviewer_uid::text,
    'extraction_review_withdrawn',
    'raw.extraction_results',
    candidate_result_id::text,
    jsonb_build_object('decision', 'withdrawn'),
    jsonb_build_object('editorial_review_id', review_id)
  );

  return review_id;
end;
$function$;

revoke all on function
  api.withdraw_extraction_review(uuid, text) from public, anon;
grant execute on function
  api.withdraw_extraction_review(uuid, text) to authenticated;

-- Histórico: candidatos cuja decisão vigente é final, com justificativa.
create or replace function api.get_extraction_review_history(
  page_size integer default 50
)
returns table (
  result_id uuid,
  candidate_type text,
  result_payload jsonb,
  artifact_sha256 text,
  decision text,
  rationale text,
  decided_at timestamptz,
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
  if not api.is_active_reviewer() then
    raise exception 'acesso restrito a revisores ativos'
      using errcode = '42501';
  end if;

  return query
  select
    result.id,
    result.candidate_type,
    result.result_payload,
    artifact.sha256,
    latest.decision,
    latest.rationale,
    latest.reviewed_at,
    'extraction-review-history/1.0.0'::text
  from raw.extraction_results as result
  join raw.extraction_jobs as job
    on job.id = result.extraction_job_id
  join raw.raw_artifacts as artifact
    on artifact.id = job.raw_artifact_id
  join lateral (
    select review.decision, review.rationale, review.reviewed_at
    from editorial.editorial_reviews as review
    where review.target_type = 'raw.extraction_results'
      and review.target_id = result.id
    order by review.created_at desc, review.id desc
    limit 1
  ) as latest on true
  where latest.decision in ('approved', 'rejected')
  order by latest.reviewed_at desc, result.id
  limit page_size;
end;
$function$;

revoke all on function
  api.get_extraction_review_history(integer) from public, anon;
grant execute on function
  api.get_extraction_review_history(integer) to authenticated;

-- Projeção pública: vale a decisão vigente, não qualquer aprovação antiga.
create or replace function api.get_approved_gazette_acts(
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
  approved_at timestamptz,
  artifact_sha256 text,
  extractor_version text,
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
    result.result_payload #>> '{fields,person_name,value}',
    result.result_payload #>> '{fields,position,value}',
    result.result_payload #>> '{fields,position_symbol,value}',
    result.result_payload #>> '{fields,organization,value}',
    gazette.published_date,
    gazette.source_url,
    result.result_payload ->> 'excerpt',
    latest.reviewed_at,
    artifact.sha256,
    result.extractor_version,
    'approved-gazette-acts/1.1.0'::text
  from raw.extraction_results as result
  join raw.extraction_jobs as job
    on job.id = result.extraction_job_id
  join raw.raw_artifacts as artifact
    on artifact.id = job.raw_artifact_id
  join lateral (
    select review.decision, review.reviewed_at
    from editorial.editorial_reviews as review
    where review.target_type = 'raw.extraction_results'
      and review.target_id = result.id
    order by review.created_at desc, review.id desc
    limit 1
  ) as latest on true
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
