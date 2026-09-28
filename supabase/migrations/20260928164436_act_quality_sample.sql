begin;

-- Amostra anotada para medir precisão e revocação da extração de atos
-- (nomeação e exoneração) do Diário Oficial. Unidade: página do PDF oficial.
-- A página de cada ato é derivada do texto canônico reconstruído a partir de
-- raw.document_pages e só é aceita quando o hash bate com o registrado no ato.
-- A anotação é humana e fica separada de editorial.editorial_reviews: medir a
-- qualidade nunca altera o que está publicado.

create table editorial.act_quality_samples (
  id uuid primary key default gen_random_uuid(),
  sample_version text not null unique check (
    sample_version ~ '^act-quality-sample/[0-9]+\.[0-9]+\.[0-9]+$'
  ),
  seed text not null check (length(btrim(seed)) between 8 and 200),
  per_stratum integer not null check (per_stratum between 1 and 200),
  strata jsonb not null check (jsonb_typeof(strata) = 'object'),
  methodology text not null check (length(btrim(methodology)) > 0),
  created_at timestamptz not null default statement_timestamp()
);

create table editorial.act_quality_sample_pages (
  id uuid primary key default gen_random_uuid(),
  sample_id uuid not null references editorial.act_quality_samples(id),
  stratum text not null check (stratum in (
    'act_embedded', 'act_ocr', 'keyword_embedded', 'keyword_ocr',
    'other_embedded', 'other_ocr'
  )),
  sample_rank integer not null check (sample_rank > 0),
  raw_artifact_id uuid not null references raw.raw_artifacts(id),
  artifact_sha256 text not null check (artifact_sha256 ~ '^[a-f0-9]{64}$'),
  edition integer not null check (edition > 0),
  edition_year integer not null check (edition_year between 2000 and 2100),
  page_number integer not null check (page_number > 0),
  text_source text not null check (text_source in ('embedded', 'ocr')),
  pdf_url text not null check (pdf_url ~ '^https://'),
  created_at timestamptz not null default statement_timestamp(),
  unique (sample_id, raw_artifact_id, page_number),
  unique (sample_id, stratum, sample_rank)
);

create table editorial.act_quality_sample_acts (
  sample_page_id uuid not null
    references editorial.act_quality_sample_pages(id),
  extraction_result_id uuid not null references raw.extraction_results(id),
  act_type text not null check (act_type in ('nomeacao', 'exoneracao')),
  published boolean not null,
  primary key (sample_page_id, extraction_result_id)
);

create table editorial.act_quality_annotations (
  id uuid primary key default gen_random_uuid(),
  sample_page_id uuid not null
    references editorial.act_quality_sample_pages(id),
  reviewer_subject text not null check (length(btrim(reviewer_subject)) > 0),
  act_verdicts jsonb not null check (jsonb_typeof(act_verdicts) = 'object'),
  missed_nomeacoes integer not null check (missed_nomeacoes between 0 and 200),
  missed_exoneracoes integer not null
    check (missed_exoneracoes between 0 and 200),
  note text check (note is null or length(note) <= 1000),
  created_at timestamptz not null default statement_timestamp()
);

create index act_quality_sample_pages_artifact_idx
  on editorial.act_quality_sample_pages (raw_artifact_id);

create index act_quality_sample_acts_result_idx
  on editorial.act_quality_sample_acts (extraction_result_id);

create index act_quality_annotations_page_idx
  on editorial.act_quality_annotations (sample_page_id, created_at desc, id desc);

do $$
declare
  relation_name text;
begin
  foreach relation_name in array array[
    'editorial.act_quality_samples',
    'editorial.act_quality_sample_pages',
    'editorial.act_quality_sample_acts',
    'editorial.act_quality_annotations'
  ]
  loop
    execute format(
      'create trigger reject_mutation before update or delete on %s '
      'for each row execute function audit.reject_mutation()',
      relation_name
    );
    execute format('alter table %s enable row level security', relation_name);
    execute format(
      'revoke all on %s from public, anon, authenticated', relation_name
    );
  end loop;
end
$$;

-- Texto de cada página como a extração o montou: texto embutido, ou o OCR
-- quando o embutido falta ou é só o número da página. `ocr_version` nulo
-- escolhe o OCR mais recente da página.
create function editorial.act_quality_page_parts(
  p_artifact_id uuid,
  p_embedded_version text,
  p_ocr_version text
)
returns table (page_number integer, part text, text_source text)
language sql
stable
set search_path = ''
as $$
  select
    embedded.page_number,
    case
      when embedded.text_content is null
        or btrim(embedded.text_content, E' \n\t\r')
          = embedded.page_number::text
      then ocr.text_content
      else embedded.text_content
    end,
    case
      when embedded.text_content is null
        or btrim(embedded.text_content, E' \n\t\r')
          = embedded.page_number::text
      then 'ocr'
      else 'embedded'
    end
  from raw.document_pages as embedded
  left join lateral (
    select candidate.text_content
    from raw.document_pages as candidate
    where candidate.raw_artifact_id = embedded.raw_artifact_id
      and candidate.page_number = embedded.page_number
      and candidate.extraction_method = 'ocr'
      and candidate.text_content is not null
      and (p_ocr_version is null or candidate.parser_version = p_ocr_version)
    order by candidate.created_at desc, candidate.id desc
    limit 1
  ) as ocr on true
  where embedded.raw_artifact_id = p_artifact_id
    and embedded.parser_version = p_embedded_version
