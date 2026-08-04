-- Regras de candidato 2.0.0: o candidato passa a ser o ato inteiro (bloco da
-- Portaria), não cada ocorrência de palavra. Os candidatos gerados pelas
-- regras antigas duplicavam o mesmo ato, transformavam menção em cartão e
-- exibiam trecho cortado. Eles são aposentados aqui com decisão registrada
-- (nada é apagado) para não serem publicados pelo fluxo automático; o
-- reprocessamento com a régua nova gera candidatos corretos, porque a chave
-- de idempotência do job inclui a versão do ruleset.

insert into editorial.editorial_reviews (
  target_type,
  target_id,
  reviewer_subject,
  review_type,
  decision,
  rationale,
  checklist
)
select
  'raw.extraction_results',
  result.id,
  'automated:ruleset-migration',
  'editorial',
  'rejected',
  'Aposentado pela régua gazette-act-candidates/2.0.0: o ato passa a ser '
    || 'identificado pelo bloco da Portaria, sem duplicar o mesmo ato nem '
    || 'transformar menção em candidato. Substituído pelo reprocessamento.',
  jsonb_build_object(
    'action', 'ruleset-retirement/1.0.0',
    'previous_extractor_version', result.extractor_version,
    'new_ruleset', 'gazette-act-candidates/2.0.0'
  )
from raw.extraction_results as result
where result.candidate_type in ('nomeacao', 'exoneracao')
  and result.validation_status = 'needs_review'
  and result.extractor_version <> 'gazette-act-candidates/2.0.0'
  and not exists (
    select 1
    from editorial.editorial_reviews as review
    where review.target_type = 'raw.extraction_results'
      and review.target_id = result.id
      and review.decision in ('approved', 'rejected')
  );

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
  'system',
  'automated:ruleset-migration',
  'candidate_ruleset_retired',
  'raw.extraction_results',
  'gazette-act-candidates/1.0.0',
  jsonb_build_object('decision', 'rejected'),
  jsonb_build_object('new_ruleset', 'gazette-act-candidates/2.0.0')
);

-- Atos aprovados 1.4.0: um ato por (tipo, número, data) mesmo que a régua
-- antiga tenha aprovado duplicatas; o mais recente vence.

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
    deduped.act_id,
    deduped.act_type,
    deduped.person_name,
    deduped.position_title,
    deduped.position_symbol,
    deduped.organization,
    deduped.gazette_date,
    deduped.gazette_url,
    deduped.excerpt,
    deduped.assisted_summary,
    deduped.assisted_provider,
    deduped.approved_at,
    deduped.artifact_sha256,
    deduped.extractor_version,
    deduped.review_mode,
    'approved-gazette-acts/1.4.0'::text
  from (
    select distinct on (
      result.candidate_type,
      coalesce(
        latest.checklist #>> '{verification,fields,act_number,value}',
        result.result_payload #>> '{fields,act_number,value}',
        result.id::text
      ),
      coalesce(
        latest.checklist #>> '{verification,fields,act_date,value}',
        result.result_payload #>> '{fields,act_date,value}',
        ''
      )
    )
      result.id as act_id,
      result.candidate_type as act_type,
      coalesce(
        latest.checklist #>> '{verification,fields,person_name,value}',
        result.result_payload #>> '{fields,person_name,value}'
      ) as person_name,
      coalesce(
        latest.checklist #>> '{verification,fields,position,value}',
        result.result_payload #>> '{fields,position,value}'
      ) as position_title,
      coalesce(
        latest.checklist #>> '{verification,fields,position_symbol,value}',
        result.result_payload #>> '{fields,position_symbol,value}'
      ) as position_symbol,
      coalesce(
        latest.checklist #>> '{verification,fields,organization,value}',
        result.result_payload #>> '{fields,organization,value}'
      ) as organization,
      gazette.published_date as gazette_date,
      coalesce(
        gazette.source_url,
        case
          when artifact.metadata ->> 'schema_name' = 'gazette-direct-edition'
          then artifact.source_url
        end
      ) as gazette_url,
      result.result_payload ->> 'excerpt' as excerpt,
      reviewed_assist.summary as assisted_summary,
      reviewed_assist.provider as assisted_provider,
      latest.reviewed_at as approved_at,
      artifact.sha256 as artifact_sha256,
      result.extractor_version,
      case
        when latest.reviewer_subject like 'automated:%' then 'automated'
        else 'human'
      end as review_mode
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
        and record.source_record_key
            = artifact.metadata ->> 'source_record_key'
      order by record.collected_at desc
      limit 1
    ) as gazette on true
    where latest.decision = 'approved'
    order by
      result.candidate_type,
      coalesce(
        latest.checklist #>> '{verification,fields,act_number,value}',
        result.result_payload #>> '{fields,act_number,value}',
        result.id::text
      ),
      coalesce(
        latest.checklist #>> '{verification,fields,act_date,value}',
        result.result_payload #>> '{fields,act_date,value}',
        ''
      ),
      latest.reviewed_at desc
  ) as deduped
  order by deduped.approved_at desc, deduped.act_id
  limit page_size;
end;
$function$;

revoke all on function api.get_approved_gazette_acts(integer) from public;
grant execute on function api.get_approved_gazette_acts(integer)
  to anon, authenticated;

comment on function api.get_approved_gazette_acts(integer) is
  'Atos aprovados, um por (tipo, portaria, data), com modo de revisão.';
