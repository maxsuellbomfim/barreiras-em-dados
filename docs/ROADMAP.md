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

A fundação da identidade privada agora valida CPF, cifra valor e evidência com
AES-256-GCM, compara por HMAC-SHA-256 independente e recorta o cadastro oficial
do TSE somente para candidaturas previamente aprovadas. O importador e o
workflow de 2022/2024 usam a credencial exclusiva `identity_registry`, membro
somente do papel `identity_worker`, e duas chaves distintas no cofre do GitHub
Actions. Vereadores e prefeito com voto individual entram no recorte; o vice
fica bloqueado até possuir identificador individual oficial; deputados ficam
limitados aos dez estaduais e dez federais mais votados em Barreiras no primeiro
turno de cada eleição. Nenhuma chave ou CPF é transportado por input manual,
log, artefato de CI ou aplicação web.

A coleta de representação passa a isolar Câmara dos Deputados, Câmara
Municipal, ALBA e Executivo em execuções matriciais com `fail-fast: false`. Para
respeitar as duas conexões da role de coleta, a matriz usa uma conexão e o TSE
roda em job próprio com a segunda. O importador cifrado depende somente desse
acervo eleitoral. Assim, indisponibilidade de uma API parlamentar continua
visível como falha, mas não cancela fontes independentes nem posterga o
tratamento privado de identidade. Um job final consolida a saúde sem transformar
falha em ausência de registros.

A coleta financeira programada também respeita esse orçamento. Depois da matriz
municipal serializada, Transferegov, execução estadual do FIPLAN e anexos
territoriais da LOA executam em cadeia. A mudança elimina a disputa simultânea
pela role PostgreSQL do plano gratuito que, em 14/08/2026, interrompeu uma
execução com `too many connections`; a falha permanece registrada e o replay
posterior não é usado para apagar o incidente. O replay isolado
`31855664796` recuperou as dez falhas pendentes do Transferegov. Todos os
workflows que usam a role financeira compartilham agora duas filas limitadas:
uma para coletas e outra para publicações. No máximo uma execução de cada classe
chega ao banco, impedindo que agendas independentes voltem a exceder as duas
conexões sem represar todas as publicações atrás de uma coleta longa.

Em 20/08/2026, a auditoria das projeções financeiras públicas identificou outro
gargalo independente da coleta: a validação exata da origem documental era
repetida uma vez para cada linha financeira. Em produção, a leitura das 18.009
receitas elegíveis consumiu cerca de 30,8 segundos e 2,2 milhões de acessos a
blocos compartilhados. A projeção equivalente, calculando primeiro o conjunto
de pares exatos entre registro bruto e PDF, concluiu em cerca de 0,46 segundo e
13 mil acessos, sem flexibilizar a proveniência. A migration correspondente
mantém a função auxiliar privada e troca apenas as duas agregações públicas de
cobertura e fechamento mensal; publicação e valores continuam sujeitos aos
mesmos estados, versões e documentos oficiais.

Após uma indisponibilidade temporária da página HTML da ALBA, a execução manual
passa a aceitar uma fonte isolada (`federal`, `municipal`, `state`, `executive`
ou `elections`). O retry de `state` repete somente a ALBA; não baixa novamente
o arquivo eleitoral nem executa identidades privadas. A consolidação exige
`success` apenas dos jobs selecionados e exige `skipped` dos demais, de modo que
uma falha continua vermelha e nunca é convertida em sucesso por exclusão.

O leiaute oficial do cadastro de candidaturas de 2024 usa o valor numérico `-4`
quando um dado pessoal não é divulgável. O importador passa a classificar esse
caso como `not_disclosed_by_source`, em vez de `invalid_official_value`. Lacunas
anteriores sustentadas pelos mesmos hashes oficiais são supersedidas por uma
nova versão auditável; não há exclusão do histórico, criação de identidade sem
CPF oficial nem busca em fonte alternativa não autorizada.

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

