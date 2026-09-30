begin;

-- A amostra 1.0.0 mede a régua gazette-act-candidates/2.3.0 e ainda juntava
-- atos de réguas anteriores (o mesmo ato repetido). A amostra passa a medir
-- uma régua só, registrada em `ruleset_version`, e é criada automaticamente
-- quando o reprocessamento do acervo por aquela régua termina.

alter table editorial.act_quality_samples
  add column ruleset_version text check (
    ruleset_version is null
    or ruleset_version ~ '^gazette-act-candidates/[0-9]+\.[0-9]+\.[0-9]+$'
  );

comment on column editorial.act_quality_samples.ruleset_version is
  'Régua de candidatos medida pela amostra; nula na 1.0.0 (várias réguas).';

drop function editorial.create_act_quality_sample(text, text, integer);

create function editorial.create_act_quality_sample(
  p_version text,
  p_seed text,
  p_per_stratum integer,
  p_ruleset text
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
  if p_ruleset !~ '^gazette-act-candidates/[0-9]+\.[0-9]+\.[0-9]+$' then
    raise exception 'régua inválida' using errcode = '22023';
  end if;
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
    -- Só edições já processadas pela régua medida.
    and exists (
      select 1 from raw.extraction_jobs as job
      where job.raw_artifact_id = artifact.id
        and job.job_type = 'gazette_act_candidates'
        and job.status = 'succeeded'
        and (
          job.extractor_version = p_ruleset
          or job.idempotency_key = encode(sha256(convert_to(
            'gazette-acts:' || artifact.sha256 || ':' || p_ruleset, 'UTF8'
          )), 'hex')
        )
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
      -- Régua antiga deixava o mesmo ato repetido na amostra 1.0.0.
      and result.extractor_version = p_ruleset
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
    sample_version, seed, per_stratum, ruleset_version, strata, methodology
  ) values (
    p_version,
    p_seed,
    p_per_stratum,
    p_ruleset,
    coalesce(strata_summary, '{}'::jsonb) || jsonb_build_object(
      '_excluded', jsonb_build_object(
        'unverified_artifacts', unverified_artifacts,
        'unmapped_acts', unmapped_acts
      )
    ),
    'Páginas de PDFs próprios do Diário (edições processadas pela régua '
      || p_ruleset || '), estratificadas '
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

revoke all on function editorial.create_act_quality_sample(text, text, integer, text)
  from public, anon, authenticated, service_role;

-- Cria a amostra da régua vigente quando nenhuma edição já processada por
-- régua anterior está à espera. Idempotente: com a amostra criada, só informa.
create function editorial.ensure_act_quality_sample(p_ruleset text)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
#variable_conflict use_column
declare
  existing text;
  pending integer;
  processed integer;
  next_version text;
begin
  if p_ruleset !~ '^gazette-act-candidates/[0-9]+\.[0-9]+\.[0-9]+$' then
    raise exception 'régua inválida' using errcode = '22023';
  end if;
  select sample.sample_version into existing
  from editorial.act_quality_samples as sample
  where sample.ruleset_version = p_ruleset
  order by sample.created_at desc
  limit 1;
  if existing is not null then
    return jsonb_build_object('status', 'current', 'sample_version', existing);
  end if;

  select
    count(*) filter (where not status.done)::integer,
    count(*) filter (where status.done)::integer
  into pending, processed
  from (
    select exists (
      select 1 from raw.extraction_jobs as job
      where job.raw_artifact_id = artifact.id
        and job.job_type = 'gazette_act_candidates'
        and (
          job.extractor_version = p_ruleset
          or job.idempotency_key = encode(sha256(convert_to(
            'gazette-acts:' || artifact.sha256 || ':' || p_ruleset, 'UTF8'
          )), 'hex')
        )
        -- Falha transitória ainda vai ser tentada de novo.
        and not (
          job.status = 'failed'
          and job.last_error_code = 'processing_error'
          and job.attempt_count < job.max_attempts
        )
    ) as done
    from raw.raw_artifacts as artifact
    where artifact.metadata ->> 'schema_name' = 'gazette-direct-edition'
      and artifact.content_type = 'application/pdf'
      -- Edição que alguma régua já processou; as nunca processadas
      -- (aguardando OCR) não seguram a amostra.
      and exists (
        select 1 from raw.extraction_jobs as earlier
        where earlier.raw_artifact_id = artifact.id
          and earlier.job_type = 'gazette_act_candidates'
          and earlier.status = 'succeeded'
      )
      -- Cópia servida no lugar de outra edição: a fila de atos a ignora.
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
      )
  ) as status;

  if pending > 0 or processed = 0 then
    return jsonb_build_object(
      'status', 'waiting', 'pending', pending, 'processed', processed
    );
  end if;

  select 'act-quality-sample/1.' || count(*)::text || '.0' into next_version
  from editorial.act_quality_samples;
  perform editorial.create_act_quality_sample(
    next_version, 'barreiras-act-quality-' || p_ruleset, 20, p_ruleset
  );
  return jsonb_build_object(
    'status', 'created', 'sample_version', next_version, 'processed', processed
  );
end;
$$;

revoke all on function editorial.ensure_act_quality_sample(text)
  from public, anon, authenticated, service_role;
grant execute on function editorial.ensure_act_quality_sample(text)
  to collector_worker;

commit;
