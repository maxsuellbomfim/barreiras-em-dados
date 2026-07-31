# Revisão da etapa 1A — persistência inicial

Data: 30/07/2026

## Resultado

**Implementação local, fundação Supabase e identidade PostgreSQL do coletor
aprovadas; sessão real do Storage e replay remoto ainda pendentes.**

Uma página de metadados do Querido Diário agora pode ser preservada no Storage,
restaurada e verificada por SHA-256 antes de receber referências no PostgreSQL.
O replay é idempotente e versões diferentes do parser podem coexistir.

Nenhuma coleta completa foi gravada no Supabase remoto. O login PostgreSQL
dedicado foi provisionado e testado; a credencial restrita de Storage está
provisionada, mas sua sessão real ainda não foi exercitada.

## O que foi implementado

- chave de objeto derivada do SHA-256;
- upload com `upsert=false`;
- restauração e conferência de hash/tamanho antes da escrita no banco;
- registro transacional de `collection_runs`, `raw_artifacts` e `raw_records`;
- payload de cada diário preservado exatamente como recebido;
- `ON CONFLICT DO NOTHING` seguido de verificação do registro existente;
- replay sem duplicação;
- objeto preservado quando o banco falha, permitindo retry seguro;
- múltiplas observações podem referenciar o mesmo objeto;
- múltiplas versões do parser podem estruturar o mesmo artefato;
- papel `collector_worker` sem login, sem `DELETE` ou `UPDATE` no bruto;
- comando operacional limitado a uma janela de sete dias;
- validação de TLS, segredo server-side e login dedicado em produção.

## Verificações

- 24 testes Python offline: aprovados;
- Ruff lint: aprovado;
- Ruff format: aprovado;
- 5 contratos JSON Schema: aprovados;
- 2 catálogos de fontes, 79 recursos: aprovados;
- 2 migrations e seed reaplicável em PostgreSQL embutido: aprovados;
- imutabilidade de `raw_artifacts` exercitada por teste negativo;
- duas versões de parser no mesmo índice de artefato: aprovadas;
- replay da mesma chave de registro: uma única linha;
- comando operacional carrega e exibe ajuda sem acessar a rede.

PGlite valida SQL PostgreSQL, mas não substitui o teste final no stack Supabase.

## Revisão de segurança

Controles presentes:

- bucket bruto permanece privado;
- segredo de Storage não possui prefixo público;
- URL remota do banco exige `sslmode`;
- staging/produção rejeitam login `postgres`;
- SQL é parametrizado;
- transação não contém chamada HTTP;
- role do coletor possui grants por tabela e coluna;
- tabelas brutas bloqueiam mutação por trigger mesmo para outra role de
  aplicação;
- object key não contém nome de pessoa, URL ou parâmetro externo;
- falha de integridade impede registro no banco.

Pendências:

- `SUPABASE_SECRET_KEY` ignora RLS e possui alcance amplo. Antes de produção,
  substituir por identidade de workload e política restrita ao bucket
  `raw-artifacts` e ao prefixo do coletor;
- testar grants usando o login real do worker, não apenas `has_*_privilege`;
- aplicar migrations em Supabase descartável e executar advisors/lint;
- configurar rotação, backup independente e alerta de hash divergente;
- definir reconciliação de objetos órfãos após falha permanente do banco;
- Storage não oferece, nesta configuração, prova externa de WORM/object lock.

## Revisão de qualidade dos dados

Controles presentes:

- bytes recebidos são a autoridade do registro bruto;
- campos futuros da API são preservados;
- identidade da edição usa território, data, edição, tipo e URL;
- observação e conteúdo não são confundidos;
- versão do parser faz parte da idempotência do registro;
- resposta vazia continua diferente de falha;
- URL solicitada, URL final, cursor, ETag e horários ficam registrados.

Pendências:

- testar duas URLs diferentes retornando o mesmo conteúdo;
- testar a mesma URL mudando de conteúdo entre coletas;
- criar inventário de lacunas por edição/data;
- baixar e preservar PDF/texto como artefatos filhos;
- verificar MIME real dos documentos antes de processamento;
- comparar cobertura do agregador com o Diário Oficial direto.

## Limitações

