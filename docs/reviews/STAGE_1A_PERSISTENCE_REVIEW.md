# Revisão da etapa 1A — persistência inicial

Data: 30/07/2026

## Resultado

**Implementação local aprovada; gate operacional ainda aberto.**

Uma página de metadados do Querido Diário agora pode ser preservada no Storage,
restaurada e verificada por SHA-256 antes de receber referências no PostgreSQL.
O replay é idempotente e versões diferentes do parser podem coexistir.

Nenhuma coleta foi gravada em Supabase remoto porque não há projeto descartável,
login dedicado e credenciais de Storage configurados neste ambiente.

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
de US$ 0/mês, e verificado como `ACTIVE_HEALTHY`. Nenhuma migration, seed, chave,
bucket ou configuração de Auth foi aplicada nesta operação.

O próximo gate passa a ser: aplicar migrations e seed versionados, executar
advisors de segurança/desempenho, verificar schemas internos, provisionar
identidade dedicada do coletor e criar o bucket privado sem acesso público.
