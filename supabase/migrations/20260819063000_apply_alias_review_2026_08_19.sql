begin;

-- Aplica a revisao humana de aliases de 19/08/2026, registrada em
-- docs/reviews/REPRESENTATIVE_ALIAS_REVIEW_2026-08-19.md e confirmada pelo
-- titular (inclusive o caso "Melo de Oliveira" = Dra. Graca, confirmado em
-- conversa de 19/08/2026). Este arquivo e executado PELO PROPRIO REVISOR
-- ATIVO no SQL Editor: a execucao e o ato de revisao, e reviewed_by /
-- approved_by registram a identidade dele (auth 40c5bb11-...). Nada aqui e
-- decisao automatica de IA; a analise assistida apenas preparou a tabela.
-- Cada bloco toca somente sugestoes ainda pendentes: o que ja tiver sido
-- revisado na fila do admin permanece intocado.

-- 1) Aceites em que a propria cascata ja apontava match (paridade com a
--    RPC api.review_representative_alias_suggestion).
with accepted as (
  select
    suggestion.*,
    (
      select candidate ->> 'canonical_name'
      from jsonb_array_elements(suggestion.candidates) as candidate
      where candidate ->> 'representative_external_id'
        = suggestion.candidate_external_id
        and nullif(btrim(candidate ->> 'canonical_name'), '') is not null
      limit 1
    ) as canonical_name
  from political.representative_alias_suggestions as suggestion
  where suggestion.status = 'pending'
    and suggestion.decision = 'match'
    and suggestion.candidate_external_id is not null
    and suggestion.id in (
      '259edbfe-9512-4d03-b760-ec378536c79f',
      '83ae7dff-ed7c-4b27-97e7-bdbc8de22ef9',
      'cb08f95c-5573-47b0-bc4d-40a802b5a7a6',
      '7d74a723-aab9-4e6a-8107-69b02164f798',
      '1991c43c-244f-4140-bd48-62d8d086511b',
      '59e0b93c-2190-45cb-bc5e-c6035ba637ee',
      '96640d63-e652-40aa-b4d2-f0a596cf68d3',
      '73ada46b-8c4b-432e-9c35-d3410d091b9b',
      'd567e5a3-938e-439a-9223-fc4dc6ea6e15',
      '528eed31-a94e-4c72-aa17-89f7d4c965aa',
      '6371da5d-c7cd-4923-bfce-83afc5d719e9',
      'c61e1df1-127c-48e8-b228-2051ea58a96b',
      '5eb9bc7c-5258-4c12-bf55-bc57cdb7883f',
      '036884c8-54de-4cbe-9dda-26a5dc6370e2',
      '79db7a80-fd1d-4499-9edd-73438993e3e4',
      'c82e788d-3d4f-4426-a82c-1566131954d9',
      '474324ff-af66-4e5a-9616-afbca2126f0b',
      '92269798-acd7-45dd-a7f2-35793df3283c',
      '912252ad-ea56-4a1e-a0b9-8c1837d1fd04',
      '90264518-57ce-4b72-a3dc-f1b99727180d',
      'c5ea44e1-8973-4d1e-bd0f-3cd40b3383f4',
      '27c8849c-8912-47cd-8a65-3cdc186bd089',
      'b628cb5f-893f-431a-ac4d-8d35661de697',
      'a8b92d43-bc06-434f-8989-0e272da4d568',
      '8d5a0c6d-6cb2-4072-9c01-3fe67008ebf6',
      '5fd883db-2ee6-4acf-9f52-9d3e22337a41'
    )
)
insert into political.representative_aliases (
  source_kind, representative_external_id, canonical_name, alias_text,
  alias_kind, evidence_url, evidence_note, source_record_keys, approved_by
)
select
  accepted.source_kind,
  accepted.candidate_external_id,
  accepted.canonical_name,
  accepted.observed_name,
  accepted.alias_kind,
  'https://cmbarreiras.ba.gov.br/vereadores',
  'Alias aceito por revisão humana a partir de sugestão assistida '
    || '(revisão em lote de 19/08/2026, '
    || 'docs/reviews/REPRESENTATIVE_ALIAS_REVIEW_2026-08-19.md). '
    || accepted.rationale,
  accepted.source_record_keys,
  '40c5bb11-acee-48c1-991f-233e7017edba'::uuid
from accepted
where accepted.canonical_name is not null
on conflict (source_kind, representative_external_id, alias_text)
do update set
  alias_kind = excluded.alias_kind,
  evidence_note = excluded.evidence_note,
  source_record_keys = excluded.source_record_keys,
  approved_by = excluded.approved_by,
  approved_at = statement_timestamp(),
  active = true;