- não há download de PDF ou TXT;
- não há DLQ persistida para falha da etapa de armazenamento;
- não há health/status interno;
- não há parser de nomeação/exoneração;
- não há publicação, admin ou página pública;
- não existe lockfile Python; versões diretas estão fixadas no `pyproject.toml`,
  mas dependências transitivas ainda precisam de lock reproduzível.

## Próxima menor etapa

1. criar projeto Supabase descartável;
2. aplicar migrations e seed;
3. provisionar login dedicado membro de `collector_worker`;
4. restringir a credencial de Storage ao bucket/prefixo;
5. executar uma janela de um dia;
6. repetir a mesma janela e conferir contagens;
7. restaurar o objeto remoto e comparar o SHA-256;
8. expor apenas health/status interno da fonte.

Somente depois: baixar PDF/TXT como artefatos filhos. Parser de atos e PNCP
continuam fora desta etapa.

## Adendo — modo local portável

Data: 30/07/2026

O passo remoto acima foi adiado porque a conta Supabase atingiu o limite de dois
projetos gratuitos. Nenhum projeto existente foi reutilizado, pausado ou
apagado. O ADR 0008 substitui a dependência operacional imediata por um modo
local restrito a desenvolvimento/teste.

### Implementado

- objetos locais endereçados por SHA-256 e criados sem overwrite;
- restauração e hash verificados depois da escrita;
- manifestos canônicos com hash no nome do arquivo;
- uma versão de manifesto por execução e versão de parser;
- IDs locais determinísticos para execução e artefato;
- replay alinhado à idempotência do repositório PostgreSQL;
- bloqueio de travessia de diretório e links simbólicos;
- recusa do modo `filesystem` em staging/produção;
- configuração local sem chaves ou banco.

### Verificação

- 33 testes Python: aprovados;
- Ruff lint e format: aprovados;
- coleta pública real de `2026-06-10`: 2 registros preservados;
- replay da mesma janela: 1 objeto e 1 manifesto, sem duplicação;
- janela `2026-07-01`: resposta `empty` preservada sem ser tratada como falha;
- hashes do objeto e do manifesto conferem com seus nomes;
- alteração de objeto e manifesto exercitada por testes negativos.

O acervo de ensaio está em `data/local-evidence/` e não integra o repositório.
Ele não substitui o teste futuro de PostgreSQL, grants, backup e armazenamento
privado no provedor escolhido.

### Próxima menor etapa

Baixar um único PDF e, quando disponível, seu TXT como artefatos filhos,
aplicando allowlist de host, limite de tamanho, MIME real, SHA-256, replay e
relação explícita com a edição de origem. Ainda não interpretar nem publicar o
conteúdo.

## Adendo — projeto Supabase provisionado

Data: 30/07/2026

Com autorização expressa, `Site Kelvin Vinicius` foi pausado de forma
recuperável para liberar a cota gratuita. `Maxsuell Bomfim | Defesa em Saúde`
permaneceu ativo e intocado.

O projeto `Barreiras em Dados` foi criado em `sa-east-1`, com custo confirmado
de US$ 0/mês, e verificado como `ACTIVE_HEALTHY`.

## Adendo — migrations, seed e hardening remoto

Data: 30/07/2026

Com autorização expressa, somente o projeto `Barreiras em Dados`
(`mpladsyzilmgiefejpkq`) recebeu as alterações. Os demais projetos Supabase não
foram modificados.

Foram aplicadas, em ordem:

1. `initial_public_data_foundation`;
2. `collector_persistence_boundaries`;
3. `harden_extensions_and_foreign_keys`.

O seed foi executado de forma idempotente e cadastrou três fontes, três
endpoints e o bucket privado `raw-artifacts`. O bucket aceita JSON, PDF, bytes,
HTML e texto, com limite de 100 MB por objeto.

### Verificação remota

- projeto: `ACTIVE_HEALTHY`, PostgreSQL 17, `sa-east-1`;
- 39 tabelas nos schemas internos e 0 tabelas no schema `public`;
- `anon` sem `USAGE` em `source`, `raw`, `hr` e `procurement`;
- 5 triggers append-only sobre evidência e auditoria;
- `collector_worker` sem login, superusuário, criação de banco/role,
  replicação ou `BYPASSRLS`;
