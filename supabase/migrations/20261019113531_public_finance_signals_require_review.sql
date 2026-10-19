begin;

-- ADR 0099: a projeção pública de sinais só mostra sinal com revisão
-- (automatizada ou humana) aprovada; vale a decisão mais recente.
create or replace function api.get_public_finance_signals(
  page_size integer default 50
)
returns table (
  finding_id uuid,
  rule_slug text,
  rule_name text,
  severity text,
  target_type text,
  target_id uuid,
  fiscal_year smallint,
  period_start date,
  period_end date,
  public_body_name text,
  public_explanation text,
  deterministic_output jsonb,
  source_url text,
  artifact_sha256 text,
  created_at timestamptz
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
  with exact_lineage as materialized (
    select lineage.origin_raw_record_id, lineage.document_artifact_id
    from finance.get_exact_document_lineage_pairs() as lineage
  )
  select
    finding.id,
    rule.slug,
    rule.name,
    rule.severity,
    finding.target_type,
    finding.target_id,
    report.fiscal_year,
    report.period_start,
    report.period_end,
    body.name,
    finding.public_explanation,
    finding.deterministic_output,
    evidence.source_url,
    artifact.sha256,
    finding.created_at
  from analysis.anomaly_findings as finding
  join analysis.anomaly_rules as rule on rule.id = finding.anomaly_rule_id
  join finance.expense_reports as report
    on finding.target_type = 'finance.expense_report'
   and report.id = finding.target_id
  join exact_lineage as lineage
    on lineage.origin_raw_record_id = report.origin_raw_record_id
   and lineage.document_artifact_id = report.source_document_artifact_id
  join org.public_bodies as body on body.id = report.public_body_id
  left join lateral (
    select item.source_url
    from evidence.evidence_items as item
    where item.target_type = 'analysis.anomaly_finding'
      and item.target_id = finding.id
      and item.is_primary
    order by item.created_at desc
    limit 1
  ) as evidence on true
  -- ADR 0099: só sinais com revisão (automatizada ou humana) aprovada; vale
  -- a decisão mais recente.
  join lateral (
    select review.decision
    from editorial.editorial_reviews as review
    where review.target_type = 'analysis.anomaly_finding'
      and review.target_id = finding.id
    order by review.reviewed_at desc, review.created_at desc, review.id desc
    limit 1
  ) as latest_review on latest_review.decision = 'approved'
  join raw.raw_records as origin on origin.id = finding.origin_raw_record_id
  join raw.raw_artifacts as artifact on artifact.id = origin.raw_artifact_id
  where finding.status in ('triage', 'needs_context', 'confirmed_as_signal')
    and finding.supersedes_id is null
    and finding.origin_raw_record_id = report.origin_raw_record_id
  order by report.period_end desc, finding.created_at desc, finding.id desc
  limit page_size;
end;
$function$;

notify pgrst, 'reload schema';

commit;
