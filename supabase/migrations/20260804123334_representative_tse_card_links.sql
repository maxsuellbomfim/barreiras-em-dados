-- Vínculos eleitorais exibidos dentro dos cartões de representantes.
--
-- A tabela é um crosswalk explícito entre o identificador da fonte do perfil
-- (Câmara ou ALBA) e o identificador oficial da candidatura no TSE. Não há
-- associação por aproximação de nome em tempo de consulta: somente linhas
-- aprovadas e com coincidência exata de nome de urna, cargo, partido (quando a
-- fonte de perfil publica partido) e eleição entram na projeção pública.

create schema if not exists political;

create table if not exists political.representative_tse_crosswalk (
  source_kind text not null check (source_kind in ('federal', 'state')),
  representative_external_id text not null,
  election_year integer not null check (election_year between 1900 and 2100),
  office text not null,
  candidate_id text not null,
  review_status text not null default 'approved'
    check (review_status in ('approved', 'pending', 'rejected')),
  match_method text not null
    check (match_method = 'exact_ballot_name_party_office'),
  evidence_url text not null,
  evidence_note text not null,
  methodology_version text not null default 'representative-tse-crosswalk/1.0.0',
  created_at timestamptz not null default now(),
  primary key (source_kind, representative_external_id, election_year, office, candidate_id)
);

comment on table political.representative_tse_crosswalk is
  'Crosswalk revisado entre perfis oficiais de representantes e candidaturas do TSE; nomes não são usados como chave pública.';

create index if not exists representative_tse_crosswalk_candidate_idx
  on political.representative_tse_crosswalk (candidate_id, election_year, office)
  where review_status = 'approved';

insert into political.representative_tse_crosswalk
  (source_kind, representative_external_id, election_year, office, candidate_id,
   match_method, evidence_url, evidence_note)
