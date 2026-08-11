# Roadmap

## Regra de progressão

Uma fase só termina quando testes, segurança, qualidade de dados, documentação,
limitações e recuperação de falhas estiverem estáveis. “Código escrito” não é
critério de saída.

## Programa transversal de estabilização e expansão (iniciado em 05/08/2026)

Ordem aprovada: plano central de cobertura/falhas; backfill classificado desde
2021; identidade privada; normalização das fontes ainda brutas; e rastro do
dinheiro. A primeira entrega adiciona `source.collection_partitions`,
`source.collection_failures`, `private.person_identifiers` e
`identity.person_aliases`, integra o Diário direto ao controle e inclui a suíte
Node no CI.

A segunda entrega integra a janela principal do Querido Diário e os recursos
financeiros municipais suportados. Cada execução começa antes da autenticação e
do HTTP; orçamento de documentos, paginação limitada e falha parcial passam a
ser visíveis como cobertura `partial`, sem apagar os dados já preservados.

A terceira entrega consome automaticamente o `next_offset` das partições
municipais parciais e integra as janelas de contratações do PNCP ao controle
central. Modalidades truncadas ficam registradas como `partial`.

A quarta entrega inclui cadastro, itens, resultados e contratos do PNCP no
mesmo contrato. Limites de backlog/página agora são `partial`, e contratos
percorrem todas as páginas declaradas pela fonte. Backlogs retomam do
`next_offset`, evitando inanição dos registros posteriores ao primeiro lote.
Legislativo e Representação eram as próximas fatias de estabilização.

A quinta entrega torna o plano de controle visível no painel administrativo.
Revisores passam a enxergar endpoints ainda sem cobertura, períodos completos
ou comprovadamente vazios, partições parciais/bloqueadas e falhas pendentes,
sem receber dados brutos sensíveis.

A sexta entrega leva Legislativo e Representação ao mesmo contrato. Leis,
indicações, composição federal e municipal, Executivo, lista e perfis da ALBA e
votação do TSE passam a registrar execução antes da autenticação e do HTTP. A
próxima fatia é usar essa cobertura observada para abrir o backfill amplo desde
2021, começando pelos recursos com período oficial bem definido.

O backfill do Diário agora calcula a fronteira pela faixa contínua de execuções
bem-sucedidas até a véspera. Um registro histórico isolado não pode mais saltar
lacunas recentes nem encerrar prematuramente a cobertura desde 2021. Janelas
antigas preservadas continuam válidas, mas só se unem à fronteira quando os
intervalos intermediários também forem coletados ou confirmados como vazios.
O painel administrativo passa a exibir essa faixa contínua, o progresso em dias
e a próxima janela de sete dias, sem tratar um workflow verde como prova isolada
de cobertura.

Cada coletor só entra no backfill amplo depois de registrar execução antes do
HTTP e classificar cada partição como completa, vazia, parcial, falha ou
bloqueada.

### Portal público de pré-lançamento

Uma página institucional pode permanecer no ar durante a etapa 1A para explicar
fontes, método e andamento. Ela não antecipa o gate da etapa 1C: não contém
registros municipais normalizados, alegações, anomalias ou métricas de gestão.
Todo número exibido nessa página descreve a infraestrutura e recebe contexto
explícito.

## Etapa 0 — Fundação

Escopo:

- visão, arquitetura, fontes, governança, editorial, segurança e metodologia;
- ADRs e subagentes Claude Code;
- estrutura do monorepo;
- contratos iniciais;
- migration fundamental;
- conector paginado do Querido Diário com fixtures e testes.

Gate:

- documentação revisada;
- schemas validáveis;
- migration aplica em banco descartável e seed é reaplicável;
- testes de conector sem rede passam;
- teste smoke contra API pode falhar explicitamente por indisponibilidade;
- nenhuma chave ou dado pessoal real no repositório.

## Etapa 1A — Coleta preservada do Diário

Menor próxima fatia vertical:

1. cadastrar Querido Diário e endpoint em seed;
2. coletar uma janela pequena de edições;
3. salvar cada página JSON bruta;
4. baixar PDF/texto com limites;
5. verificar hashes e idempotência;
6. exibir status agregado da coleta, sem registros ou conteúdo reputacional.

Gate:

- replay produz os mesmos registros sem duplicar;
- modo local é restrito a desenvolvimento/teste e detecta adulteração;
- 429/5xx/timeout/circuit breaker/DLQ testados;
- lacunas e última coleta visíveis;
- restauração de um artefato por hash comprovada;
- antes de staging, bucket privado, grants e backup do provedor são revisados.

Estado em 31/07/2026 — **etapa encerrada**:

