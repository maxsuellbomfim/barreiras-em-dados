# Importação privada de identidades políticas

## Finalidade e recorte

O workload associa pessoas a candidaturas oficiais sem transformar CPF em dado
público. Ele processa somente crosswalks aprovados e com voto individual:

- vereadores e prefeito cobertos pelo pleito municipal;
- dez candidaturas a deputado federal mais votadas em Barreiras por eleição;
- dez candidaturas a deputado estadual mais votadas em Barreiras por eleição.

O primeiro e o segundo turno nunca são somados. O vice-prefeito não herda o CPF
do titular da chapa e permanece fora do importador até existir identificador
individual em fonte oficial.

## Limite de segurança

1. A migration cria `identity_registry` como `NOLOGIN`, membro somente de
   `identity_worker`, com uma conexão e timeouts restritos.
2. A habilitação de `LOGIN` e a senha são procedimentos operacionais no banco;
   a senha nunca entra em migration ou Git.
3. `IDENTITY_DATABASE_URL` deve usar esse login, `sslmode=verify-full` e a CA
   versionada em `config/certificates/supabase-prod-ca-2021.crt`.
4. `IDENTITY_AES_KEY_B64` e `IDENTITY_HMAC_KEY_B64` devem ser duas chaves Base64
   distintas de 32 bytes. `IDENTITY_KEY_VERSION` começa em `1`.
5. Os quatro valores ficam somente em GitHub Actions Secrets.

O workflow não recebe esses segredos no nível do job. Apenas a verificação de
presença e o comando privado recebem cada valor. Logs contêm exclusivamente ano,
quantidades inseridas, replays idempotentes e conflitos.

## Execução e confirmação

Após aplicar a migration e configurar os segredos, execute **Coletar
representação política**. O job **Registrar identidades privadas oficiais** deve
produzir uma linha JSON por ano com `selected`, `inserted`, `unchanged`,
`conflicted` e `unavailable`.

Critérios:

- reexecução do mesmo cadastro retorna somente `unchanged`;
- candidatura aprovada ausente no arquivo do TSE aborta o ano antes da primeira
  gravação;
- CPF divergente gera conflito privado e nunca fusão automática;
- CPF ausente ou inválido na linha oficial não interrompe as demais
  candidaturas: a linha integral fica cifrada em
  `private.person_identifier_sources` e a lacuna fica registrada em
  `private.person_identifier_gaps`, sem inventar identificador;
- nenhuma sequência de CPF, fingerprint, quatro últimos dígitos, cifra, senha ou
  chave pode aparecer no log ou em artefato;
- `anon`, `authenticated`, `collector_worker`, web e admin não possuem leitura.

## Rotação e incidente

Uma rotação incrementa `IDENTITY_KEY_VERSION` e agenda recifra controlada antes
de revogar a chave anterior. Em suspeita de exposição, desative `LOGIN` de
`identity_registry`, revogue/rotacione as chaves e preserve os registros de
auditoria. Nunca apague evidência histórica para esconder o incidente.