$$;

create function editorial.create_act_quality_sample(
  p_version text,
  p_seed text,
  p_per_stratum integer
)
returns uuid
language plpgsql
security definer
set search_path = ''
as $$
#variable_conflict use_column
declare
  v_sample_id uuid;
  artifact record;
  variant record;
  chosen_embedded text;
  chosen_ocr text;
  rebuilt_sha text;
  strata_summary jsonb;
  unmapped_acts integer;
  unverified_artifacts integer := 0;
begin
  create temporary table act_quality_eligible on commit drop as
  select
    artifact.id,
    artifact.sha256,
    (artifact.metadata ->> 'edition')::integer as edition,
    (artifact.metadata ->> 'year')::integer as edition_year,
    artifact.source_url
  from raw.raw_artifacts as artifact
  where artifact.metadata ->> 'schema_name' = 'gazette-direct-edition'
    and artifact.content_type = 'application/pdf'
    and coalesce(artifact.metadata ->> 'edition', '') ~ '^[0-9]{1,6}$'
    and coalesce(artifact.metadata ->> 'year', '') ~ '^[0-9]{4}$'
    and artifact.source_url ~ '^https://'
    and exists (
      select 1 from raw.extraction_jobs as job
      where job.raw_artifact_id = artifact.id
    )
    -- Cópia servida pelo catálogo no lugar de outra edição (mesma regra da
    -- fila de OCR): o PDF não é da edição que o nome indica.
    and not exists (
      select 1
      from raw.raw_artifacts as other_edition
      where other_edition.metadata ->> 'schema_name' = 'gazette-direct-edition'
        and other_edition.sha256 = artifact.sha256
        and other_edition.metadata ->> 'edition'
          <> artifact.metadata ->> 'edition'
        and other_edition.metadata ->> 'edition' = substring(
          artifact.metadata ->> 'final_url'
          from '/diario([0-9]+)(?:-[A-Za-z0-9-]+)?\.pdf$'
        )
    );

  -- Atos vigentes (não substituídos por outro do mesmo tipo) do texto
  -- canônico mais recente de cada edição.
  create temporary table act_quality_acts on commit drop as
  with acts as (
    select
      result.id as result_id,
      result.candidate_type as act_type,
      job.raw_artifact_id,
      (result.result_payload ->> 'match_start')::integer as match_start,
      result.result_payload ->> 'canonical_text_sha256' as canonical_sha,
      result.created_at
    from raw.extraction_results as result
    join raw.extraction_jobs as job on job.id = result.extraction_job_id
    join act_quality_eligible as eligible on eligible.id = job.raw_artifact_id
    where result.candidate_type in ('nomeacao', 'exoneracao')
      and result.result_payload ->> 'match_start' ~ '^[0-9]+$'
      and not exists (
        select 1 from raw.extraction_results as newer
        where newer.supersedes_id = result.id
          and newer.candidate_type = result.candidate_type
      )
  ), latest as (
    select distinct on (raw_artifact_id) raw_artifact_id, canonical_sha
    from acts
    order by raw_artifact_id, created_at desc, result_id desc
  )
  select acts.*
  from acts
  join latest
    on latest.raw_artifact_id = acts.raw_artifact_id
   and latest.canonical_sha = acts.canonical_sha;

  create temporary table act_quality_pages (
    raw_artifact_id uuid,
    page_number integer,
    part text,
    text_source text,
    start_offset integer
  ) on commit drop;

  for artifact in
    select eligible.id,
      (select acts.canonical_sha from act_quality_acts as acts
       where acts.raw_artifact_id = eligible.id limit 1) as canonical_sha
    from act_quality_eligible as eligible
  loop
    chosen_embedded := null;
    chosen_ocr := null;
    for variant in
      select * from (values
        (1, 'gazette-pdf-embedded-text/1.1.0', 'gazette-ocr-text/1.0.0'),
        (2, 'gazette-pdf-embedded-text/1.1.0', 'gazette-ocr-text/1.1.0'),
        (3, 'gazette-pdf-embedded-text/1.0.0', 'gazette-ocr-text/1.0.0'),
        (4, 'gazette-pdf-embedded-text/1.0.0', 'gazette-ocr-text/1.1.0')
      ) as candidates(priority, embedded_version, ocr_version)
      order by priority
    loop
      if not exists (
        select 1 from raw.document_pages as page
        where page.raw_artifact_id = artifact.id
          and page.parser_version = variant.embedded_version
      ) then
        continue;
      end if;
      if artifact.canonical_sha is null then
        -- Sem ato não há hash a conferir: vale o texto embutido mais novo
        -- com o OCR mais recente.
        chosen_embedded := variant.embedded_version;
        chosen_ocr := null;
        exit;
      end if;
      select encode(sha256(convert_to(
        string_agg(parts.part, E'\n\n' order by parts.page_number)
          filter (where parts.part is not null and parts.part <> ''),
        'UTF8')), 'hex')
      into rebuilt_sha
      from editorial.act_quality_page_parts(
        artifact.id, variant.embedded_version, variant.ocr_version
      ) as parts;
      if rebuilt_sha = artifact.canonical_sha then
        chosen_embedded := variant.embedded_version;
        chosen_ocr := variant.ocr_version;
        exit;
      end if;
    end loop;

    if chosen_embedded is null then
      -- Texto que não reproduz o hash do ato: a página do ato seria
      -- incerta, então a edição fica fora da amostra (contada no resumo).
      unverified_artifacts := unverified_artifacts + 1;
      delete from act_quality_acts where raw_artifact_id = artifact.id;
      continue;
    end if;

    insert into act_quality_pages
    select
      artifact.id,
      parts.page_number,
      parts.part,
      parts.text_source,
      coalesce(sum(length(parts.part) + 2) over (
        order by parts.page_number
        rows between unbounded preceding and 1 preceding
      ), 0)::integer
    from editorial.act_quality_page_parts(
      artifact.id, chosen_embedded, chosen_ocr
    ) as parts
    where parts.part is not null and parts.part <> '';
  end loop;

  create temporary table act_quality_act_pages on commit drop as
  select acts.result_id, acts.act_type, pages.raw_artifact_id, pages.page_number
  from act_quality_acts as acts
  join act_quality_pages as pages
    on pages.raw_artifact_id = acts.raw_artifact_id
   and acts.match_start >= pages.start_offset
   and acts.match_start < pages.start_offset + length(pages.part);

  select count(*) into unmapped_acts
  from act_quality_acts as acts
  where not exists (
    select 1 from act_quality_act_pages as mapped
    where mapped.result_id = acts.result_id
  );

  create temporary table act_quality_strata on commit drop as
  select
    pages.raw_artifact_id,
    pages.page_number,
    pages.text_source,
    case
      when exists (
        select 1 from act_quality_act_pages as mapped
        where mapped.raw_artifact_id = pages.raw_artifact_id
          and mapped.page_number = pages.page_number
      ) then 'act'
      when pages.part ~* '(nome[ai]|exoner)' then 'keyword'
      else 'other'
    end || '_' || pages.text_source as stratum
  from act_quality_pages as pages;

  select jsonb_object_agg(counts.stratum, jsonb_build_object(
    'population', counts.population,
    'sampled', least(counts.population, p_per_stratum)
  ))
  into strata_summary
  from (
    select stratum, count(*)::integer as population
    from act_quality_strata
    group by stratum
  ) as counts;

  insert into editorial.act_quality_samples (
    sample_version, seed, per_stratum, strata, methodology
  ) values (
    p_version,
    p_seed,
    p_per_stratum,
    coalesce(strata_summary, '{}'::jsonb) || jsonb_build_object(
      '_excluded', jsonb_build_object(
        'unverified_artifacts', unverified_artifacts,
        'unmapped_acts', unmapped_acts
      )
    ),
    'Páginas de PDFs próprios do Diário (edições com extração), estratificadas '
    'por ato extraído / palavra-chave (nome[ai]|exoner) / demais e por origem '
    'do texto; sorteio por sha256(semente:hash do PDF:página). Edições do '
    'Querido Diário (texto sem página) ficam fora.'
  )
  returning id into v_sample_id;

  insert into editorial.act_quality_sample_pages (
    sample_id, stratum, sample_rank, raw_artifact_id, artifact_sha256,
    edition, edition_year, page_number, text_source, pdf_url
  )
  select
    v_sample_id,
    ranked.stratum,
    ranked.sample_rank,
    ranked.raw_artifact_id,
    eligible.sha256,
    eligible.edition,
    eligible.edition_year,
    ranked.page_number,
    ranked.text_source,
    eligible.source_url
  from (
    select
      strata.*,
      row_number() over (
        partition by strata.stratum
        order by encode(sha256(convert_to(
          p_seed || ':' || eligible.sha256 || ':' || strata.page_number::text,
          'UTF8')), 'hex')
      )::integer as sample_rank
    from act_quality_strata as strata
    join act_quality_eligible as eligible
      on eligible.id = strata.raw_artifact_id
  ) as ranked
  join act_quality_eligible as eligible on eligible.id = ranked.raw_artifact_id
  where ranked.sample_rank <= p_per_stratum;

  insert into editorial.act_quality_sample_acts (
    sample_page_id, extraction_result_id, act_type, published
  )
  select
    sampled.id,
    mapped.result_id,
    mapped.act_type,
    coalesce((
      select review.decision = 'approved'
      from editorial.editorial_reviews as review
      where review.target_type = 'raw.extraction_results'
        and review.target_id = mapped.result_id
      order by review.reviewed_at desc, review.id desc
      limit 1
    ), false)
  from editorial.act_quality_sample_pages as sampled
  join act_quality_act_pages as mapped
    on mapped.raw_artifact_id = sampled.raw_artifact_id
   and mapped.page_number = sampled.page_number
  where sampled.sample_id = v_sample_id;

  return v_sample_id;
