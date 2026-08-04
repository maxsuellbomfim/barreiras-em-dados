-- Completa o crosswalk eleitoral com os vereadores de Barreiras e a chapa
-- majoritária de 2024. A votação do vice não é uma votação individual no TSE:
-- o cartão informa explicitamente que o número é da chapa.

alter table political.representative_tse_crosswalk
  drop constraint if exists representative_tse_crosswalk_source_kind_check;

alter table political.representative_tse_crosswalk
  add constraint representative_tse_crosswalk_source_kind_check
  check (source_kind in ('federal', 'state', 'municipal', 'executive'));

alter table political.representative_tse_crosswalk
  add column if not exists vote_scope text not null default 'person'
    check (vote_scope in ('person', 'ticket'));

alter table political.representative_tse_crosswalk
  add column if not exists scope_note text not null default 'Votos da candidatura no recorte municipal do TSE.';

alter table political.representative_tse_crosswalk
  drop constraint if exists representative_tse_crosswalk_match_method_check;

alter table political.representative_tse_crosswalk
  add constraint representative_tse_crosswalk_match_method_check
  check (match_method in ('exact_ballot_name_party_office', 'reviewed_official_alias'));

insert into political.representative_tse_crosswalk
  (source_kind, representative_external_id, election_year, office, candidate_id,
   match_method, evidence_url, evidence_note, vote_scope, scope_note)