update political.representative_alias_suggestions as suggestion
set status = 'accepted',
    reviewed_by = '40c5bb11-acee-48c1-991f-233e7017edba'::uuid,
    reviewed_at = statement_timestamp(),
    review_note = 'Aceito na revisão em lote de 19/08/2026: variante '
      || 'literal de titular em exercício '
      || '(docs/reviews/REPRESENTATIVE_ALIAS_REVIEW_2026-08-19.md).',
    updated_at = statement_timestamp()
where suggestion.status = 'pending'
  and suggestion.decision = 'match'
  and suggestion.candidate_external_id is not null
  and exists (
    select 1
    from jsonb_array_elements(suggestion.candidates) as candidate
    where candidate ->> 'representative_external_id'
      = suggestion.candidate_external_id
      and nullif(btrim(candidate ->> 'canonical_name'), '') is not null
  )
  and suggestion.id in (
    '259edbfe-9512-4d03-b760-ec378536c79f',
    '83ae7dff-ed7c-4b27-97e7-bdbc8de22ef9',
    'cb08f95c-5573-47b0-bc4d-40a802b5a7a6',
    '7d74a723-aab9-4e6a-8107-69b02164f798',
    '1991c43c-244f-4140-bd48-62d8d086511b',
    '59e0b93c-2190-45cb-bc5e-c6035ba637ee',
    '96640d63-e652-40aa-b4d2-f0a596cf68d3',
    '73ada46b-8c4b-432e-9c35-d3410d091b9b',
    'd567e5a3-938e-439a-9223-fc4dc6ea6e15',
    '528eed31-a94e-4c72-aa17-89f7d4c965aa',
    '6371da5d-c7cd-4923-bfce-83afc5d719e9',
    'c61e1df1-127c-48e8-b228-2051ea58a96b',
    '5eb9bc7c-5258-4c12-bf55-bc57cdb7883f',
    '036884c8-54de-4cbe-9dda-26a5dc6370e2',
    '79db7a80-fd1d-4499-9edd-73438993e3e4',
    'c82e788d-3d4f-4426-a82c-1566131954d9',
    '474324ff-af66-4e5a-9616-afbca2126f0b',
    '92269798-acd7-45dd-a7f2-35793df3283c',
    '912252ad-ea56-4a1e-a0b9-8c1837d1fd04',
    '90264518-57ce-4b72-a3dc-f1b99727180d',
    'c5ea44e1-8973-4d1e-bd0f-3cd40b3383f4',
    '27c8849c-8912-47cd-8a65-3cdc186bd089',
    'b628cb5f-893f-431a-ac4d-8d35661de697',
    'a8b92d43-bc06-434f-8989-0e272da4d568',
    '8d5a0c6d-6cb2-4072-9c01-3fe67008ebf6',
    '5fd883db-2ee6-4acf-9f52-9d3e22337a41'
  );