end;
$$;

revoke all on function editorial.act_quality_page_parts(uuid, text, text)
  from public, anon, authenticated, service_role;
revoke all on function editorial.create_act_quality_sample(text, text, integer)
  from public, anon, authenticated, service_role;

create function api.get_act_quality_sample()
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
        'created_at', annotation.created_at
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

create function api.annotate_act_quality_page(
  p_sample_page_id uuid,
  p_act_verdicts jsonb,
  p_missed_nomeacoes integer,
  p_missed_exoneracoes integer,
  p_note text default null
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
  if not api.is_active_reviewer() then
    raise exception 'acesso restrito a revisores ativos' using errcode = '42501';
  end if;
  if not exists (
    select 1 from editorial.act_quality_sample_pages as page
    where page.id = p_sample_page_id
  ) then
    raise exception 'página da amostra inexistente' using errcode = '22023';
  end if;
  if jsonb_typeof(p_act_verdicts) is distinct from 'object' then
    raise exception 'veredito dos atos inválido' using errcode = '22023';
  end if;
  select coalesce(array_agg(act.extraction_result_id::text order by act.extraction_result_id::text), '{}')
  into expected_ids
  from editorial.act_quality_sample_acts as act
  where act.sample_page_id = p_sample_page_id;
  select coalesce(array_agg(key order by key), '{}')
  into given_ids
  from jsonb_object_keys(p_act_verdicts) as key;
  if expected_ids is distinct from given_ids then
    raise exception 'cada ato da página precisa de exatamente um veredito'
      using errcode = '22023';
  end if;
  if exists (
    select 1 from jsonb_each_text(p_act_verdicts) as verdict
    where verdict.value not in ('correct', 'partial', 'incorrect')
  ) then
    raise exception 'veredito deve ser correct, partial ou incorrect'
      using errcode = '22023';
  end if;
  if p_missed_nomeacoes is null or p_missed_exoneracoes is null
    or p_missed_nomeacoes not between 0 and 200
    or p_missed_exoneracoes not between 0 and 200 then
    raise exception 'contagem de atos não extraídos inválida'
      using errcode = '22023';
  end if;
  insert into editorial.act_quality_annotations (
    sample_page_id, reviewer_subject, act_verdicts,
    missed_nomeacoes, missed_exoneracoes, note
  ) values (
    p_sample_page_id,
    auth.uid()::text,
    p_act_verdicts,
    p_missed_nomeacoes,
    p_missed_exoneracoes,
    nullif(btrim(coalesce(p_note, '')), '')
  )
  returning id into annotation_id;
  return annotation_id;
end;
$$;

-- Estimativa estratificada, determinística e versionada. Cada página anotada
-- representa population/annotated páginas do seu estrato. Achado = correct
-- ou partial; precisão estrita só conta correct.
create function api.get_act_quality_metrics()
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
    'act-quality-metrics/1.0.0'::text
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
    'act-quality-metrics/1.0.0'::text
  from weighted
  group by weighted.scope
  order by 1;
end;
$$;

revoke all on function api.get_act_quality_sample() from public, anon;
revoke all on function api.annotate_act_quality_page(uuid, jsonb, integer, integer, text)
  from public, anon;
revoke all on function api.get_act_quality_metrics() from public, anon;
grant execute on function api.get_act_quality_sample() to authenticated;
grant execute on function api.annotate_act_quality_page(uuid, jsonb, integer, integer, text)
  to authenticated;
grant execute on function api.get_act_quality_metrics() to authenticated;

select editorial.create_act_quality_sample(
  'act-quality-sample/1.0.0',
  'barreiras-act-quality-2026-09-28',
  20
);

commit;
