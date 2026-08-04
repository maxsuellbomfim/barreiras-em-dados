-- Etapa 1C, fatia 2: decisão humana sobre candidatos, sem tocar no bruto.
-- A decisão vira uma linha em editorial.editorial_reviews (o dado bruto em
-- raw.* permanece intacto) mais um evento de auditoria. Aprovar ainda NÃO
-- publica nada: a projeção pública é uma fatia futura, separada de propósito.
-- ponytail: sem trava de unicidade porque há um único revisor ativo; ao
-- introduzir dupla revisão, substituir a checagem por regra explícita.

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
    reviewer_uid::text,
    'editorial',
    review_decision,
    normalized_rationale,
    jsonb_build_object(
      'queue', 'extraction-review-queue/1.0.0',
      'action', 'extraction-candidate-review/1.0.0'
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

revoke all on function
  api.review_extraction_candidate(uuid, text, text)
  from public, anon;
grant execute on function
  api.review_extraction_candidate(uuid, text, text)
  to authenticated;

comment on function api.review_extraction_candidate(uuid, text, text) is
  'Registra decisão humana sobre um candidato; não publica nada.';

-- A fila deixa de mostrar candidatos que já receberam decisão final.
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
    'extraction-review-queue/1.1.0'::text
  from raw.extraction_results as result
  join raw.extraction_jobs as job
    on job.id = result.extraction_job_id
  join raw.raw_artifacts as artifact
    on artifact.id = job.raw_artifact_id
  where result.validation_status = 'needs_review'
    and not exists (
      select 1
      from editorial.editorial_reviews as review
      where review.target_type = 'raw.extraction_results'
        and review.target_id = result.id
        and review.decision in ('approved', 'rejected')
    )
  order by result.created_at asc, result.id asc
  limit page_size;
end;
$function$;