values
  ('federal', '204560', 2022, 'Deputado Federal', '50001613575', 'exact_ballot_name_party_office', 'https://divulgacandcontas.tse.jus.br/', 'Nome de urna ADOLFO VIANA e partido PSDB coincidem com o perfil oficial da Câmara.'),
  ('federal', '160508', 2022, 'Deputado Federal', '50001605378', 'exact_ballot_name_party_office', 'https://divulgacandcontas.tse.jus.br/', 'Nome de urna AFONSO FLORENCE e partido PT coincidem com o perfil oficial da Câmara.'),
  ('federal', '74057', 2022, 'Deputado Federal', '50001605368', 'exact_ballot_name_party_office', 'https://divulgacandcontas.tse.jus.br/', 'Nome de urna ALICE PORTUGAL e partido PCdoB coincidem com o perfil oficial da Câmara.'),
  ('federal', '160553', 2022, 'Deputado Federal', '50001607229', 'exact_ballot_name_party_office', 'https://divulgacandcontas.tse.jus.br/', 'Nome de urna ANTONIO BRITO e partido PSD coincidem com o perfil oficial da Câmara.'),
  ('federal', '69871', 2022, 'Deputado Federal', '50001605351', 'exact_ballot_name_party_office', 'https://divulgacandcontas.tse.jus.br/', 'Nome de urna BACELAR e partido PV coincidem com o perfil oficial da Câmara.'),
  ('federal', '220690', 2022, 'Deputado Federal', '50001609344', 'exact_ballot_name_party_office', 'https://divulgacandcontas.tse.jus.br/', 'Nome de urna CAPITÃO ALDEN e partido PL coincidem com o perfil oficial da Câmara.'),
  ('federal', '205476', 2022, 'Deputado Federal', '50001607219', 'exact_ballot_name_party_office', 'https://divulgacandcontas.tse.jus.br/', 'Nome de urna CHARLES FERNANDES e partido PSD coincidem com o perfil oficial da Câmara.'),
  ('federal', '74537', 2022, 'Deputado Federal', '50001621019', 'exact_ballot_name_party_office', 'https://divulgacandcontas.tse.jus.br/', 'Nome de urna CLAUDIO CAJADO e partido PP coincidem com o perfil oficial da Câmara.'),
  ('federal', '220691', 2022, 'Deputado Federal', '50001607221', 'exact_ballot_name_party_office', 'https://divulgacandcontas.tse.jus.br/', 'Nome de urna DIEGO CORONEL e partido REPUBLICANOS coincidem com o perfil oficial da Câmara.'),
  ('federal', '178854', 2022, 'Deputado Federal', '50001634583', 'exact_ballot_name_party_office', 'https://divulgacandcontas.tse.jus.br/', 'Nome de urna ELMAR NASCIMENTO e partido UNIÃO coincidem com o perfil oficial da Câmara.'),
  ('federal', '220708', 2022, 'Deputado Federal', '50001607226', 'exact_ballot_name_party_office', 'https://divulgacandcontas.tse.jus.br/', 'Nome de urna GABRIEL NUNES e partido PSD coincidem com o perfil oficial da Câmara.'),
  ('federal', '220696', 2022, 'Deputado Federal', '50001605353', 'exact_ballot_name_party_office', 'https://divulgacandcontas.tse.jus.br/', 'Nome de urna IVONEIDE CAETANO e partido PT coincidem com o perfil oficial da Câmara.'),
  ('federal', '141458', 2022, 'Deputado Federal', '50001609371', 'exact_ballot_name_party_office', 'https://divulgacandcontas.tse.jus.br/', 'Nome de urna JOÃO CARLOS BACELAR e partido PL coincidem com o perfil oficial da Câmara.'),
  ('federal', '235800', 2022, 'Deputado Federal', '50001621015', 'exact_ballot_name_party_office', 'https://divulgacandcontas.tse.jus.br/', 'Nome de urna JORGE ARAÚJO e partido PP coincidem com o perfil oficial da Câmara.'),
  ('federal', '178857', 2022, 'Deputado Federal', '50001605359', 'exact_ballot_name_party_office', 'https://divulgacandcontas.tse.jus.br/', 'Nome de urna JORGE SOLLA e partido PT coincidem com o perfil oficial da Câmara.'),
  ('federal', '74554', 2022, 'Deputado Federal', '50001634584', 'exact_ballot_name_party_office', 'https://divulgacandcontas.tse.jus.br/', 'Nome de urna JOSÉ ROCHA e partido UNIÃO coincidem com o perfil oficial da Câmara.'),
  ('federal', '209189', 2022, 'Deputado Federal', '50001605369', 'exact_ballot_name_party_office', 'https://divulgacandcontas.tse.jus.br/', 'Nome de urna JOSEILDO RAMOS e partido PT coincidem com o perfil oficial da Câmara.'),
  ('federal', '139285', 2022, 'Deputado Federal', '50001606032', 'exact_ballot_name_party_office', 'https://divulgacandcontas.tse.jus.br/', 'Nome de urna LÍDICE DA MATA e partido PSB coincidem com o perfil oficial da Câmara.'),
  ('federal', '204558', 2022, 'Deputado Federal', '50001619849', 'exact_ballot_name_party_office', 'https://divulgacandcontas.tse.jus.br/', 'Nome de urna MARCELO NILO e partido REPUBLICANOS coincidem com o perfil oficial da Câmara.'),
  ('federal', '220703', 2022, 'Deputado Federal', '50001621029', 'exact_ballot_name_party_office', 'https://divulgacandcontas.tse.jus.br/', 'Nome de urna NETO CARLETTO e partido AVANTE coincidem com o perfil oficial da Câmara.'),
  ('federal', '204553', 2022, 'Deputado Federal', '50001602958', 'exact_ballot_name_party_office', 'https://divulgacandcontas.tse.jus.br/', 'Nome de urna PASTOR SARGENTO ISIDÓRIO e partido AVANTE coincidem com o perfil oficial da Câmara.'),
  ('federal', '178860', 2022, 'Deputado Federal', '50001634593', 'exact_ballot_name_party_office', 'https://divulgacandcontas.tse.jus.br/', 'Nome de urna PAULO AZI e partido UNIÃO coincidem com o perfil oficial da Câmara.'),
  ('federal', '74574', 2022, 'Deputado Federal', '50001607232', 'exact_ballot_name_party_office', 'https://divulgacandcontas.tse.jus.br/', 'Nome de urna PAULO MAGALHÃES e partido PSD coincidem com o perfil oficial da Câmara.'),
  ('federal', '204567', 2022, 'Deputado Federal', '50001615380', 'exact_ballot_name_party_office', 'https://divulgacandcontas.tse.jus.br/', 'Nome de urna RAIMUNDO COSTA e partido PSD coincidem com o perfil oficial da Câmara.'),
  ('federal', '220694', 2022, 'Deputado Federal', '50001614047', 'exact_ballot_name_party_office', 'https://divulgacandcontas.tse.jus.br/', 'Nome de urna RICARDO MAIA e partido MDB coincidem com o perfil oficial da Câmara.'),
  ('federal', '220693', 2022, 'Deputado Federal', '50001609349', 'exact_ballot_name_party_office', 'https://divulgacandcontas.tse.jus.br/', 'Nome de urna ROBERTA ROMA e partido PL coincidem com o perfil oficial da Câmara.'),
  ('federal', '73808', 2022, 'Deputado Federal', '50001607223', 'exact_ballot_name_party_office', 'https://divulgacandcontas.tse.jus.br/', 'Nome de urna SÉRGIO BRITO e partido PSD coincidem com o perfil oficial da Câmara.'),
  ('federal', '160610', 2022, 'Deputado Federal', '50001605371', 'exact_ballot_name_party_office', 'https://divulgacandcontas.tse.jus.br/', 'Nome de urna VALMIR ASSUNÇÃO e partido PT coincidem com o perfil oficial da Câmara.'),
  ('federal', '160569', 2022, 'Deputado Federal', '50001605361', 'exact_ballot_name_party_office', 'https://divulgacandcontas.tse.jus.br/', 'Nome de urna WALDENOR PEREIRA e partido PT coincidem com o perfil oficial da Câmara.'),
  ('federal', '204559', 2022, 'Deputado Federal', '50001605365', 'exact_ballot_name_party_office', 'https://divulgacandcontas.tse.jus.br/', 'Nome de urna ZÉ NETO e partido PT coincidem com o perfil oficial da Câmara.'),
  ('state', '910629', 2022, 'Deputado Estadual', '50001607292', 'exact_ballot_name_party_office', 'https://divulgacandcontas.tse.jus.br/', 'Nome de urna ADOLFO MENEZES e cargo coincidem com o perfil oficial da ALBA.'),
  ('state', '921263', 2022, 'Deputado Estadual', '50001607306', 'exact_ballot_name_party_office', 'https://divulgacandcontas.tse.jus.br/', 'Nome de urna ALEX DA PIATÃ e cargo coincidem com o perfil oficial da ALBA.'),
  ('state', '929445', 2022, 'Deputado Estadual', '50001605968', 'exact_ballot_name_party_office', 'https://divulgacandcontas.tse.jus.br/', 'Nome de urna ANGELO ALMEIDA e cargo coincidem com o perfil oficial da ALBA.'),
  ('state', '932104', 2022, 'Deputado Estadual', '50001607294', 'exact_ballot_name_party_office', 'https://divulgacandcontas.tse.jus.br/', 'Nome de urna ANGELO CORONEL FILHO e cargo coincidem com o perfil oficial da ALBA.'),
  ('state', '932169', 2022, 'Deputado Estadual', '50001610379', 'exact_ballot_name_party_office', 'https://divulgacandcontas.tse.jus.br/', 'Nome de urna BINHO GALINHA e cargo coincidem com o perfil oficial da ALBA.'),
  ('state', '921283', 2022, 'Deputado Estadual', '50001606413', 'exact_ballot_name_party_office', 'https://divulgacandcontas.tse.jus.br/', 'Nome de urna BOBÔ e cargo coincidem com o perfil oficial da ALBA.'),
  ('state', '932181', 2022, 'Deputado Estadual', '50001607305', 'exact_ballot_name_party_office', 'https://divulgacandcontas.tse.jus.br/', 'Nome de urna CAFU BARRETO e cargo coincidem com o perfil oficial da ALBA.'),
  ('state', '932099', 2022, 'Deputado Estadual', '50001609451', 'exact_ballot_name_party_office', 'https://divulgacandcontas.tse.jus.br/', 'Nome de urna DR. DIEGO CASTRO e cargo coincidem com o perfil oficial da ALBA.'),
  ('state', '926918', 2022, 'Deputado Estadual', '50001607296', 'exact_ballot_name_party_office', 'https://divulgacandcontas.tse.jus.br/', 'Nome de urna EDUARDO ALENCAR e cargo coincidem com o perfil oficial da ALBA.'),
  ('state', '921268', 2022, 'Deputado Estadual', '50001647028', 'exact_ballot_name_party_office', 'https://divulgacandcontas.tse.jus.br/', 'Nome de urna EDUARDO SALLES e cargo coincidem com o perfil oficial da ALBA.'),
  ('state', '910635', 2022, 'Deputado Estadual', '50001606438', 'exact_ballot_name_party_office', 'https://divulgacandcontas.tse.jus.br/', 'Nome de urna EUCLIDES FERNANDES e cargo coincidem com o perfil oficial da ALBA.'),
  ('state', '932102', 2022, 'Deputado Estadual', '50001647074', 'exact_ballot_name_party_office', 'https://divulgacandcontas.tse.jus.br/', 'Nome de urna FELIPE DUARTE e cargo coincidem com o perfil oficial da ALBA.'),
  ('state', '926902', 2022, 'Deputado Estadual', '50001600622', 'exact_ballot_name_party_office', 'https://divulgacandcontas.tse.jus.br/', 'Nome de urna HILTON COELHO e cargo coincidem com o perfil oficial da ALBA.'),
  ('state', '915867', 2022, 'Deputado Estadual', '50001607307', 'exact_ballot_name_party_office', 'https://divulgacandcontas.tse.jus.br/', 'Nome de urna IVANA BASTOS e cargo coincidem com o perfil oficial da ALBA.'),
  ('state', '915859', 2022, 'Deputado Estadual', '50001619281', 'exact_ballot_name_party_office', 'https://divulgacandcontas.tse.jus.br/', 'Nome de urna JOSE DE ARIMATEIA e cargo coincidem com o perfil oficial da ALBA.'),
  ('state', '926897', 2022, 'Deputado Estadual', '50001619298', 'exact_ballot_name_party_office', 'https://divulgacandcontas.tse.jus.br/', 'Nome de urna JURAILTON SANTOS e cargo coincidem com o perfil oficial da ALBA.'),
  ('state', '935220', 2022, 'Deputado Estadual', '50001607303', 'exact_ballot_name_party_office', 'https://divulgacandcontas.tse.jus.br/', 'Nome de urna JUSMARI OLIVEIRA e cargo coincidem com o perfil oficial da ALBA.'),
  ('state', '926922', 2022, 'Deputado Estadual', '50001604617', 'exact_ballot_name_party_office', 'https://divulgacandcontas.tse.jus.br/', 'Nome de urna LAERTE DO VANDO e cargo coincidem com o perfil oficial da ALBA.'),
  ('state', '932100', 2022, 'Deputado Estadual', '50001609456', 'exact_ballot_name_party_office', 'https://divulgacandcontas.tse.jus.br/', 'Nome de urna LEANDRO DE JESUS e cargo coincidem com o perfil oficial da ALBA.'),
  ('state', '936939', 2022, 'Deputado Estadual', '50001648289', 'exact_ballot_name_party_office', 'https://divulgacandcontas.tse.jus.br/', 'Nome de urna LUCIANO RIBEIRO e cargo coincidem com o perfil oficial da ALBA.'),
  ('state', '932107', 2022, 'Deputado Estadual', '50001606389', 'exact_ballot_name_party_office', 'https://divulgacandcontas.tse.jus.br/', 'Nome de urna LUDMILLA FISCINA e cargo coincidem com o perfil oficial da ALBA.'),
  ('state', '932118', 2022, 'Deputado Estadual', '50001648303', 'exact_ballot_name_party_office', 'https://divulgacandcontas.tse.jus.br/', 'Nome de urna MANUEL ROCHA e cargo coincidem com o perfil oficial da ALBA.'),
  ('state', '926899', 2022, 'Deputado Estadual', '50001648309', 'exact_ballot_name_party_office', 'https://divulgacandcontas.tse.jus.br/', 'Nome de urna MARCELINHO VEIGA e cargo coincidem com o perfil oficial da ALBA.'),
  ('state', '932147', 2022, 'Deputado Estadual', '50001648293', 'exact_ballot_name_party_office', 'https://divulgacandcontas.tse.jus.br/', 'Nome de urna MARCINHO OLIVEIRA e cargo coincidem com o perfil oficial da ALBA.'),
  ('state', '915885', 2022, 'Deputado Estadual', '50001606396', 'exact_ballot_name_party_office', 'https://divulgacandcontas.tse.jus.br/', 'Nome de urna MARIA DEL CARMEN e cargo coincidem com o perfil oficial da ALBA.'),
  ('state', '919329', 2022, 'Deputado Estadual', '50001606436', 'exact_ballot_name_party_office', 'https://divulgacandcontas.tse.jus.br/', 'Nome de urna MARQUINHO VIANA e cargo coincidem com o perfil oficial da ALBA.'),
  ('state', '903706', 2022, 'Deputado Estadual', '50001647023', 'exact_ballot_name_party_office', 'https://divulgacandcontas.tse.jus.br/', 'Nome de urna NELSON LEAL e cargo coincidem com o perfil oficial da ALBA.'),
  ('state', '932367', 2022, 'Deputado Estadual', '50001606395', 'exact_ballot_name_party_office', 'https://divulgacandcontas.tse.jus.br/', 'Nome de urna NEUSA CADORE e cargo coincidem com o perfil oficial da ALBA.'),
  ('state', '926913', 2022, 'Deputado Estadual', '50001647048', 'exact_ballot_name_party_office', 'https://divulgacandcontas.tse.jus.br/', 'Nome de urna NILTINHO e cargo coincidem com o perfil oficial da ALBA.'),
  ('state', '926908', 2022, 'Deputado Estadual', '50001606433', 'exact_ballot_name_party_office', 'https://divulgacandcontas.tse.jus.br/', 'Nome de urna OLIVIA SANTANA e cargo coincidem com o perfil oficial da ALBA.'),
  ('state', '932146', 2022, 'Deputado Estadual', '50001620017', 'exact_ballot_name_party_office', 'https://divulgacandcontas.tse.jus.br/', 'Nome de urna PANCADINHA e cargo coincidem com o perfil oficial da ALBA.'),
  ('state', '932113', 2022, 'Deputado Estadual', '50001603011', 'exact_ballot_name_party_office', 'https://divulgacandcontas.tse.jus.br/', 'Nome de urna PATRICK LOPES e cargo coincidem com o perfil oficial da ALBA.'),
  ('state', '935102', 2022, 'Deputado Estadual', '50001613898', 'exact_ballot_name_party_office', 'https://divulgacandcontas.tse.jus.br/', 'Nome de urna PAULO CÂMARA e cargo coincidem com o perfil oficial da ALBA.'),
  ('state', '915876', 2022, 'Deputado Estadual', '50001648327', 'exact_ballot_name_party_office', 'https://divulgacandcontas.tse.jus.br/', 'Nome de urna PEDRO TAVARES e cargo coincidem com o perfil oficial da ALBA.'),
  ('state', '932119', 2022, 'Deputado Estadual', '50001609434', 'exact_ballot_name_party_office', 'https://divulgacandcontas.tse.jus.br/', 'Nome de urna RAIMUNDINHO DA JR e cargo coincidem com o perfil oficial da ALBA.'),
  ('state', '932108', 2022, 'Deputado Estadual', '50001607297', 'exact_ballot_name_party_office', 'https://divulgacandcontas.tse.jus.br/', 'Nome de urna RICARDO RODRIGUES e cargo coincidem com o perfil oficial da ALBA.'),
  ('state', '907278', 2022, 'Deputado Estadual', '50001606388', 'exact_ballot_name_party_office', 'https://divulgacandcontas.tse.jus.br/', 'Nome de urna ROBERTO CARLOS e cargo coincidem com o perfil oficial da ALBA.'),
  ('state', '921265', 2022, 'Deputado Estadual', '50001648336', 'exact_ballot_name_party_office', 'https://divulgacandcontas.tse.jus.br/', 'Nome de urna ROBINHO e cargo coincidem com o perfil oficial da ALBA.'),
  ('state', '932115', 2022, 'Deputado Estadual', '50001614699', 'exact_ballot_name_party_office', 'https://divulgacandcontas.tse.jus.br/', 'Nome de urna ROGÉRIO ANDRADE e cargo coincidem com o perfil oficial da ALBA.'),
  ('state', '923801', 2022, 'Deputado Estadual', '50001619261', 'exact_ballot_name_party_office', 'https://divulgacandcontas.tse.jus.br/', 'Nome de urna SAMUEL JUNIOR e cargo coincidem com o perfil oficial da ALBA.'),
  ('state', '907264', 2022, 'Deputado Estadual', '50001648297', 'exact_ballot_name_party_office', 'https://divulgacandcontas.tse.jus.br/', 'Nome de urna SANDRO RÉGIS e cargo coincidem com o perfil oficial da ALBA.'),
  ('state', '932117', 2022, 'Deputado Estadual', '50001605984', 'exact_ballot_name_party_office', 'https://divulgacandcontas.tse.jus.br/', 'Nome de urna SOANE GALVÃO e cargo coincidem com o perfil oficial da ALBA.'),
  ('state', '927093', 2022, 'Deputado Estadual', '50001613902', 'exact_ballot_name_party_office', 'https://divulgacandcontas.tse.jus.br/', 'Nome de urna TIAGO CORREIA e cargo coincidem com o perfil oficial da ALBA.'),
  ('state', '932116', 2022, 'Deputado Estadual', '50001609449', 'exact_ballot_name_party_office', 'https://divulgacandcontas.tse.jus.br/', 'Nome de urna VITOR AZEVEDO e cargo coincidem com o perfil oficial da ALBA.'),
  ('state', '921274', 2022, 'Deputado Estadual', '50001606406', 'exact_ballot_name_party_office', 'https://divulgacandcontas.tse.jus.br/', 'Nome de urna VITOR BONFIM e cargo coincidem com o perfil oficial da ALBA.'),
  ('state', '915869', 2022, 'Deputado Estadual', '50001606439', 'exact_ballot_name_party_office', 'https://divulgacandcontas.tse.jus.br/', 'Nome de urna ZÉ RAIMUNDO FONTES e cargo coincidem com o perfil oficial da ALBA.'),
  ('state', '921266', 2022, 'Deputado Estadual', '50001606432', 'exact_ballot_name_party_office', 'https://divulgacandcontas.tse.jus.br/', 'Nome de urna ZÓ e cargo coincidem com o perfil oficial da ALBA.')