Auditoria operacional em 14/08/2026 encontrou 63 autorizações territoriais da
LOA e nenhum agregado de execução persistido. O ZIP oficial estava íntegro,
com 5.686 linhas na visão de despesas, mas a persistência fazia uma ida ao banco
por linha. Uma execução controlada confirmou o gargalo: o download terminou em
17 segundos e a normalização permaneceu ativa por horas. O processador passa a
inserir o lote validado em uma única instrução transacional, e o workflow ganha
o modo `bahia-state-only` para executar e diagnosticar apenas FIPLAN e LOA, sem
abrir coletas municipais ou federais. O gate de reconciliação permanece fechado
até o replay produzir agregados e a medição comprovar correspondências oficiais
únicas.

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

Checkpoint de estabilidade em 20/08/2026: a projeção pública de atos passou
a resolver, em conjuntos materializados, a revisão editorial vigente, o
enriquecimento assistido anterior à aprovação e os metadados da edição. A
mudança elimina subconsultas repetidas por ato e preserva os mesmos critérios
de aprovação, deduplicação, evidência e ordenação; seu contrato de migração
impede a reintrodução desse padrão sujeito a timeout.

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
públicas com evidência e persistência normalizada preparados. Pagamentos de
restos a pagar de março a junho de 2026 estão publicados com acumulado anterior,
pagamento do mês e acumulado atual reconciliados por código e ligados ao PDF
oficial exato. Janeiro e fevereiro passaram por ensaio OCR remoto sem escrita:
as duas competências fecharam aritmeticamente e a progressão fevereiro-março
coincidiu. O backfill de 2021 foi publicado com dez competências validadas e
duas ausências comprovadas na fonte. Para 2022, quatro layouts oficiais foram
corrigidos; setembro é preservado como documento oficial incompleto, sem valor
inferido. O gate atual é um ensaio remoto de 2022 com zero falhas técnicas antes
da publicação idempotente das competências válidas.

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
ou recalcular valores. A explicação chegou ao detalhe público de cada mês, com
estágios contábeis separados, diferença operacional condicionada à
reconciliação e links para os documentos e hashes que sustentam receita e
despesa. A próxima menor fatia é executar o backfill idempotente dos balancetes
desde 2021 e, em seguida, normalizar empréstimos e saldos de obrigações sem
confundir dívida, pagamento e despesa do mês.

Checkpoint em 20/08/2026: o fechamento mensal e a cobertura financeira passaram
a resolver a linhagem documental em conjunto, eliminando o timeout observado na
página geral. A mesma estratégia foi aplicada às listas públicas de receitas e
linhas de despesa, sem alterar valores, filtros, versões metodológicas ou a
exigência de correspondência exata entre registro bruto e PDF. O teste de banco
descartável continua cobrindo tanto a evidência direta quanto a proveniência
corrigida e impede a volta da validação linha a linha.

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

Estado atual: o contrato oficial de Gestão de Parcerias do Transferegov foi
validado para o código IBGE de Barreiras. Propostas, distribuições, parcerias,
empenhos, documentos hábeis, ordens de pagamento e ordens bancárias possuem
coleta e preservação bruta. A projeção pública inicial separa autoria pessoal
de autoria coletiva, deduplica reexecuções e mostra valores destinados,
empenhados e pagos sem somar estágios. A próxima menor fatia é ampliar a
cobertura histórica. O backfill anual da API de Parcerias agora consulta e
classifica separadamente cada exercício desde 2021, e a página pública mostra
quando a fonte foi consultada, ficou vazia, falhou ou ainda não foi
classificada. O primeiro crosswalk de autoria individual com perfil
político foi implementado com evidência Câmara/TSE; novas associações exigem o
mesmo padrão e não são inferidas por semelhança de nome. A resposta cidadã e o
ranking da API federal atual agora aceitam recorte anual explícito, escolhendo
na abertura o exercício mais recente com emendas encontradas. Anos vazios
continuam consultáveis e são descritos como ausência na fonte atual, nunca como
valor financeiro zero; pessoas permanecem separadas de comissões e bancadas. A
página também separa a navegação entre API federal atual, arquivo federal
histórico e emendas estaduais. Somente uma origem aparece por vez, impedindo
que autorização estadual, indicação histórica e pagamento federal sejam lidos
como etapas ou valores do mesmo conjunto.