- grants de inserção do coletor limitados por coluna;
- coletor sem `DELETE` em `raw_artifacts` e sem `UPDATE` em `raw_records`;
- `pg_trgm` movida de `public` para `extensions`;
- 123 chaves estrangeiras, nenhuma sem índice de cobertura;
- advisor de segurança: 0 alertas;
- advisor de desempenho: somente índices ainda não utilizados, condição
  esperada antes da primeira carga.
- replay remoto do seed: 3 fontes, 3 endpoints e 1 bucket, sem duplicação.

O teste PostgreSQL embutido foi ampliado para impedir regressão do schema da
extensão e da cobertura de índices e permanece aprovado. O bucket privado não
equivale a uma credencial de workload restrita: políticas, login real e testes
negativos continuam sendo o gate antes da primeira escrita remota.

### Próxima menor etapa

1. provisionar login dedicado membro de `collector_worker`;
2. restringir a identidade de Storage a `raw-artifacts` e ao prefixo do
   coletor;
3. testar que a identidade consegue inserir somente as colunas previstas;
4. testar que não consegue apagar nem alterar evidência bruta;
5. executar e repetir uma única janela de um dia;
6. restaurar o objeto remoto e comparar SHA-256.

Somente depois desse gate: baixar PDF/TXT como artefatos filhos. Parser de atos,
admin e PNCP permanecem fora desta etapa.

## Adendo — fronteiras da identidade do coletor

Data: 30/07/2026

Duas migrations adicionais foram aplicadas no projeto `Barreiras em Dados`:

1. `provision_collector_workload_boundaries`;
2. `deny_direct_workload_identity_access`.

O banco agora possui 40 tabelas internas. A role
`collector_querido_diario` foi criada com `NOLOGIN`, `INHERIT`, limite de duas
conexões e sem privilégios administrativos. Ela é membro de `collector_worker`,
herda inserções por coluna e continua sem `DELETE` em `raw_artifacts` nem
`UPDATE` em `raw_records`.

O Storage recebeu duas policies para `authenticated`: `SELECT` e `INSERT`.
Ambas exigem UUID presente e ativo em
`audit.storage_workload_identities`, bucket `raw-artifacts` e prefixo
`querido-diario/gazettes/`. Naquele momento, a allowlist estava vazia e o
projeto continuava com zero usuários Auth. Acesso direto à allowlist possui
política restritiva de negação.

### Testes

- UUID Auth não cadastrado: leitura e inserção negadas;
- outro bucket: negado;
- outro prefixo: negado;
- operação `DELETE`: negada;
- função de autorização: executável por `authenticated`, não por `anon`;
- advisor de segurança depois das policies: zero alertas;
- teste local de RLS permite o prefixo correto e bloqueia fuga de prefixo e
  exclusão;
- coletor atualizado para chave publicável + sessão Auth;
- secret/service role recusada pela validação de ambiente;
- 35 testes Python aprovados.

Nenhuma senha, usuário Auth ou login PostgreSQL foi ativado. A próxima ação é
manual e está descrita em `docs/COLLECTOR_CREDENTIALS.md`: o responsável cria o
usuário técnico no painel, guarda sua senha fora do chat e informa somente o
User UID.

## Adendo — identidade Auth do Storage ativada

Data: 30/07/2026

O User UID `d3e7a733-6101-4c9e-8d7a-d0f88a243eee`, informado expressamente
pelo responsável, foi validado sem consultar ou expor e-mail e senha. O usuário
está confirmado, não é anônimo, não está banido nem marcado como excluído e
possui identidade de senha.

A identidade foi registrada na allowlist com slug
`querido-diario-collector`, bucket `raw-artifacts`, prefixo
`querido-diario/gazettes/`, `SELECT` e `INSERT`. A ativação gerou um evento
append-only em `audit.audit_events`.

### Testes remotos de autorização

- UUID autorizado no bucket e prefixo corretos: `SELECT` e `INSERT` permitidos;
- `UPDATE` e `DELETE`: negados;
- outro prefixo e outro bucket: negados;
- UUID aleatório não cadastrado: `SELECT` e `INSERT` negados;
- uma identidade ativa e um evento de ativação registrados;
- role `collector_querido_diario`: permanece com `NOLOGIN`.