-- 2) Aceites decididos pelo revisor onde a cascata ficou ambígua. O
--    candidato correto e a justificativa vêm da revisão humana; o nome
--    canônico vem do conjunto fechado de candidatos oficiais da sugestão.
with decisions (suggestion_id, external_id, decided_kind, decision_note) as (
  values
    (
      'c2a234c4-cd47-41c4-8a3a-0cbc616e31d7'::uuid,
      'cm-barreiras:vereador:5cc47cedc474435f',
      'case_variant',
      'Nome idêntico ao canônico sem o apelido (Tatico); único Antônio '
        || 'Rocha Teixeira no elenco.'
    ),
    (
      '1710e585-a352-4fba-9003-8f51b71587d7'::uuid,
      'cm-barreiras:vereador:5cc47cedc474435f',
      'other',
      'Rótulo editorial VEREADOR seguido do nome canônico literal.'
    ),
    (
      '9f760913-0e4f-4b43-af78-529a6a036741'::uuid,
      'cm-barreiras:vereador:9a3cb3b43364dfdf',
      'case_variant',
      'Igualdade exata com o nome canônico; a cascata marcou ambíguo por '
        || 'inconsistência.'
    ),
    (
      '91be2118-a94d-48a6-8890-3c541cbaee2a'::uuid,
      'cm-barreiras:vereador:f852d49c295630dd',
      'other',
      'Forma sem o sufixo Filho; único Valdimiro do elenco, eleito em 2024 '
        || '(TSE, ELEITO POR QP).'
    ),
    (
      'c9fed199-14fb-484e-a441-2d10b07b95bb'::uuid,
      'cm-barreiras:vereador:aa1a622e47a11a1d',
      'other',
      'Confirmado pelo titular em 19/08/2026: mesma pessoa (Drª. Graça); '
        || 'o sobrenome "de Oliveira" é grafia da fonte. Única "Maria das '
        || 'Graças Melo" no TSE 2022/2024 (eleita 2024, urna DRA GRAÇA MELO).'
    ),
    (
      'ea821181-c6e4-44fb-b823-55f4ea11d0c2'::uuid,
      'cm-barreiras:vereador:ca5dffb0034b8dac',
      'case_variant',
      'Igualdade literal com o canônico, apenas com "Dos" em maiúscula; a '
        || 'resposta da cascata foi retida pela validação, não por dúvida '
        || 'de identidade.'
    )
), overridden as (
  select
    suggestion.*,
    decisions.external_id,
    decisions.decided_kind,
    decisions.decision_note,
    (
      select candidate ->> 'canonical_name'
      from jsonb_array_elements(suggestion.candidates) as candidate
      where candidate ->> 'representative_external_id' = decisions.external_id
        and nullif(btrim(candidate ->> 'canonical_name'), '') is not null
      limit 1
    ) as canonical_name
  from political.representative_alias_suggestions as suggestion
  join decisions on decisions.suggestion_id = suggestion.id
  where suggestion.status = 'pending'
)
insert into political.representative_aliases (
  source_kind, representative_external_id, canonical_name, alias_text,
  alias_kind, evidence_url, evidence_note, source_record_keys, approved_by
)
select
  overridden.source_kind,
  overridden.external_id,
  overridden.canonical_name,
  overridden.observed_name,
  overridden.decided_kind,
  'https://cmbarreiras.ba.gov.br/vereadores',
  'Alias aceito por revisão humana (revisão em lote de 19/08/2026, '
    || 'docs/reviews/REPRESENTATIVE_ALIAS_REVIEW_2026-08-19.md). '
    || overridden.decision_note,
  overridden.source_record_keys,
  '40c5bb11-acee-48c1-991f-233e7017edba'::uuid
from overridden
where overridden.canonical_name is not null
on conflict (source_kind, representative_external_id, alias_text)
do update set
  alias_kind = excluded.alias_kind,
  evidence_note = excluded.evidence_note,
  source_record_keys = excluded.source_record_keys,
  approved_by = excluded.approved_by,
  approved_at = statement_timestamp(),
  active = true;

with decisions (suggestion_id, external_id, decision_note) as (
  values
    (
      'c2a234c4-cd47-41c4-8a3a-0cbc616e31d7'::uuid,
      'cm-barreiras:vereador:5cc47cedc474435f',
      'Nome idêntico ao canônico sem o apelido (Tatico).'
    ),
    (
      '1710e585-a352-4fba-9003-8f51b71587d7'::uuid,
      'cm-barreiras:vereador:5cc47cedc474435f',
      'Rótulo editorial VEREADOR seguido do nome canônico literal.'
    ),
    (
      '9f760913-0e4f-4b43-af78-529a6a036741'::uuid,
      'cm-barreiras:vereador:9a3cb3b43364dfdf',
      'Igualdade exata com o nome canônico.'
    ),
    (
      '91be2118-a94d-48a6-8890-3c541cbaee2a'::uuid,
      'cm-barreiras:vereador:f852d49c295630dd',
      'Forma sem o sufixo Filho; único Valdimiro do elenco (TSE 2024).'
    ),
    (
      'c9fed199-14fb-484e-a441-2d10b07b95bb'::uuid,
      'cm-barreiras:vereador:aa1a622e47a11a1d',
      'Confirmado pelo titular em 19/08/2026: mesma pessoa (Drª. Graça).'
    ),
    (
      'ea821181-c6e4-44fb-b823-55f4ea11d0c2'::uuid,
      'cm-barreiras:vereador:ca5dffb0034b8dac',
      'Igualdade literal com o canônico ("Dos" em maiúscula).'
    )
)
update political.representative_alias_suggestions as suggestion
set status = 'accepted',
    reviewed_by = '40c5bb11-acee-48c1-991f-233e7017edba'::uuid,
    reviewed_at = statement_timestamp(),
    review_note = 'Aceito na revisão em lote de 19/08/2026. '
      || decisions.decision_note,
    updated_at = statement_timestamp()
from decisions
where suggestion.id = decisions.suggestion_id
  and suggestion.status = 'pending'
  and exists (
    select 1
    from jsonb_array_elements(suggestion.candidates) as candidate
    where candidate ->> 'representative_external_id' = decisions.external_id
      and nullif(btrim(candidate ->> 'canonical_name'), '') is not null
  );