A cobertura federal também passa a ser comparável por fonte e ano em uma matriz
pública: execução regionalizada da CGU, arquivo histórico do Transferegov e API
atual de convênios. Cada célula distingue registro encontrado, fonte conferida
sem linha municipal e coleta incompleta. O ranking individual da CGU oferece um
atalho para as linhas oficiais que o compõem. A próxima menor fatia é usar essa
matriz para orientar o backfill dos anos/fontes ainda não classificados, sem
fabricar zeros e sem somar séries sobrepostas.

O catálogo oficial dos arquivos históricos de transferências discricionárias
e legais passa a ser preservado diariamente como uma fonte separada. O
manifesto monitora oito conjuntos essenciais e interrompe a cobertura quando
há paginação pendente, arquivo ausente ou URL fora do contêiner oficial. A
primeira projeção histórica de `siconv_proposta.zip` forma o conjunto candidato pelo código
IBGE oficial, preserva o ZIP nacional em área privada e exclui dados bancários e
endereços dos registros municipais. O catálogo público mostra essas propostas
separadas por ano, com situação, objeto e valores propostos, deixando explícito
que cadastro não prova transferência ou pagamento. O coletor de
`siconv_emenda.zip` agora relaciona as linhas pelo identificador oficial da
proposta, preserva o ZIP privado e minimiza o identificador do beneficiário.
A projeção pública histórica já exibe essas emendas e um ranking próprio,
mantendo autoria coletiva separada e sem chamar valor indicado de dinheiro
pago. O recorte territorial estrito também impede que projetos de consórcio
destinados a Barra/BA ou sem município comprovado sejam atribuídos a Barreiras;
esses registros continuam preservados e aparecem apenas como exclusões
metodológicas. A série corrente e o arquivo histórico federal passaram a ser
reconciliados por proposta e número oficial da emenda. Correspondências exatas
entram uma única vez; conflitos são publicados para auditoria e excluídos dos
totais. A próxima menor fatia é aplicar o mesmo contrato de evidência e
separação de estágios às emendas estaduais. O ranking federal consolidado já
evita dupla contagem entre as duas séries disponíveis.

A trilha estadual foi iniciada em fonte e cobertura próprias a partir do
conjunto diário **Emendas Parlamentares Estaduais** da SEFAZ-BA/FIPLAN. Ela
separará valor indicado, empenhado, liquidado, pago, restos e cancelamentos; o
ranking público não misturará emendas estaduais com federais e nunca tratará
anúncio ou indicação como recurso já recebido por Barreiras.

Primeira fatia concluída: preservação privada e imutável do catálogo CKAN e do
ZIP estadual, com validação estrita dos cinco CSVs e detecção de mudança de
schema. O CSV de despesas também passa a ser normalizado automaticamente após a
coleta em valores separados de orçamento, empenho, liquidação e pagamento, com
hashes e versão do parser. Como o arquivo não publica chave municipal explícita,
todo resultado permanece marcado como agregado estadual e nenhum valor entra em
totais ou rankings municipais por simples menção textual.

Cobertura pública do retrato concluída: cada snapshot validado atualiza uma
projeção anual com contagem de linhas e autores do FIPLAN desde 2021, linhagem e
hash. O painel explica que o arquivo é estadual, não informa município e não
representa valores destinados a Barreiras. A tabela privada permanece protegida
por RLS; o site consome somente uma RPC agregada e sanitizada.

Segunda fatia concluída: extração determinística das linhas territoriais de
Barreiras nos anexos oficiais da LOA 2022-2026, com evidência literal e estágio
`authorized`. O replay inicial de produção publicou 63 linhas distintas. Em
14/08/2026, uma auditoria independente pelas coordenadas das colunas dos cinco
PDFs confirmou integralmente 2022-2025 e encontrou 7 omissões em 2026, causadas
pela união visual das colunas objeto e município no texto embutido. O parser
1.2.0 recuperou essas linhas e o replay totalizou 70 registros; a projeção
pública mostra ranking e catálogo por
autor, ano, objeto, página, URL e hashes. Os 13 autores observados foram ligados
a perfis oficiais por crosswalk TSE aprovado. Marcone Amaral foi associado ao
perfil histórico oficial da ALBA e à candidatura de 2022, preservando no texto
que o mandato temporário ocorreu entre 29/01/2025 e 06/04/2026. A interface
separa a autoria publicada no orçamento do perfil oficial atualmente disponível,
evitando transformar mudança de Casa ou suplência em cargo retroativo. O próximo gate é medir
correspondências únicas, ambíguas e bloqueadas
entre as autorizações territoriais e a execução estadual normalizada. Somente
ligações determinísticas poderão alimentar a projeção pública; ausência será
descrita como “não encontrada na fonte consultada”, nunca como zero ou falta de
trabalho parlamentar.

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
- rankings estadual e federal separados por legislatura, com todos os autores
  individuais observados no recorte atual ligados a perfis oficiais;