O advisor de segurança não encontrou falha de RLS ou exposição de dados. Há um
aviso de que a proteção do Auth contra senhas vazadas está desativada. Enquanto
esse recurso não for habilitado, a mitigação obrigatória é uma senha aleatória,
exclusiva e longa no gerenciador de senhas.

### Limitação e próximo gate

Os testes exercitaram as mesmas funções e condições das policies com o UUID
real, mas não fizeram login HTTP nem upload real porque a senha permaneceu
corretamente fora do chat. O próximo gate é ativar a role PostgreSQL por
`psql` com prompt interativo e, depois, testar as duas sessões reais sem revelar
segredos.

## Adendo — cliente PostgreSQL instalado

Data: 30/07/2026

O cliente `psql 17.10` foi instalado no perfil do usuário a partir do arquivo
ZIP Windows x64 indicado pela página oficial do PostgreSQL/EDB. Foram extraídos
somente `psql.exe` e suas DLLs de runtime: `postgres.exe` não está presente e
nenhum serviço PostgreSQL foi criado.

O ZIP tinha 333.927.270 bytes e SHA-256
`ef9b1e5e23d2e8a83914ba13d9dc536a72210fba53fd1808ff1f7e06bb22b106`.
O arquivo temporário foi removido depois da instalação. O executável não possui
assinatura Authenticode; origem HTTPS oficial e hash registrado são os controles
de proveniência disponíveis para este pacote.

Nenhuma conexão com o banco foi feita e nenhuma senha foi criada, consultada ou
redefinida nesta ação. O próximo gate continua sendo obter acesso administrativo
por um canal seguro e usar `\password collector_querido_diario` no prompt
interativo.

## Adendo — identidade PostgreSQL ativada

Data: 30/07/2026

Com autorização expressa, a senha administrativa foi redefinida somente no
projeto `Barreiras em Dados`, antes de existirem integrações dependentes dela. A
senha foi gerada e guardada pelo responsável fora do chat e do Git.

O acesso temporário descrito na documentação não estava disponível na tela de
Database Settings. Nenhuma restrição de rede foi ampliada e nenhum outro projeto
Supabase foi alterado.

A conexão administrativa usou o Session pooler em `sa-east-1`,
`sslmode=verify-full` e o certificado `Supabase Root 2021 CA`. Dentro de uma
transação, a senha do coletor foi definida enquanto a role ainda estava com
`NOLOGIN`; somente depois o LOGIN foi ativado com limite de duas conexões. O
evento `database_workload_identity.activated` foi inserido na auditoria antes do
commit.

### Verificação remota

- role com LOGIN e limite de 2 conexões;
- membro de `collector_worker`;
- sem superusuário, criação de role/banco, replicação ou `BYPASSRLS`;
- sem `DELETE` em `raw.raw_artifacts`;
- sem `UPDATE` em `raw.raw_records`;
- exatamente um evento de ativação;
- advisor sem falha de RLS ou exposição de dados;
- permanece o aviso de proteção contra senhas vazadas desativada no Auth.

O roteiro operacional temporário foi removido. As senhas administrativa e do
coletor não foram observadas pelo agente.

## Adendo — sessão real do coletor PostgreSQL aprovada

Data: 30/07/2026

O teste foi aberto em terminal interativo e solicitou somente a senha da role
`collector_querido_diario`. A senha foi colada no prompt oculto do `psql` e não
foi registrada em arquivo, chat ou Git.

A conexão utilizou o Session pooler em `sa-east-1`, usuário com sufixo do projeto,
`sslmode=verify-full` e o certificado `Supabase Root 2021 CA`. O teste
determinístico confirmou:

- `current_user = collector_querido_diario`;
- inserção permitida em `source.collection_runs`;
- negação real de `DELETE` em `raw.raw_artifacts`;
- negação real de `UPDATE` em `raw.raw_records`;
- rollback da inserção temporária;
- zero registros com prefixo `credential-smoke-test` após a sessão.

Ainda falta testar uma sessão real do Storage com a identidade Auth restrita e,
em seguida, executar a primeira coleta remota de um dia com replay idempotente.