- gate integralmente cumprido: replay idempotente validado em produção,
  PDF/texto como artefatos filhos verificados por hash (execução nº 5),
  caminho de falha exercitado de verdade com DLQ sanitizada (execução nº 4),
  status público agregado no ar, visão interna de lacunas
  (`source.querido_diario_daily_coverage`) sem acesso anônimo e revisão de
  bucket, grants e backup registrada;
- limitação aceita: o plano gratuito do provedor não oferece backup
  automático; mitigação registrada na revisão de encerramento;
- revisões: `docs/reviews/STAGE_1A_PUBLIC_STATUS_REVIEW.md`,
  `docs/reviews/STAGE_1A_DOCUMENT_ARTIFACTS_REVIEW.md` e
  `docs/reviews/STAGE_1A_CLOSURE_REVIEW.md`.

## Etapa 1B — Documento e extração candidata

- páginas e texto canônico;
- identificação determinística de candidatos;
- extração de nomeação/exoneração;
- pessoa, cargo, órgão, data e vigência com incerteza por campo;
- amostra anotada e métricas;
- fila de revisão.

Estado em 01/08/2026:

- fatia inicial implementada: texto canônico em `raw.document_pages`,
  candidatos determinísticos versionados em fila `needs_review` e passo diário
  no workflow, aguardando validação remota
  (`docs/reviews/STAGE_1B_CANDIDATE_QUEUE_REVIEW.md`);
- backfill retroativo automático: um segundo agendamento diário resolve, a
  partir do banco, a próxima janela curta anterior à cobertura existente e
  avança até `QUERIDO_DIARIO_BACKFILL_HORIZON` (2021-01-01, cobrindo a gestão
  anterior), com janelas vazias também progredindo;
- fonte primária trocada: o Querido Diário parou em 10/06/2026 (a prefeitura
  migrou o diário de plataforma) e um coletor direto por cursor de edição
  preserva os PDFs oficiais de `barreiras.ba.gov.br`, com o QD como backfill
  e verificação cruzada
  (`docs/reviews/STAGE_1B_DIRECT_DIARY_DISCOVERY.md`);
- OCR Tesseract (por) para páginas escaneadas, como passo do workflow;
- resumos assistidos por cascata determinística de provedores de IA
  (ADR 0011) anexados aos candidatos da fila — nunca publicados sem revisão;
- primeiro candidato real revisado e rejeitado com justificativa
  ("menção, não é ato"), exercitando aprovação por engano + retirada +
  decisão final com histórico íntegro.

Gate:

- precisão/revocação mínimas definidas com especialista;
- nenhum candidato publicado;
- trecho e offsets reproduzíveis;
- PDFs hostis e OCR falho tratados.

## Etapa 1C — Revisão e publicação

Estado em 01/08/2026: fatias 1 a 3 implementadas — fila de revisão
autenticada em `apps/admin` com identidades de revisor auditáveis e negação
explícita; decisão humana (aprovar/rejeitar) com justificativa obrigatória
gravada em `editorial.editorial_reviews` + auditoria, sem tocar no bruto;
retirada de decisão e histórico completo por candidato; projeção pública
somente de aprovados em `/atos`, com trecho, documento oficial, hash e o
resumo assistido revisado publicado junto (princípio: tudo publicado tem
explicação simples); canal público de correção via issues do repositório
(`docs/reviews/STAGE_1C_ADMIN_QUEUE_REVIEW.md`). Pendentes: MFA (adiado por
decisão do titular; obrigatório antes do lançamento), dupla revisão de
amostra e testes negativos de autorização em produção.

- admin com MFA e estados editoriais;
- aprovação/rejeição auditada;
- projeção pública somente de aprovados;
- linha do tempo, filtros e documento/trecho;
- canal de correção;
- acessibilidade e performance.

Gate:

- testes negativos de autorização;
- dupla revisão de amostra;
- retração/correção sem apagar histórico;
- WCAG 2.1 AA e fluxo móvel verificados.

## Etapa 2 — PNCP e portais locais de contratação

Sequência:

1. cadastro confirmado de órgãos/unidades por CNPJ;
2. contratações e histórico de atualização;
3. itens e resultados;
4. contratos/empenhos;
5. documentos e fornecedores;
6. coleta de `contratos`, `processos` e `licitacoes` das APIs locais;
7. reconciliação sem fonte vencedora global e páginas públicas.

Estado em 01/08/2026 — itens 1 a 3 implementados na camada bruta:

- cadastro (órgão + unidades) preservado semanalmente por CNPJ;
- contratações das 13 modalidades da Lei 14.133/2021 com paginação completa,
  janela semanal e backfill diário até 2021-07-01 (validação do PNCP);
- itens e resultados homologados derivados do banco: contratações sem itens
  preservados ou publicadas nos últimos 120 dias são revisitadas (homologação
  tardia), com teto explícito por execução e truncamento sempre logado;