-- 3) Suplentes de 2024 em exercício: não vincular a titulares. Aguardam
--    decisão de modelagem (perfil próprio de suplente).
update political.representative_alias_suggestions
set status = 'needs_more_evidence',
    reviewed_by = '40c5bb11-acee-48c1-991f-233e7017edba'::uuid,
    reviewed_at = statement_timestamp(),
    review_note = 'Revisão em lote de 19/08/2026: suplente de vereador em '
      || '2024 (TSE) em exercício; sem perfil no elenco atual da CM. '
      || 'Vincular a um titular seria falso. Aguardando modelagem de '
      || 'suplentes.',
    updated_at = statement_timestamp()
where status = 'pending'
  and id in (
    '74641bd1-20ad-4616-9ca8-d9c9aa75bfff',
    '941491f3-5f82-478d-8df3-566966aadad1',
    '8502f5a1-cc31-4a4a-a72d-35d81f7d2124',
    '252733a3-8ae4-444c-a9a6-31c5626af07b',
    '7486c1f5-2ed9-4f2d-b2bd-a94bbcb785dc'
  );

-- 4) Autores sem identidade no acervo (legislaturas anteriores; registro
--    histórico ainda vazio; TSE coletado cobre só 2022 e 2024).
update political.representative_alias_suggestions
set status = 'needs_more_evidence',
    reviewed_by = '40c5bb11-acee-48c1-991f-233e7017edba'::uuid,
    reviewed_at = statement_timestamp(),
    review_note = 'Revisão em lote de 19/08/2026: autor(a) de legislatura '
      || 'anterior, sem correspondência no elenco atual nem no TSE '
      || '2022/2024. Aguardando povoamento do registro histórico de '
      || 'representantes.',
    updated_at = statement_timestamp()
where status = 'pending'
  and id in (
    'f6d39cde-9285-44ae-b114-2c59103b95bc',
    '22b82ffc-1e13-43e1-a8af-878a4d0896a8',
    '67493de7-dee9-45c0-bf7e-5b7a78a8a943',
    '9dc9fa42-c7b2-4f13-899d-4e52505d0c30',
    '80f197a5-3257-4afd-9f17-2fe16a11ece4',
    'f0515be2-b73d-4170-890f-19318021f820',
    '2abbc9a5-763b-4542-9519-8fa3a4c60c77',
    'cda75ed2-b0fa-4e3d-a402-2c23693d0ee1',
    '0f0a70fc-8571-4b60-82fa-d7981b31d5d3'
  );

-- 4b) Autoria do Executivo: o Prefeito eleito em 2024 assina leis, mas o
--     conjunto fechado de candidatos desta fila só contém vereadores.
update political.representative_alias_suggestions
set status = 'needs_more_evidence',
    reviewed_by = '40c5bb11-acee-48c1-991f-233e7017edba'::uuid,
    reviewed_at = statement_timestamp(),
    review_note = 'Revisão em lote de 19/08/2026: é o Prefeito eleito em '
      || '2024 (TSE, urna OTONIEL); autoria do Executivo. O vínculo correto '
      || 'é a um perfil do Executivo, não ao elenco de vereadores. '
      || 'Aguardando modelagem de autoria do Executivo.',
    updated_at = statement_timestamp()
where status = 'pending'
  and id = '1cedfe9e-ff5c-4795-b53f-b30fb4ead494';

update political.representative_alias_suggestions
set status = 'needs_more_evidence',
    reviewed_by = '40c5bb11-acee-48c1-991f-233e7017edba'::uuid,
    reviewed_at = statement_timestamp(),
    review_note = 'Revisão em lote de 19/08/2026: no TSE coletado a única '
      || 'ocorrência é candidatura a deputado estadual em 2022 (suplente), '
      || 'não vereador; sem vínculo com o elenco municipal atual.',
    updated_at = statement_timestamp()
where status = 'pending'
  and id = '0fc8a001-2851-414b-9dd0-f9ac713a6ec6';

-- 5) Registro de auditoria da revisão em lote.
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
  'reviewer',
  'auth:40c5bb11-acee-48c1-991f-233e7017edba',
  'representative_alias_suggestions.batch_reviewed',
  'political.representative_alias_suggestions',
  'review:2026-08-19',
  jsonb_build_object(
    'accepted', 32,
    'needs_more_evidence', 16,
    'rejected', 0
  ),
  jsonb_build_object(
    'review_document',
    'docs/reviews/REPRESENTATIVE_ALIAS_REVIEW_2026-08-19.md',
    'executed_by_active_reviewer_in_sql_editor', true,
    'special_case_confirmed_by_owner',
    'VEREADORA MARIA DAS GRACAS MELO DE OLIVEIRA = Dra. Graca'
  )
);

commit;
