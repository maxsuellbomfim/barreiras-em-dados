-- Projecao deterministica das emendas destinadas a Barreiras preservadas no
-- Transferegov. Autoria individual e autoria coletiva nunca sao misturadas.
-- Os estagios financeiros so sao atribuidos quando a proposta possui uma
-- unica distribuicao de recurso; ambiguidade permanece explicita e sem soma.

create schema if not exists territory;

revoke all on schema territory from public;
revoke all on schema territory from anon, authenticated;

-- A projecao consulta somente o subconjunto Transferegov e sempre seleciona a
-- versao bruta mais recente. Os indices abaixo evitam varreduras integrais do
-- acervo append-only conforme o historico crescer.
create index if not exists raw_records_transferegov_latest_idx
  on raw.raw_records (
    record_type,
    source_record_key,
    collected_at desc,
    id desc
  )
  where record_type in (
    'transferegov_proposta',
    'transferegov_distribuicao_recurso',
    'transferegov_parceria',
    'transferegov_empenho',
    'transferegov_documento_habil',
    'transferegov_ordem_pagamento',
    'transferegov_ordem_bancaria'
  )
    and source_record_key is not null;

create index if not exists raw_records_transferegov_proposal_idx
  on raw.raw_records ((payload ->> 'id_proposta'))
  where record_type in (
    'transferegov_proposta',
    'transferegov_distribuicao_recurso',
    'transferegov_parceria'
  );

create index if not exists raw_records_transferegov_partnership_idx
  on raw.raw_records ((payload ->> 'id_parceria'))
  where record_type in (
    'transferegov_parceria',
    'transferegov_empenho',
    'transferegov_documento_habil'
  );

create index if not exists raw_records_transferegov_document_idx
  on raw.raw_records ((payload ->> 'id_documento_habil'))
  where record_type in (
    'transferegov_documento_habil',
    'transferegov_ordem_pagamento'
  );

create view territory.latest_transferegov_records
with (security_barrier = true)
as
select distinct on (record.record_type, record.source_record_key)
  record.id as raw_record_id,
  record.raw_artifact_id,
  record.source_record_key,
  record.record_type,
  record.payload,
  record.collected_at
from raw.raw_records as record
where record.record_type in (
  'transferegov_proposta',
  'transferegov_distribuicao_recurso',
  'transferegov_parceria',
  'transferegov_empenho',
  'transferegov_documento_habil',
  'transferegov_ordem_pagamento',
  'transferegov_ordem_bancaria'
)
  and record.source_record_key is not null
order by
  record.record_type,
  record.source_record_key,
  record.collected_at desc,
  record.id desc;

