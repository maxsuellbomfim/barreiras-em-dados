begin;

-- Marcone Amaral aparece na LOA de 2026 com o codigo de autor 500144.
-- O perfil oficial da ALBA registra o mandato temporario na 20a legislatura,
-- e o recorte municipal do TSE preservado pelo projeto identifica a
-- candidatura estadual de 2022 pelo SQ_CANDIDATO 50001607304.
insert into political.representative_tse_crosswalk (
  source_kind,
  representative_external_id,
  election_year,
  office,
  candidate_id,
  match_method,
  evidence_url,
  evidence_note,
  vote_scope,
  scope_note,
  methodology_version,
  review_status
)
values (
  'state',
  '935240',
  2022,
  'Deputado Estadual',
  '50001607304',
  'reviewed_official_alias',
  'https://divulgacandcontas.tse.jus.br/',
  'O perfil oficial da ALBA 935240 publica Marcone Amaral Costa Junior e o '
    || 'registro eleitoral de 2022 publica MARCONE AMARAL, numero 55123, '
    || 'partido PSD e situacao de suplente.',
  'person',
  'Votos da candidatura individual no recorte municipal do TSE.',
  'representative-tse-crosswalk/1.1.0',
  'approved'
)
on conflict (
  source_kind,
  representative_external_id,
  election_year,
  office,
  candidate_id
) do update set
  match_method = excluded.match_method,
  evidence_url = excluded.evidence_url,
  evidence_note = excluded.evidence_note,
  vote_scope = excluded.vote_scope,
  scope_note = excluded.scope_note,
  methodology_version = excluded.methodology_version,
  review_status = excluded.review_status;

insert into political.parliamentary_transfer_author_crosswalk (
  author_kind,
  author_key,
  official_author_name,
  representative_source_kind,
  representative_external_id,
  representative_profile_url,
  identity_evidence_url,
  identity_evidence_note,
  match_method,
  review_status,
  methodology_version,
  approved_at
)
with candidates (
  author_key,
  official_author_name,
  representative_external_id,
  representative_profile_url,
  candidate_id,
  evidence_note
) as (
  values
    (
      'hassan',
      'Hassan',
      '932105',
      'https://www.al.ba.gov.br/deputados/deputado-legislatura-atual/932105',
      '50001647026',
      'O perfil oficial da ALBA 932105 publica Hassan e o crosswalk TSE '
        || 'aprovado liga esse perfil a candidatura HASSAN DE ZE COCA de 2022.'
    ),
    (
      'luciano simoes filho',
      'Luciano Simões Filho',
      '921278',
      'https://www.al.ba.gov.br/deputados/ex-deputado-estadual/921278',
      '50001648313',
      'O perfil oficial da ALBA 921278 publica Luciano Simoes Filho e o '
        || 'crosswalk TSE aprovado liga esse perfil a candidatura estadual '
        || 'de 2022. O caminho historico da URL nao altera a autoria da LOA.'
    ),
    (
      'marcone amaral',
      'Marcone Amaral',
      '935240',
      'https://www.al.ba.gov.br/deputados/deputado-estadual/935240',
      '50001607304',
      'O perfil oficial da ALBA 935240 publica Marcone Amaral Costa Junior, '
        || 'suplente que exerceu mandato entre 29/01/2025 e 06/04/2026, e o '
        || 'crosswalk TSE aprovado liga o perfil a candidatura MARCONE AMARAL '
        || 'de 2022. O vinculo nao transforma o mandato temporario em atual.'
    )
)
select
  'person',
  candidate.author_key,
  candidate.official_author_name,
  'state',
  candidate.representative_external_id,
  candidate.representative_profile_url,
  crosswalk.evidence_url,
  candidate.evidence_note,
  'approved_official_profile_and_tse_crosswalk',
  'approved',
  'parliamentary-transfer-author-crosswalk/1.2.0',
  statement_timestamp()
from candidates as candidate
join political.representative_tse_crosswalk as crosswalk
  on crosswalk.source_kind = 'state'
  and crosswalk.representative_external_id = candidate.representative_external_id
  and crosswalk.election_year = 2022
  and crosswalk.office = 'Deputado Estadual'
  and crosswalk.candidate_id = candidate.candidate_id
  and crosswalk.review_status = 'approved'
on conflict (author_kind, author_key) do update set
  official_author_name = excluded.official_author_name,
  representative_source_kind = excluded.representative_source_kind,
  representative_external_id = excluded.representative_external_id,
  representative_profile_url = excluded.representative_profile_url,
  identity_evidence_url = excluded.identity_evidence_url,
  identity_evidence_note = excluded.identity_evidence_note,
  match_method = excluded.match_method,
  review_status = excluded.review_status,
  methodology_version = excluded.methodology_version,
  approved_at = excluded.approved_at,
  updated_at = statement_timestamp();

notify pgrst, 'reload schema';

commit;