- limitação observada: a API `consulta/v1` do PNCP estava degradada na fonte
  em 01/08/2026 (500/504); a primeira janela real de contratações ainda
  aguarda validação remota nos agendamentos.

Gate:

- paginação completa;
- erro HTTP 200 com raiz `error` tratado como falha;
- orçamento sigiloso modelado corretamente;
- itens/contratos com evidência e histórico;
- nenhuma comparação de preços nesta fase.

## Etapa 3 — Execução orçamentária

Portais locais, SICONFI e TCM-BA:

- receitas;
- empenhos, liquidações e pagamentos;
- órgãos, fontes de recurso e classificações;
- conflitos entre fontes.

Estado atual: contratos determinísticos de receita e obrigações, projeções
públicas com evidência e persistência normalizada preparados; a reconciliação
de uma amostra real de obrigações ainda está pendente.

Próxima fatia em execução: fechamento mensal operacional, com receita no nível
do total declarado por documento e pagamentos no nível do relatório validado;
inventário interno dos PDFs preservados, filas, falhas e publicações; e
comentário assistido somente depois que os números determinísticos estiverem
fechados. Empréstimos e dívidas já possuem entidade e evidência próprias; a
próxima fatia é normalizar uma família documental real e reconciliar as linhas
antes de publicar qualquer consolidação.

O painel administrativo passa a diagnosticar cada competência desde 2021 como
pronta, incompleta, duplicada ou bloqueada. O diagnóstico distingue vínculo
direto, correção versionada de proveniência e pendência documental sem usar IA
ou recalcular valores. A próxima menor fatia é levar essa explicação ao detalhe
público do mês, com links para os documentos que sustentam receita e despesa.

Gate:

- unidade/escala contábil verificadas;
- totais reconciliáveis e determinísticos;
- períodos e retificações preservados;
- explicações populares revisadas por especialista.

## Etapa 4 — RH, concursos, diárias e obras

Entradas independentes, cada uma com política de minimização e gate próprio.
Folha não será simplesmente importada e publicada integralmente.

## Etapa 5 — Fluxos territoriais

- receita diária somente após modelar data contábil, estornos e atualização;
- transferências constitucionais, legais, voluntárias, fundo a fundo e
  especiais;
- emendas por autoria, beneficiário, objeto e estágio financeiro;
- recursos estaduais e federais destinados a Barreiras;
- páginas de órgãos e secretarias com atos, metas e execução verificáveis.

Gate:

- valores reconciliados sem somar estágios incompatíveis;
- cobertura e atraso visíveis;
- vínculo entre entrada e despesa somente com chave determinística ou revisão;
- nenhuma nota subjetiva de utilidade ou desempenho.

## Etapa 6 — Representação política

### 6A — Perfil municipal mínimo

- roster oficial de prefeito, vice, secretários e vereadores;
- cargo, vigência, partido quando aplicável e evidência;
- subsídio legal e remuneração bruta por competência;
- candidaturas municipais de 2024 e candidaturas oficiais de 2026;
- página com cobertura, atualização e correções.

### 6B — Atuação e representação ampliada

- critérios públicos de vínculo territorial;
- mandatos estaduais e federais acompanhados;
- proposições, votações, comissões, agenda e despesas;
- emendas relacionadas a Barreiras;
- declarações eleitorais por pleito, com limitações;
- fotos oficiais com metadados e histórico.

Gate:

- identidade e vínculo territorial revisados;
- metodologia igual para partido, gestão e pessoa;
- bens eleitorais não apresentados como patrimônio atual;
- nenhuma conclusão reputacional automática.
- ausência de fonte não exibida como zero ou “ficha limpa”.

## Etapa 7 — Registros oficiais e rede de vínculos

- CEIS, CNEP, CEPIM, CEAF e acordos por identificador exato;
- QSA da Receita Federal com minimização;
- rede de vínculos públicos em PostgreSQL e React Flow;
- exportações verificáveis em PDF, DOCX e XLSX;
- avaliação separada do DataJud.

Gate:

- evidência por nó e por aresta;
- homônimo não publicado como identidade;
- sanção não propagada a pessoas relacionadas;
- exports auditados e submetidos às mesmas regras do portal;
- DataJud liberado somente por parecer jurídico e esclarecimento do CNJ.

## Etapa 8 — Anomalias

Ativar apenas regras operacionais de baixo risco. Regras financeiras ou
reputacionais exigem amostra anotada, especialista, revisão legal/editorial e
ADR adicional.

## Backlog deliberadamente adiado

- busca semântica/embeddings;
- chatbot;
- banco de grafos dedicado;
- ML complexo;
- múltiplos municípios;
- broker externo;
- microsserviços por domínio.