create view territory.parliamentary_transfers
with (security_barrier = true)
as
with proposals as (
  select
    latest.raw_record_id,
    latest.raw_artifact_id,
    latest.payload ->> 'id_proposta' as proposal_id,
    case
      when latest.payload ->> 'ano_proposta' ~ '^[0-9]{4}$'
      then (latest.payload ->> 'ano_proposta')::smallint
    end as fiscal_year,
    nullif(btrim(latest.payload ->> 'ds_objeto'), '') as object_description,
    nullif(btrim(latest.payload ->> 'nm_ente_recebedor'), '') as beneficiary_name,
    nullif(btrim(latest.payload ->> 'situacao_proposta'), '') as proposal_status,
    case
      when latest.payload ->> 'vl_total_planejamento_gastos'
        ~ '^-?[0-9]+(?:[.][0-9]+)?$'
      then (latest.payload ->> 'vl_total_planejamento_gastos')::numeric(20,2)
    end as proposal_amount,
    latest.collected_at
  from territory.latest_transferegov_records as latest
  where latest.record_type = 'transferegov_proposta'
    and latest.payload ->> 'id_proposta' ~ '^[0-9]+$'
),
distributions as (
  select
    latest.raw_record_id,
    latest.raw_artifact_id,
    latest.source_record_key,
    latest.payload ->> 'id_distribuicao_recurso_proposta' as distribution_id,
    latest.payload ->> 'id_proposta' as proposal_id,
    nullif(btrim(latest.payload ->> 'nm_parlamentar_proposta'), '') as author_name,
    nullif(btrim(latest.payload ->> 'nr_emenda_proposta'), '') as amendment_number,
    nullif(btrim(latest.payload ->> 'in_tipo_distribuicao'), '') as distribution_kind,
    nullif(
      btrim(latest.payload ->> 'in_tipo_emenda_parlamentar_proposta'),
      ''
    ) as amendment_kind,
    case
      when latest.payload ->> 'valor_emenda' ~ '^-?[0-9]+(?:[.][0-9]+)?$'
      then (latest.payload ->> 'valor_emenda')::numeric(20,2)
    end as destination_amount,
    latest.collected_at
  from territory.latest_transferegov_records as latest
  where latest.record_type = 'transferegov_distribuicao_recurso'
    and latest.payload ->> 'id_distribuicao_recurso_proposta' ~ '^[0-9]+$'
    and latest.payload ->> 'id_proposta' ~ '^[0-9]+$'
),
distribution_counts as (
  select proposal_id, count(*)::integer as distribution_count
  from distributions
  group by proposal_id
),
partnerships as (
  select
    latest.payload ->> 'id_parceria' as partnership_id,
    latest.payload ->> 'id_proposta' as proposal_id
  from territory.latest_transferegov_records as latest
  where latest.record_type = 'transferegov_parceria'
    and latest.payload ->> 'id_parceria' ~ '^[0-9]+$'
    and latest.payload ->> 'id_proposta' ~ '^[0-9]+$'
),
commitment_totals as (
  select
    partnership.proposal_id,
    sum(
      case
        when latest.payload ->> 'valor_empenho' ~ '^-?[0-9]+(?:[.][0-9]+)?$'
        then (latest.payload ->> 'valor_empenho')::numeric(20,2)
      end
    )::numeric(20,2) as committed_amount
  from territory.latest_transferegov_records as latest
  join partnerships as partnership
    on partnership.partnership_id = latest.payload ->> 'id_parceria'
  where latest.record_type = 'transferegov_empenho'
  group by partnership.proposal_id
),
payable_documents as (
  select
    latest.payload ->> 'id_documento_habil' as document_id,
    partnership.proposal_id
  from territory.latest_transferegov_records as latest
  join partnerships as partnership
    on partnership.partnership_id = latest.payload ->> 'id_parceria'
  where latest.record_type = 'transferegov_documento_habil'
    and latest.payload ->> 'id_documento_habil' ~ '^[0-9]+$'
),
payment_totals as (
  select
    document.proposal_id,
    sum(
      case
        when lower(btrim(latest.payload ->> 'in_situacao_op')) = 'paga'
          and latest.payload ->> 'vl_ordem_pagamento'
            ~ '^-?[0-9]+(?:[.][0-9]+)?$'
        then (latest.payload ->> 'vl_ordem_pagamento')::numeric(20,2)
      end
    )::numeric(20,2) as paid_amount,
    case
      when count(distinct nullif(
        btrim(latest.payload ->> 'nr_ordem_bancaria'), ''
      )) = 1
      then max(nullif(btrim(latest.payload ->> 'nr_ordem_bancaria'), ''))
    end as bank_order_number,
    case
      when count(distinct nullif(
        btrim(latest.payload ->> 'dt_emissao_ordem_bancaria'), ''
      )) = 1
        and max(nullif(btrim(
          latest.payload ->> 'dt_emissao_ordem_bancaria'
        ), '')) ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
      then max(nullif(btrim(
        latest.payload ->> 'dt_emissao_ordem_bancaria'
      ), ''))::date
    end as bank_order_date
  from territory.latest_transferegov_records as latest
  join payable_documents as document
    on document.document_id = latest.payload ->> 'id_documento_habil'
  where latest.record_type = 'transferegov_ordem_pagamento'
  group by document.proposal_id
)
select
  distribution.source_record_key as external_transfer_key,
  distribution.raw_record_id as origin_distribution_raw_record_id,
  proposal.raw_record_id as origin_proposal_raw_record_id,
  distribution.proposal_id,
  distribution.distribution_id,
  proposal.fiscal_year,
  distribution.amendment_number,
  distribution.author_name,
  lower(regexp_replace(distribution.author_name, '[[:space:]]+', ' ', 'g'))
    as author_key,
  case
    when lower(coalesce(distribution.amendment_kind, '')) like 'individual%'
      then 'person'
    when lower(coalesce(distribution.amendment_kind, '')) like 'comiss%'
      then 'commission'
    when lower(coalesce(distribution.amendment_kind, '')) like 'bancad%'
      then 'bench'
    when lower(coalesce(distribution.amendment_kind, '')) like 'coletiv%'
      then 'collective'
    else 'other'
  end as author_kind,
  distribution.distribution_kind,
  distribution.amendment_kind,
  proposal.beneficiary_name,
  proposal.object_description,
  proposal.proposal_status,
  proposal.proposal_amount,
  distribution.destination_amount,
  case
    when distribution_count.distribution_count = 1
    then commitment.committed_amount
  end as committed_amount,
  case
    when distribution_count.distribution_count = 1
    then payment.paid_amount
  end as paid_amount,
  case
    when distribution_count.distribution_count = 1
    then payment.bank_order_number
  end as bank_order_number,
  case
    when distribution_count.distribution_count = 1
    then payment.bank_order_date
  end as bank_order_date,
  case
    when distribution_count.distribution_count = 1
      then 'exact_single_distribution'
    else 'ambiguous_multiple_distributions'
  end as stage_attribution_status,
  greatest(proposal.collected_at, distribution.collected_at) as collected_at,
  artifact.source_url,
  artifact.sha256 as artifact_sha256