values
  ('federal', '160600', 2022, 'Deputado Federal', '50001634596', 'exact_ballot_name_party_office', 'https://divulgacandcontas.tse.jus.br/', 'Nome de urna ARTHUR MAIA, nome civil compatível e partido UNIÃO no pleito de 2022.', 'person', 'Votos da candidatura no recorte municipal do TSE.'),
  ('federal', '220692', 2022, 'Deputado Federal', '50001634594', 'reviewed_official_alias', 'https://divulgacandcontas.tse.jus.br/', 'Perfil oficial Dal Barreto associado à candidatura DEPUTADO DAL; mesmo estado e partido no pleito de 2022.', 'person', 'Votos da candidatura no recorte municipal do TSE.'),
  ('federal', '74060', 2022, 'Deputado Federal', '50001605367', 'reviewed_official_alias', 'https://divulgacandcontas.tse.jus.br/', 'Perfil oficial Daniel Almeida associado ao nome civil DANIEL GOMES DE ALMEIDA; partido PCdoB no pleito de 2022.', 'person', 'Votos da candidatura no recorte municipal do TSE.'),
  ('federal', '160666', 2022, 'Deputado Federal', '50001620846', 'reviewed_official_alias', 'https://divulgacandcontas.tse.jus.br/', 'Perfil oficial Félix Mendonça Júnior associado ao nome civil FELIX DE ALMEIDA MENDONCA JUNIOR; partido PDT.', 'person', 'Votos da candidatura no recorte municipal do TSE.'),
  ('federal', '74140', 2022, 'Deputado Federal', '50001620847', 'reviewed_official_alias', 'https://divulgacandcontas.tse.jus.br/', 'Perfil oficial José Carlos Araujo associado ao nome de urna JOSÉ CARLOS ARAÚJO; candidatura histórica de 2022.', 'person', 'Votos da candidatura no recorte municipal do TSE.'),
  ('federal', '92102', 2022, 'Deputado Federal', '50001634592', 'reviewed_official_alias', 'https://divulgacandcontas.tse.jus.br/', 'Perfil oficial Leur Lomanto Júnior associado ao nome de urna LEUR LOMANTO JR.', 'person', 'Votos da candidatura no recorte municipal do TSE.'),
  ('federal', '150418', 2022, 'Deputado Federal', '50001619869', 'reviewed_official_alias', 'https://divulgacandcontas.tse.jus.br/', 'Perfil oficial Márcio Marinho associado ao nome civil MARCIO CARLOS MARINHO; partido Republicanos.', 'person', 'Votos da candidatura no recorte municipal do TSE.'),
  ('federal', '178858', 2022, 'Deputado Federal', '50001621035', 'reviewed_official_alias', 'https://divulgacandcontas.tse.jus.br/', 'Perfil oficial Mário Negromonte Jr. associado ao nome civil MÁRIO SÍLVIO MENDES NEGROMONTE JÚNIOR.', 'person', 'Votos da candidatura no recorte municipal do TSE.'),
  ('federal', '220695', 2022, 'Deputado Federal', '50001619841', 'reviewed_official_alias', 'https://divulgacandcontas.tse.jus.br/', 'Perfil oficial Rogéria Santos associado ao nome de urna ROGERIA SANTOS; partido Republicanos.', 'person', 'Votos da candidatura no recorte municipal do TSE.'),
  ('state', '921264', 2022, 'Deputado Estadual', '50001647027', 'reviewed_official_alias', 'https://divulgacandcontas.tse.jus.br/', 'Perfil oficial Antonio Henrique Júnior associado ao nome de urna ANTÔNIO HENRIQUE JR.', 'person', 'Votos da candidatura no recorte municipal do TSE.'),
  ('state', '932112', 2022, 'Deputado Estadual', '50001607301', 'reviewed_official_alias', 'https://divulgacandcontas.tse.jus.br/', 'Perfil oficial Cláudia Oliveira associado ao nome civil CLAUDIA SILVA SANTOS OLIVEIRA.', 'person', 'Votos da candidatura no recorte municipal do TSE.'),
  ('state', '915868', 2022, 'Deputado Estadual', '50001606408', 'reviewed_official_alias', 'https://divulgacandcontas.tse.jus.br/', 'Perfil oficial Fabrício Falcão associado ao nome civil JEAN FABRÍCIO FALCÃO.', 'person', 'Votos da candidatura no recorte municipal do TSE.'),
  ('state', '910636', 2022, 'Deputado Estadual', '50001606437', 'reviewed_official_alias', 'https://divulgacandcontas.tse.jus.br/', 'Perfil oficial Fátima Nunes associado ao nome civil MARIA DE FATIMA NUNES DOS ANJOS.', 'person', 'Votos da candidatura no recorte municipal do TSE.'),
  ('state', '932105', 2022, 'Deputado Estadual', '50001647026', 'reviewed_official_alias', 'https://divulgacandcontas.tse.jus.br/', 'Perfil oficial Hassan associado ao nome de urna HASSAN DE ZÉ COCÁ.', 'person', 'Votos da candidatura no recorte municipal do TSE.'),
  ('state', '932101', 2022, 'Deputado Estadual', '50001613908', 'reviewed_official_alias', 'https://divulgacandcontas.tse.jus.br/', 'Perfil oficial Jordávio Ramos associado ao nome civil JORDAVIO ALEXANDRE ESPINOLA RAMOS.', 'person', 'Votos da candidatura no recorte municipal do TSE.'),
  ('state', '926901', 2022, 'Deputado Estadual', '50001606416', 'reviewed_official_alias', 'https://divulgacandcontas.tse.jus.br/', 'Perfil oficial Júnior Muniz associado ao nome de urna JUNIOR MUNIZ.', 'person', 'Votos da candidatura no recorte municipal do TSE.'),
  ('state', '932103', 2022, 'Deputado Estadual', '50001648300', 'reviewed_official_alias', 'https://divulgacandcontas.tse.jus.br/', 'Perfil oficial Júnior Nascimento associado ao nome de urna JUNIOR NASCIMENTO.', 'person', 'Votos da candidatura no recorte municipal do TSE.'),
  ('state', '926898', 2022, 'Deputado Estadual', '50001648299', 'reviewed_official_alias', 'https://divulgacandcontas.tse.jus.br/', 'Perfil oficial Kátia Oliveira associado ao nome civil KATIA CRISTINA CERQUEIRA OLIVEIRA.', 'person', 'Votos da candidatura no recorte municipal do TSE.'),
  ('state', '932106', 2022, 'Deputado Estadual', '50001620001', 'reviewed_official_alias', 'https://divulgacandcontas.tse.jus.br/', 'Perfil oficial Luciano Araújo associado ao nome civil LUCIANO ARAUJO DE OLIVEIRA.', 'person', 'Votos da candidatura no recorte municipal do TSE.'),
  ('state', '921278', 2022, 'Deputado Estadual', '50001648313', 'reviewed_official_alias', 'https://divulgacandcontas.tse.jus.br/', 'Perfil oficial Luciano Simões Filho associado ao nome civil LUCIANO SIMOES DE CASTRO BARBOSA FILHO.', 'person', 'Votos da candidatura no recorte municipal do TSE.'),
  ('state', '932109', 2022, 'Deputado Estadual', '50001614689', 'reviewed_official_alias', 'https://divulgacandcontas.tse.jus.br/', 'Perfil oficial Matheus Ferreira associado ao nome civil MATHEUS DE OLIVEIRA FERREIRA.', 'person', 'Votos da candidatura no recorte municipal do TSE.'),
  ('state', '926914', 2022, 'Deputado Estadual', '50001606428', 'reviewed_official_alias', 'https://divulgacandcontas.tse.jus.br/', 'Perfil oficial Osni Cardoso associado ao nome civil OSNI CARDOSO DE ARAÚJO.', 'person', 'Votos da candidatura no recorte municipal do TSE.'),
  ('state', '932114', 2022, 'Deputado Estadual', '50001620926', 'reviewed_official_alias', 'https://divulgacandcontas.tse.jus.br/', 'Perfil oficial Penalva associado ao nome de urna EMERSON PENALVA.', 'person', 'Votos da candidatura no recorte municipal do TSE.'),
  ('state', '926905', 2022, 'Deputado Estadual', '50001606417', 'reviewed_official_alias', 'https://divulgacandcontas.tse.jus.br/', 'Perfil oficial Robinson Almeida associado ao nome civil ROBINSON SANTOS ALMEIDA.', 'person', 'Votos da candidatura no recorte municipal do TSE.'),
  ('state', '915881', 2022, 'Deputado Estadual', '50001606402', 'reviewed_official_alias', 'https://divulgacandcontas.tse.jus.br/', 'Perfil oficial Rosemberg Pinto associado ao nome civil ROSEMBERG EVANGELISTA PINTO.', 'person', 'Votos da candidatura no recorte municipal do TSE.'),
  ('municipal', 'cm-barreiras:vereador:0cbbdf11ba4cde77', 2024, 'Vereador', '50002071715', 'exact_ballot_name_party_office', 'https://divulgacandcontas.tse.jus.br/', 'Nome civil e nome de urna ADRIANO STEIN coincidem com o perfil oficial da Câmara; partido PL.', 'person', 'Votos da candidatura no recorte municipal do TSE.'),
  ('municipal', 'cm-barreiras:vereador:f7b7c3fd16a711f7', 2024, 'Vereador', '50002071490', 'exact_ballot_name_party_office', 'https://divulgacandcontas.tse.jus.br/', 'Nome civil ALLAN KARDEC BOMFIM BACELAR e partido MDB coincidem com o perfil oficial da Câmara.', 'person', 'Votos da candidatura no recorte municipal do TSE.'),
  ('municipal', 'cm-barreiras:vereador:5cc47cedc474435f', 2024, 'Vereador', '50002220089', 'exact_ballot_name_party_office', 'https://divulgacandcontas.tse.jus.br/', 'Nome civil ANTONIO ROCHA TEIXEIRA e partido Podemos/PODE coincidem com o perfil oficial da Câmara.', 'person', 'Votos da candidatura no recorte municipal do TSE.'),
  ('municipal', 'cm-barreiras:vereador:8a7e2a48a68faf3e', 2024, 'Vereador', '50002280819', 'exact_ballot_name_party_office', 'https://divulgacandcontas.tse.jus.br/', 'Nome civil BEN-HIR AIRES DE SANTANA e partido PSD coincidem com o perfil oficial da Câmara.', 'person', 'Votos da candidatura no recorte municipal do TSE.'),
  ('municipal', 'cm-barreiras:vereador:8ff5a9694d3167db', 2024, 'Vereador', '50002071222', 'exact_ballot_name_party_office', 'https://divulgacandcontas.tse.jus.br/', 'Nome civil CARMELIA CARVALHO DE SOUZA e partido PP coincidem com o perfil oficial da Câmara.', 'person', 'Votos da candidatura no recorte municipal do TSE.'),
  ('municipal', 'cm-barreiras:vereador:a02928d67dffceaa', 2024, 'Vereador', '50002280814', 'exact_ballot_name_party_office', 'https://divulgacandcontas.tse.jus.br/', 'Nome civil DELMA FLORENCIA PEDRA BRITTO e partido PSD coincidem com o perfil oficial da Câmara.', 'person', 'Votos da candidatura no recorte municipal do TSE.'),
  ('municipal', 'cm-barreiras:vereador:6de82b323fafc3bf', 2024, 'Vereador', '50002071544', 'exact_ballot_name_party_office', 'https://divulgacandcontas.tse.jus.br/', 'Nome civil DICIOLA FIGUEIREDO DE ANDRADE BAQUEIRO e partido União coincidem com o perfil oficial da Câmara.', 'person', 'Votos da candidatura no recorte municipal do TSE.'),
  ('municipal', 'cm-barreiras:vereador:7498d5a73db47cbf', 2024, 'Vereador', '50002071089', 'exact_ballot_name_party_office', 'https://divulgacandcontas.tse.jus.br/', 'Nome civil HELEINA BRAZ DA SILVA CHAVES e partido PDT coincidem com o perfil oficial da Câmara.', 'person', 'Votos da candidatura no recorte municipal do TSE.'),
  ('municipal', 'cm-barreiras:vereador:ca5dffb0034b8dac', 2024, 'Vereador', '50002071524', 'exact_ballot_name_party_office', 'https://divulgacandcontas.tse.jus.br/', 'Nome civil HIPÓLITO DOS PASSOS DE DEUS e partido PRD coincidem com o perfil oficial da Câmara.', 'person', 'Votos da candidatura no recorte municipal do TSE.'),
  ('municipal', 'cm-barreiras:vereador:b61169a98a68df6a', 2024, 'Vereador', '50001998990', 'exact_ballot_name_party_office', 'https://divulgacandcontas.tse.jus.br/', 'Nome civil IZABEL ROSA DE OLIVEIRA DOS SANTOS e partido PSB coincidem com o perfil oficial da Câmara.', 'person', 'Votos da candidatura no recorte municipal do TSE.'),
  ('municipal', 'cm-barreiras:vereador:944b81b35506230f', 2024, 'Vereador', '50001998971', 'exact_ballot_name_party_office', 'https://divulgacandcontas.tse.jus.br/', 'Nome civil JOÃO FELIPE DE MELO LACERDA e partido PCdoB coincidem com o perfil oficial da Câmara.', 'person', 'Votos da candidatura no recorte municipal do TSE.'),
  ('municipal', 'cm-barreiras:vereador:754c53005e6de418', 2024, 'Vereador', '50002071529', 'exact_ballot_name_party_office', 'https://divulgacandcontas.tse.jus.br/', 'Nome civil JOSE PEREIRA ROSA e partido PRD coincidem com o perfil oficial da Câmara.', 'person', 'Votos da candidatura no recorte municipal do TSE.'),
  ('municipal', 'cm-barreiras:vereador:aa1a622e47a11a1d', 2024, 'Vereador', '50002135080', 'exact_ballot_name_party_office', 'https://divulgacandcontas.tse.jus.br/', 'Nome civil MARIA DAS GRAÇAS MELO DO ESPÍRITO SANTO e partido Solidariedade coincidem com o perfil oficial da Câmara.', 'person', 'Votos da candidatura no recorte municipal do TSE.'),
  ('municipal', 'cm-barreiras:vereador:1e7094c6d5ef7b33', 2024, 'Vereador', '50002071541', 'exact_ballot_name_party_office', 'https://divulgacandcontas.tse.jus.br/', 'Nome civil RIDER MENDONÇA E CASTRO e partido União coincidem com o perfil oficial da Câmara.', 'person', 'Votos da candidatura no recorte municipal do TSE.'),
  ('municipal', 'cm-barreiras:vereador:31d971583031e75d', 2024, 'Vereador', '50002071496', 'exact_ballot_name_party_office', 'https://divulgacandcontas.tse.jus.br/', 'Nome civil RODRIGO VIEIRA SILVA e partido MDB coincidem com o perfil oficial da Câmara.', 'person', 'Votos da candidatura no recorte municipal do TSE.'),
  ('municipal', 'cm-barreiras:vereador:77df3e37e6416ab6', 2024, 'Vereador', '50002135563', 'exact_ballot_name_party_office', 'https://divulgacandcontas.tse.jus.br/', 'Nome civil SILMA ROCHA ALVES e partido Republicanos coincidem com o perfil oficial da Câmara.', 'person', 'Votos da candidatura no recorte municipal do TSE.'),
  ('municipal', 'cm-barreiras:vereador:77a0ffc47c8a3859', 2024, 'Vereador', '50002135544', 'exact_ballot_name_party_office', 'https://divulgacandcontas.tse.jus.br/', 'Nome civil THAISLANE DIAS SABEL e partido Republicanos coincidem com o perfil oficial da Câmara.', 'person', 'Votos da candidatura no recorte municipal do TSE.'),
  ('municipal', 'cm-barreiras:vereador:f852d49c295630dd', 2024, 'Vereador', '50002071092', 'exact_ballot_name_party_office', 'https://divulgacandcontas.tse.jus.br/', 'Nome civil VALDIMIRO JOSÉ DOS SANTOS FILHO e partido PDT coincidem com o perfil oficial da Câmara.', 'person', 'Votos da candidatura no recorte municipal do TSE.'),
  ('municipal', 'cm-barreiras:vereador:9a3cb3b43364dfdf', 2024, 'Vereador', '50002071521', 'exact_ballot_name_party_office', 'https://divulgacandcontas.tse.jus.br/', 'Nome civil YURE RAMON DA SILVA CUNHA e partido PRD coincidem com o perfil oficial da Câmara.', 'person', 'Votos da candidatura no recorte municipal do TSE.'),
  ('executive', 'prefeito:https://barreiras.ba.gov.br/prefeito-e-vice/:otoniel nascimento teixeira', 2024, 'Prefeito', '50002071734', 'exact_ballot_name_party_office', 'https://divulgacandcontas.tse.jus.br/prefeito-e-vice/', 'Perfil oficial do prefeito Otoniel Nascimento Teixeira coincide com a candidatura de prefeito registrada no TSE.', 'person', 'Votos da candidatura majoritária para prefeito no recorte municipal do TSE.'),
  ('executive', 'vice-prefeito:https://barreiras.ba.gov.br/prefeito-e-vice/:túlio machado viana', 2024, 'Prefeito', '50002071734', 'reviewed_official_alias', 'https://divulgacandcontas.tse.jus.br/prefeito-e-vice/', 'O vice-prefeito integra a chapa majoritária eleita; o TSE não publica votação individual separada do vice neste recorte.', 'ticket', 'Votos da chapa majoritária; não são votos individuais do vice-prefeito.')