- declarações eleitorais por pleito, com limitações;
- fotos oficiais com metadados e histórico.

Checkpoint de estabilidade em 20/08/2026: a composição atual da ALBA passou a
resolver a lista de parlamentares e o último perfil oficial em conjuntos
materializados, sem busca repetida por pessoa. O contrato preserva exatamente
nome, perfil, foto e biografia transcritos da fonte e não transforma mandato
estadual em vínculo automático com Barreiras.

Checkpoint em 21/08/2026: a cobertura estadual anual passou a ser pública em
duas etapas independentes — anexo da LOA e execução financeira. O painel torna
visível o bloqueio documental de 2021, preserva a autorização de 2022-2025 sem
fabricar execução e limita os totais executados de 2026 às ligações oficiais
únicas. A próxima entrega é ampliar o índice integral de execução para os anos
anteriores, começando por 2025.

Checkpoint adicional em 21/08/2026: a fonte oficial de Transferências
Especiais passou a gerar, em job versionado, cobertura anual sanitizada do
retrato integral. O resultado separa linhas da fonte e ocorrências territoriais
literais, não conserva dados de credor e não converte ausência de linha em
ausência de recurso. O diagnóstico passou a ter RPC sanitizada e apresentação
pública recolhida, sem somá-lo aos valores de LOA ou Transferegov. A próxima
menor entrega é classificar a disponibilidade histórica das fontes estaduais
por ano e avançar a busca oficial do retrato de execução de 2025.

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

## Checkpoint — unicidade das emendas estaduais

- [x] preservar e extrair deterministicamente o Anexo I da LOA 2026;
- [x] confrontar o parser com uma leitura geométrica independente do Anexo I:
  34 linhas e R$ 11.198.888 destinados a Barreiras em 2026; a versão anterior
  encontrava 27 linhas e R$ 9.017.541;
- [x] corrigir as 7 omissões de município colado ou separado pelo PDF, somando
  R$ 2.181.347, sem aceitar simples menção a Barreiras dentro do objeto;
- [x] validar 3.182 linhas estruturadas em 374 páginas, sem reduzir o universo
  ao recorte de Barreiras;
- [x] separar o índice estadual privado da projeção pública municipal;
- [x] executar o replay após a migration e medir quais chaves de Barreiras são
  globalmente únicas também no retrato de execução: 10 pares únicos, 21 chaves
  repetidas no Anexo I da LOA e 3 chaves ausentes no retrato estadual de 2026;
- [x] publicar estágios financeiros somente para pares bidirecionalmente
  únicos, mantendo colisões e ausências como bloqueios explicados e sem criar
  ranking de execução enquanto a cobertura permanecer parcial.
- [x] preservar o diagrama oficial das relações do FIPLAN com hash auditável e
  explicar publicamente que a base de execução não fornece município.
- [x] testar a reconciliação segura de 2022 a 2025 e registrar que os anexos
  disponíveis não fornecem uma chave oficial única; os estágios permanecem
  nulos, e 2021 continua bloqueado enquanto o anexo oficial apontar para
  exercício divergente.
- [x] publicar nos perfis ligados uma linha do tempo anual que separa o total
  autorizado do subconjunto com execução conciliada e liga cada exercício às
  evidências no catálogo estadual.

## Backlog deliberadamente adiado

- busca semântica/embeddings;
- chatbot;
- banco de grafos dedicado;
- ML complexo;
- múltiplos municípios;
- broker externo;
- microsserviços por domínio.
