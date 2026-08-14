begin;

-- Completa os dois vinculos federais ainda ausentes no ranking por
-- legislatura. A autoria publicada pelo Transferegov somente e associada
-- quando o perfil oficial da Camara ja possui crosswalk TSE aprovado.
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
      'claudio cajado',
      'CLAUDIO CAJADO',
      '74537',
      'https://www.camara.leg.br/deputados/74537',
      '50001621019',
      'O perfil oficial da Camara 74537 publica Claudio Cajado e o crosswalk '
        || 'TSE aprovado liga esse perfil a candidatura CLAUDIO CAJADO de '
        || '2022. O Transferegov publica CLAUDIO CAJADO como autor individual.'
    ),
    (
      'rogeria santos',
      'ROGERIA SANTOS',
      '220695',
      'https://www.camara.leg.br/deputados/220695',
      '50001619841',
      'O perfil oficial da Camara 220695 publica Rogeria Santos e o '
        || 'crosswalk TSE aprovado liga esse perfil a candidatura ROGERIA '
        || 'SANTOS de 2022. O Transferegov publica ROGERIA SANTOS como autora '
        || 'individual.'
    )
)
select
  'person',
  candidate.author_key,
  candidate.official_author_name,
  'federal',
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
  on crosswalk.source_kind = 'federal'
  and crosswalk.representative_external_id = candidate.representative_external_id
  and crosswalk.election_year = 2022
  and crosswalk.office = 'Deputado Federal'
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