on conflict (source_kind, representative_external_id, election_year, office, candidate_id)
do update set
  match_method = excluded.match_method,
  evidence_url = excluded.evidence_url,
  evidence_note = excluded.evidence_note,
  vote_scope = excluded.vote_scope,
  scope_note = excluded.scope_note,
  methodology_version = excluded.methodology_version;

alter table political.representative_tse_crosswalk
  drop constraint if exists representative_tse_crosswalk_match_method_check;

alter table political.representative_tse_crosswalk
  add constraint representative_tse_crosswalk_match_method_check
  check (match_method in ('exact_ballot_name_party_office', 'reviewed_official_alias'));

drop function if exists api.get_representative_tse_votes(text, text);

create function api.get_representative_tse_votes(
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
  vote_scope text,
  scope_note text,
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
  if normalized_kind is not null
     and normalized_kind not in ('federal', 'state', 'municipal', 'executive') then
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
    crosswalk.vote_scope,
    crosswalk.scope_note,
    'representative-tse-crosswalk/1.1.0'::text
  from political.representative_tse_crosswalk as crosswalk
  join raw.raw_records as record
    on record.record_type = 'tse_votacao_barreiras'
    and record.payload ->> 'sq_candidato' = crosswalk.candidate_id
    and record.payload ->> 'ano' = crosswalk.election_year::text
    and btrim(record.payload ->> 'cargo') = crosswalk.office
  where crosswalk.review_status = 'approved'
    and (normalized_kind is null or crosswalk.source_kind = normalized_kind)
    and (normalized_external_id is null
      or crosswalk.representative_external_id = normalized_external_id)
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
  'Votação municipal do TSE ligada a vereadores e executivos por crosswalk aprovado; vice-prefeito exibe votos da chapa, não votos individuais.';