from distributions as distribution
join proposals as proposal on proposal.proposal_id = distribution.proposal_id
join distribution_counts as distribution_count
  on distribution_count.proposal_id = distribution.proposal_id
join raw.raw_artifacts as artifact
  on artifact.id = distribution.raw_artifact_id
left join commitment_totals as commitment
  on commitment.proposal_id = distribution.proposal_id
left join payment_totals as payment
  on payment.proposal_id = distribution.proposal_id
where distribution.author_name is not null
  and distribution.destination_amount is not null
  and distribution.destination_amount >= 0;

revoke all on territory.latest_transferegov_records from public;
revoke all on territory.parliamentary_transfers from public;
revoke all on territory.latest_transferegov_records from anon, authenticated;
revoke all on territory.parliamentary_transfers from anon, authenticated;

create function api.get_public_parliamentary_transfers(
  fiscal_year_filter smallint default null,
  author_kind_filter text default null,
  page_size integer default 100
)
returns table (
  external_transfer_key text,
  proposal_id text,
  distribution_id text,
  fiscal_year smallint,
  amendment_number text,
  author_name text,
  author_kind text,
  amendment_kind text,
  beneficiary_name text,
  object_description text,
  proposal_status text,
  proposal_amount numeric(20,2),
  destination_amount numeric(20,2),
  committed_amount numeric(20,2),
  paid_amount numeric(20,2),
  bank_order_number text,
  bank_order_date date,
  stage_attribution_status text,
  collected_at timestamptz,
  source_url text,
  artifact_sha256 text,
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
  if author_kind_filter is not null
    and author_kind_filter not in ('person', 'commission', 'bench', 'collective', 'other')
  then
    raise exception 'author_kind_filter nao permitido'
      using errcode = '22023';
  end if;

  return query
  select
    transfer.external_transfer_key,
    transfer.proposal_id,
    transfer.distribution_id,
    transfer.fiscal_year,
    transfer.amendment_number,
    transfer.author_name,
    transfer.author_kind,
    transfer.amendment_kind,
    transfer.beneficiary_name,
    transfer.object_description,
    transfer.proposal_status,
    transfer.proposal_amount,
    transfer.destination_amount,
    transfer.committed_amount,
    transfer.paid_amount,
    transfer.bank_order_number,
    transfer.bank_order_date,
    transfer.stage_attribution_status,
    transfer.collected_at,
    transfer.source_url,
    transfer.artifact_sha256,
    'parliamentary-transfers/1.0.0'::text
  from territory.parliamentary_transfers as transfer
  where (fiscal_year_filter is null or transfer.fiscal_year = fiscal_year_filter)
    and (author_kind_filter is null or transfer.author_kind = author_kind_filter)
  order by
    transfer.paid_amount desc nulls last,
    transfer.destination_amount desc,
    transfer.author_name,
    transfer.amendment_number
  limit page_size;
end;
$function$;

create function api.get_public_parliamentary_transfer_ranking(
  author_scope text default 'person',
  fiscal_year_filter smallint default null,
  page_size integer default 50
)
returns table (
  rank_position integer,
  author_key text,
  author_name text,
  author_kind text,
  amendment_count integer,
  destination_amount numeric(20,2),
  committed_amount numeric(20,2),
  paid_amount numeric(20,2),
  fully_paid_amendment_count integer,
  first_year smallint,
  last_year smallint,
  methodology_version text
)
language plpgsql
stable
security definer
set search_path = ''
as $function$
begin
  if author_scope not in ('person', 'collective') then
    raise exception 'author_scope deve ser person ou collective'
      using errcode = '22023';
  end if;
  if page_size < 1 or page_size > 200 then
    raise exception 'page_size deve estar entre 1 e 200'
      using errcode = '22023';
  end if;

  return query
  with grouped as (
    select
      transfer.author_key,
      coalesce(
        max(transfer.author_name) filter (
          where transfer.author_name = upper(transfer.author_name)
        ),
        max(transfer.author_name)
      ) as author_name,
      transfer.author_kind,
      count(*)::integer as amendment_count,
      sum(transfer.destination_amount)::numeric(20,2) as destination_amount,
      sum(transfer.committed_amount)::numeric(20,2) as committed_amount,
      sum(transfer.paid_amount)::numeric(20,2) as paid_amount,
      count(*) filter (
        where transfer.paid_amount is not null
          and transfer.destination_amount is not null
          and transfer.paid_amount >= transfer.destination_amount
      )::integer as fully_paid_amendment_count,
      min(transfer.fiscal_year)::smallint as first_year,
      max(transfer.fiscal_year)::smallint as last_year
    from territory.parliamentary_transfers as transfer
    where (fiscal_year_filter is null or transfer.fiscal_year = fiscal_year_filter)
      and (
        (author_scope = 'person' and transfer.author_kind = 'person')
        or
        (author_scope = 'collective' and transfer.author_kind in (
          'commission', 'bench', 'collective'
        ))
      )
    group by transfer.author_key, transfer.author_kind
  ), ranked as (
    select
      row_number() over (
        order by
          grouped.paid_amount desc nulls last,
          grouped.destination_amount desc,
          grouped.author_name
      )::integer as rank_position,
      grouped.*
    from grouped
  )
  select
    ranked.rank_position,
    ranked.author_key,
    ranked.author_name,
    ranked.author_kind,
    ranked.amendment_count,
    ranked.destination_amount,
    ranked.committed_amount,
    ranked.paid_amount,
    ranked.fully_paid_amendment_count,
    ranked.first_year,
    ranked.last_year,
    'parliamentary-transfer-ranking/1.0.0'::text
  from ranked
  order by ranked.rank_position
  limit page_size;
end;
$function$;

revoke all on function api.get_public_parliamentary_transfers(
  smallint, text, integer
) from public;
revoke all on function api.get_public_parliamentary_transfer_ranking(
  text, smallint, integer
) from public;

grant execute on function api.get_public_parliamentary_transfers(
  smallint, text, integer
) to anon, authenticated;
grant execute on function api.get_public_parliamentary_transfer_ranking(
  text, smallint, integer
) to anon, authenticated;

comment on view territory.parliamentary_transfers is
  'Projecao normalizada e rastreavel das emendas destinadas a Barreiras.';
comment on function api.get_public_parliamentary_transfers(
  smallint, text, integer
) is
  'Emendas e estagios financeiros oficiais, sem expor dados pessoais internos.';
comment on function api.get_public_parliamentary_transfer_ranking(
  text, smallint, integer
) is
  'Ranking objetivo por autoria; pessoas e autorias coletivas permanecem separadas.';
