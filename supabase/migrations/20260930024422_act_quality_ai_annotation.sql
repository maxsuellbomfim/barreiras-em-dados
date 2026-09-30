begin;

-- ADR 0091: conferência automática por IA da amostra de qualidade de atos.
-- O worker lê as páginas pendentes, manda a imagem da página do PDF oficial
-- ao modelo e grava a resposta validada como anotação rotulada de IA
-- (reviewer_subject 'ai:<modelo>:act-quality-prompt/<versão>'). As métricas
-- continuam calculadas por código e podem ser filtradas por fonte.

create function editorial.get_act_quality_pages_for_ai(
  p_prompt_version text,
  p_limit integer
)
returns table (
  sample_page_id uuid,
  page_number integer,
  object_key text,
  artifact_sha256 text,
  acts jsonb
)
language sql
stable
security definer
set search_path = ''
as $$
  with current_sample as (
    select sample.id
    from editorial.act_quality_samples as sample
    order by sample.created_at desc, sample.id desc
    limit 1
  )
  select
    page.id,
    page.page_number,
    artifact.object_key,
    page.artifact_sha256,
    coalesce((
      select jsonb_agg(jsonb_build_object(
        'result_id', act.extraction_result_id,
        'act_type', act.act_type,
        'person_name', result.result_payload -> 'fields' -> 'person_name' ->> 'value',
        'position', result.result_payload -> 'fields' -> 'position' ->> 'value'
      ) order by act.extraction_result_id)
      from editorial.act_quality_sample_acts as act
      join raw.extraction_results as result on result.id = act.extraction_result_id
      where act.sample_page_id = page.id
    ), '[]'::jsonb)
  from current_sample
  join editorial.act_quality_sample_pages as page on page.sample_id = current_sample.id
  join raw.raw_artifacts as artifact on artifact.id = page.raw_artifact_id
  where p_prompt_version ~ '^act-quality-prompt/[0-9]+\.[0-9]+\.[0-9]+$'
    and not exists (
      select 1 from editorial.act_quality_annotations as annotation
      where annotation.sample_page_id = page.id
        and annotation.reviewer_subject like 'ai:%:' || p_prompt_version
    )
  order by page.raw_artifact_id, page.page_number
  limit least(greatest(p_limit, 1), 500)
$$;

create function editorial.record_ai_act_quality_annotation(
  p_sample_page_id uuid,
  p_act_verdicts jsonb,
  p_missed_nomeacoes integer,
  p_missed_exoneracoes integer,
  p_annotator text,
  p_response_sha256 text
)
returns uuid
language plpgsql
security definer
set search_path = ''
as $$
#variable_conflict use_column
declare
  annotation_id uuid;
  expected_ids text[];
  given_ids text[];
begin
  if p_annotator !~ '^ai:[a-z0-9._-]{1,80}:act-quality-prompt/[0-9]+\.[0-9]+\.[0-9]+$' then
    raise exception 'anotador de IA inválido' using errcode = '22023';
  end if;
  if p_response_sha256 !~ '^[a-f0-9]{64}$' then
    raise exception 'hash da resposta inválido' using errcode = '22023';
  end if;
  if jsonb_typeof(p_act_verdicts) is distinct from 'object' then
    raise exception 'veredito dos atos inválido' using errcode = '22023';
  end if;
  select coalesce(array_agg(act.extraction_result_id::text
      order by act.extraction_result_id::text), '{}')
  into expected_ids
  from editorial.act_quality_sample_acts as act
  where act.sample_page_id = p_sample_page_id;
  select coalesce(array_agg(key order by key), '{}')
  into given_ids
  from jsonb_object_keys(p_act_verdicts) as key;
  if not exists (
    select 1 from editorial.act_quality_sample_pages as page
    where page.id = p_sample_page_id
  ) or expected_ids is distinct from given_ids then
    raise exception 'cada ato da página precisa de exatamente um veredito'
      using errcode = '22023';
  end if;
  if exists (
    select 1 from jsonb_each_text(p_act_verdicts) as verdict
    where verdict.value not in ('correct', 'partial', 'incorrect')
  ) or p_missed_nomeacoes not between 0 and 200
    or p_missed_exoneracoes not between 0 and 200 then
    raise exception 'anotação fora do contrato' using errcode = '22023';
  end if;
  insert into editorial.act_quality_annotations (
    sample_page_id, reviewer_subject, act_verdicts,
    missed_nomeacoes, missed_exoneracoes, note
  ) values (
    p_sample_page_id, p_annotator, p_act_verdicts,
    p_missed_nomeacoes, p_missed_exoneracoes,
    'Anotação automática por IA (ADR 0091); sha256 da resposta: '
      || p_response_sha256
  )
  returning id into annotation_id;
  return annotation_id;
end;
$$;

revoke all on function editorial.get_act_quality_pages_for_ai(text, integer)
  from public, anon, authenticated, service_role;