on conflict (source_kind, representative_external_id, election_year, office, candidate_id)
do update set
  review_status = excluded.review_status,
  match_method = excluded.match_method,
  evidence_url = excluded.evidence_url,
  evidence_note = excluded.evidence_note,
  methodology_version = excluded.methodology_version;

create or replace function api.get_representative_tse_votes(
  source_kind_filter text default null,
  representative_external_id_filter text default null
)
returns table (
  source_kind text,
  representative_external_id text,
  election_year integer,
  turn_number integer,
  office text,
  candidate_id text,
  candidate_number text,
  display_name text,
  ballot_name text,
  party text,
  situation text,
  votes_in_barreiras integer,
  zones integer,
  collected_at timestamptz,
  evidence_url text,
  match_method text,
  methodology_version text
)
language plpgsql
stable
security definer
set search_path = ''
as $function$
declare
  normalized_kind text := nullif(btrim(source_kind_filter), '');
  normalized_external_id text := nullif(btrim(representative_external_id_filter), '');
begin
  if normalized_kind is not null and normalized_kind not in ('federal', 'state') then
    raise exception 'source_kind_filter inválido'
      using errcode = '22023';
  end if;

  return query
  select
    crosswalk.source_kind,
    crosswalk.representative_external_id,
    (record.payload ->> 'ano')::integer,
    (record.payload ->> 'turno')::integer,
    btrim(record.payload ->> 'cargo'),
    record.payload ->> 'sq_candidato',
    record.payload ->> 'numero',
    btrim(record.payload ->> 'nome'),
    btrim(record.payload ->> 'nome_urna'),
    btrim(record.payload ->> 'partido'),
    btrim(record.payload ->> 'situacao'),
    (record.payload ->> 'votos_em_barreiras')::integer,
    (record.payload ->> 'zonas')::integer,
    record.collected_at,
    crosswalk.evidence_url,
    crosswalk.match_method,
    'representative-tse-crosswalk/1.0.0'::text
  from political.representative_tse_crosswalk as crosswalk
  join raw.raw_records as record
    on record.record_type = 'tse_votacao_barreiras'
    and record.payload ->> 'sq_candidato' = crosswalk.candidate_id
    and record.payload ->> 'ano' = crosswalk.election_year::text
    and btrim(record.payload ->> 'cargo') = crosswalk.office
  where crosswalk.review_status = 'approved'
    and (normalized_kind is null or crosswalk.source_kind = normalized_kind)
    and (
      normalized_external_id is null
      or crosswalk.representative_external_id = normalized_external_id
    )
    and record.payload ->> 'turno' ~ '^[0-9]+$'
    and record.payload ->> 'votos_em_barreiras' ~ '^[0-9]+$'
    and record.payload ->> 'zonas' ~ '^[0-9]+$'
  order by crosswalk.source_kind, crosswalk.representative_external_id,
    (record.payload ->> 'ano')::integer desc,
    (record.payload ->> 'turno')::integer;
end;
$function$;

revoke all on function api.get_representative_tse_votes(text, text) from public;
grant execute on function api.get_representative_tse_votes(text, text)
  to anon, authenticated;

comment on function api.get_representative_tse_votes(text, text) is
  'Votação municipal do TSE ligada a cartões de representantes somente por crosswalk aprovado e identificadores oficiais.';
