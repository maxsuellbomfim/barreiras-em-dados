begin;

-- A serie documental da CGU publica um codigo de quatro algarismos para cada
-- autoria. A ligacao abaixo somente e criada quando o perfil institucional ja
-- possui crosswalk TSE aprovado para a mesma eleicao e cargo. Nenhuma
-- aproximacao nominal participa da consulta publica.
insert into political.parliamentary_author_code_crosswalk (
  source_system,
  source_author_code,
  source_author_name,
  official_author_name,
  author_key,
  representative_source_kind,
  representative_external_id,
  representative_profile_url,
  source_author_evidence_url,
  identity_evidence_url,
  identity_evidence_note,
  valid_from_year,
  valid_to_year,
  review_status,
  methodology_version,
  approved_at
)
with candidates (
  source_author_code,
  source_author_name,
  official_author_name,
  author_key,
  representative_external_id,
  representative_profile_url,
  source_author_evidence_url,
  candidate_id,
  evidence_note
) as (
  values
    (
      '4319',
      'CAPITAO ALDEN',
      'Capitão Alden',
      'capitao alden',
      '220690',
      'https://www.camara.leg.br/deputados/220690',
      'https://portaldatransparencia.gov.br/emendas/detalhe?codigoEmenda=202443190015',
      '50001609344',
      'O Portal da Transparencia publica CAPITAO ALDEN como autor da emenda '
        || '202443190015, cujo bloco de autoria e 4319. O perfil oficial '
        || '220690 da Camara registra Capitao Alden como deputado federal '
        || 'titular em 2023-2027, e o crosswalk TSE aprovado liga esse perfil '
        || 'a candidatura federal 50001609344 de 2022.'
    ),
    (
      '4460',
      'RICARDO MAIA',
      'Ricardo Maia',
      'ricardo maia',
      '220694',
      'https://www.camara.leg.br/deputados/220694',
      'https://portaldatransparencia.gov.br/emendas/detalhe?codigoEmenda=202544600002',
      '50001614047',
      'O Portal da Transparencia publica RICARDO MAIA como autor da emenda '
        || '202544600002, cujo bloco de autoria e 4460. O perfil oficial '
        || '220694 da Camara registra Ricardo Maia como deputado federal '
        || 'titular em 2023-2027, e o crosswalk TSE aprovado liga esse perfil '
        || 'a candidatura federal 50001614047 de 2022.'
    )
)
select
  'federal_amendment_author_code',
  candidate.source_author_code,
  candidate.source_author_name,
  candidate.official_author_name,
  candidate.author_key,
  crosswalk.source_kind,
  crosswalk.representative_external_id,
  candidate.representative_profile_url,
  candidate.source_author_evidence_url,
  candidate.representative_profile_url,
  candidate.evidence_note,
  2023,
  2027,
  'approved',
  'parliamentary-author-code-crosswalk/1.1.0',
  statement_timestamp()
from candidates as candidate
join political.representative_tse_crosswalk as crosswalk
  on crosswalk.source_kind = 'federal'
  and crosswalk.representative_external_id
    = candidate.representative_external_id
  and crosswalk.election_year = 2022
  and crosswalk.office = 'Deputado Federal'
  and crosswalk.candidate_id = candidate.candidate_id
  and crosswalk.review_status = 'approved'
on conflict (
  source_system,
  source_author_code,
  valid_from_year
) do nothing;

do $$
declare
  verified_rows integer;
begin
  select count(*)::integer
  into verified_rows
  from political.parliamentary_author_code_crosswalk as crosswalk
  where crosswalk.source_system = 'federal_amendment_author_code'
    and crosswalk.valid_from_year = 2023
    and crosswalk.valid_to_year = 2027
    and crosswalk.review_status = 'approved'
    and crosswalk.methodology_version
      = 'parliamentary-author-code-crosswalk/1.1.0'
    and (
      (
        crosswalk.source_author_code = '4319'
        and crosswalk.source_author_name = 'CAPITAO ALDEN'
        and crosswalk.author_key = 'capitao alden'
        and crosswalk.representative_source_kind = 'federal'
        and crosswalk.representative_external_id = '220690'
      )
      or (
        crosswalk.source_author_code = '4460'
        and crosswalk.source_author_name = 'RICARDO MAIA'
        and crosswalk.author_key = 'ricardo maia'
        and crosswalk.representative_source_kind = 'federal'
        and crosswalk.representative_external_id = '220694'
      )
    );

  if verified_rows <> 2 then
    raise exception
      'crosswalk documental atual incompleto ou divergente: % de 2 linhas',
      verified_rows;
  end if;
end;
$$;

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
  'administrator',
  'migration:link-current-cgu-document-authors',
  'identity.cgu_document_authors_linked',
  'political.parliamentary_author_code_crosswalk',
  gen_random_uuid(),
  jsonb_build_object(
    'methodology_version', 'parliamentary-author-code-crosswalk/1.1.0',
    'source_author_codes', jsonb_build_array('4319', '4460'),
    'representative_external_ids', jsonb_build_array('220690', '220694'),
    'valid_from_year', 2023,
    'valid_to_year', 2027,
    'verified_rows', 2
  ),
  jsonb_build_object(
    'match_basis', 'official_author_code_profile_and_tse_crosswalk',
    'fuzzy_name_matching', false,
    'personal_identifiers_exposed', false,
    'cross_source_amounts_summed', false
  )
);

notify pgrst, 'reload schema';

commit;