revoke all on function editorial.record_ai_act_quality_annotation(
  uuid, jsonb, integer, integer, text, text
) from public, anon, authenticated, service_role;
grant usage on schema editorial to collector_worker;
grant execute on function editorial.get_act_quality_pages_for_ai(text, integer)
  to collector_worker;
grant execute on function editorial.record_ai_act_quality_annotation(
  uuid, jsonb, integer, integer, text, text
) to collector_worker;

drop function api.get_act_quality_metrics();

create or replace function api.get_act_quality_sample()
returns table (
  sample_page_id uuid,
  sample_version text,
  stratum text,
  sample_rank integer,
  edition integer,
  edition_year integer,
  page_number integer,
  text_source text,
  pdf_page_url text,
  acts jsonb,
  latest_annotation jsonb
)
language plpgsql
stable
security definer
set search_path = ''
as $$
#variable_conflict use_column
begin
  if not api.is_active_reviewer() then
    raise exception 'acesso restrito a revisores ativos' using errcode = '42501';
  end if;
  return query
  with current_sample as (
    select sample.id, sample.sample_version
    from editorial.act_quality_samples as sample
    order by sample.created_at desc, sample.id desc
    limit 1
  )
  select
    page.id,
    current_sample.sample_version,
    page.stratum,
    page.sample_rank,
    page.edition,
    page.edition_year,
    page.page_number,
    page.text_source,
    page.pdf_url || '#page=' || page.page_number::text,
    coalesce((
      select jsonb_agg(jsonb_build_object(
        'result_id', act.extraction_result_id,
        'act_type', act.act_type,
        'published', act.published,
        'person_name', result.result_payload -> 'fields' -> 'person_name' ->> 'value',
        'position', result.result_payload -> 'fields' -> 'position' ->> 'value',
        'excerpt', left(editorial.mask_cpf_v1(result.result_payload ->> 'excerpt'), 700)
      ) order by (result.result_payload ->> 'match_start')::integer)
      from editorial.act_quality_sample_acts as act
      join raw.extraction_results as result
        on result.id = act.extraction_result_id
      where act.sample_page_id = page.id
    ), '[]'::jsonb),
    (
      select jsonb_build_object(
        'act_verdicts', annotation.act_verdicts,
        'missed_nomeacoes', annotation.missed_nomeacoes,
        'missed_exoneracoes', annotation.missed_exoneracoes,
        'note', annotation.note,
        'created_at', annotation.created_at,
        'annotator', case
          when annotation.reviewer_subject like 'ai:%'
          then annotation.reviewer_subject else 'human' end
      )
      from editorial.act_quality_annotations as annotation
      where annotation.sample_page_id = page.id
      order by annotation.created_at desc, annotation.id desc
      limit 1
    )
  from current_sample
  join editorial.act_quality_sample_pages as page
    on page.sample_id = current_sample.id
  order by page.stratum, page.sample_rank;
end;
$$;

create function api.get_act_quality_metrics(p_source text default 'any')
returns table (
  scope text,
  population integer,
  sampled integer,
  annotated integer,
  acts_judged integer,
  acts_correct integer,
  acts_partial integer,
  acts_incorrect integer,
  missed integer,
  precision_strict numeric,
  precision_lenient numeric,
  recall_estimate numeric,
  methodology_version text
)
language plpgsql
stable
security definer
set search_path = ''
as $$
#variable_conflict use_column
begin
  if not api.is_active_reviewer() then
    raise exception 'acesso restrito a revisores ativos' using errcode = '42501';
  end if;
  if p_source not in ('any', 'human', 'ai') then
    raise exception 'fonte deve ser any, human ou ai' using errcode = '22023';
  end if;
  return query
  with current_sample as (
    select sample.id, sample.strata
    from editorial.act_quality_samples as sample
    order by sample.created_at desc, sample.id desc
    limit 1
  ), latest as (
    select distinct on (annotation.sample_page_id) annotation.*
    from editorial.act_quality_annotations as annotation
    join editorial.act_quality_sample_pages as page
      on page.id = annotation.sample_page_id
    join current_sample on current_sample.id = page.sample_id
    where p_source = 'any'
      or (p_source = 'ai') = (annotation.reviewer_subject like 'ai:%')
    order by annotation.sample_page_id, annotation.created_at desc,
      annotation.id desc
  ), page_facts as (
    select
      page.stratum,
      latest.sample_page_id is not null as is_annotated,
      coalesce(latest.missed_nomeacoes, 0) as missed_nomeacoes,
      coalesce(latest.missed_exoneracoes, 0) as missed_exoneracoes,
      act.act_type,
      latest.act_verdicts ->> act.extraction_result_id::text as verdict
    from current_sample
    join editorial.act_quality_sample_pages as page
      on page.sample_id = current_sample.id
    left join latest on latest.sample_page_id = page.id
    left join editorial.act_quality_sample_acts as act
      on act.sample_page_id = page.id
  ), per_stratum as (
    select
      strata.key as stratum,
      (strata.value ->> 'population')::integer as population,
      (strata.value ->> 'sampled')::integer as sampled,
      (
        select count(distinct page.id)::integer
        from editorial.act_quality_sample_pages as page
        join latest on latest.sample_page_id = page.id
        where page.sample_id = current_sample.id and page.stratum = strata.key
      ) as annotated
    from current_sample
    cross join lateral jsonb_each(current_sample.strata) as strata
    where strata.key <> '_excluded'
  ), scoped as (
    select
      scope_name.scope,
      facts.stratum,
      count(*) filter (where facts.verdict is not null)::integer as judged,
      count(*) filter (where facts.verdict = 'correct')::integer as correct,
      count(*) filter (where facts.verdict = 'partial')::integer as partial,
      count(*) filter (where facts.verdict = 'incorrect')::integer as incorrect
    from page_facts as facts
    cross join (values ('overall'), ('nomeacao'), ('exoneracao')) as scope_name(scope)
    where facts.is_annotated
      and (scope_name.scope = 'overall' or facts.act_type = scope_name.scope)
    group by scope_name.scope, facts.stratum
  ), missed_by_page as (
    select distinct on (latest.sample_page_id)
      page.stratum, latest.missed_nomeacoes, latest.missed_exoneracoes
    from latest
    join editorial.act_quality_sample_pages as page
      on page.id = latest.sample_page_id
  ), missed_scoped as (
    select
      scope_name.scope,
      missed_by_page.stratum,
      sum(case scope_name.scope
        when 'nomeacao' then missed_by_page.missed_nomeacoes
        when 'exoneracao' then missed_by_page.missed_exoneracoes
        else missed_by_page.missed_nomeacoes + missed_by_page.missed_exoneracoes
      end)::integer as missed
    from missed_by_page
    cross join (values ('overall'), ('nomeacao'), ('exoneracao')) as scope_name(scope)
    group by scope_name.scope, missed_by_page.stratum
  ), weighted as (
    select
      scopes.scope,
      per_stratum.stratum,
      per_stratum.population,
      per_stratum.sampled,
      per_stratum.annotated,
      coalesce(scoped.judged, 0) as judged,
      coalesce(scoped.correct, 0) as correct,
      coalesce(scoped.partial, 0) as partial,
      coalesce(scoped.incorrect, 0) as incorrect,
      coalesce(missed_scoped.missed, 0) as missed,
      case when per_stratum.annotated > 0
        then per_stratum.population::numeric / per_stratum.annotated
        else 0 end as weight
    from per_stratum
    cross join (values ('overall'), ('nomeacao'), ('exoneracao')) as scopes(scope)
    left join scoped
      on scoped.scope = scopes.scope and scoped.stratum = per_stratum.stratum
    left join missed_scoped
      on missed_scoped.scope = scopes.scope
     and missed_scoped.stratum = per_stratum.stratum
  )
  select
    case when weighted.scope = 'overall'
      then weighted.stratum else weighted.scope || ':' || weighted.stratum end,
    weighted.population, weighted.sampled, weighted.annotated,
    weighted.judged, weighted.correct, weighted.partial, weighted.incorrect,
    weighted.missed,
    case when weighted.judged > 0
      then round(weighted.correct::numeric / weighted.judged, 4) end,
    case when weighted.judged > 0
      then round((weighted.correct + weighted.partial)::numeric
        / weighted.judged, 4) end,
    case when weighted.correct + weighted.partial + weighted.missed > 0
      then round((weighted.correct + weighted.partial)::numeric
        / (weighted.correct + weighted.partial + weighted.missed), 4) end,
    'act-quality-metrics/1.1.0'::text
  from weighted
  union all
  select
    'total:' || weighted.scope,
    sum(weighted.population)::integer,
    sum(weighted.sampled)::integer,
    sum(weighted.annotated)::integer,
    sum(weighted.judged)::integer,
    sum(weighted.correct)::integer,
    sum(weighted.partial)::integer,
    sum(weighted.incorrect)::integer,
    sum(weighted.missed)::integer,
    case when sum(weighted.weight * weighted.judged) > 0
      then round(sum(weighted.weight * weighted.correct)
        / sum(weighted.weight * weighted.judged), 4) end,
    case when sum(weighted.weight * weighted.judged) > 0
      then round(sum(weighted.weight * (weighted.correct + weighted.partial))
        / sum(weighted.weight * weighted.judged), 4) end,
    case when sum(weighted.weight
        * (weighted.correct + weighted.partial + weighted.missed)) > 0
      then round(sum(weighted.weight * (weighted.correct + weighted.partial))
        / sum(weighted.weight
          * (weighted.correct + weighted.partial + weighted.missed)), 4) end,
    'act-quality-metrics/1.1.0'::text
  from weighted
  group by weighted.scope
  order by 1;
end;
$$;

revoke all on function api.get_act_quality_metrics(text) from public, anon;
grant execute on function api.get_act_quality_metrics(text) to authenticated;

commit;
