# Fontes de dados

## Regra de admissão

“Oficial” não significa “completo”, “correto” ou “estável”. Cada fonte entra por
um processo de descoberta e recebe:

- responsável/publicador;
- base URL e endpoints;
- cobertura institucional e temporal;
- formato e paginação;
- limites de consumo e termos de uso;
- campos identificadores e semântica de atualização;
- estratégia de coleta incremental e backfill;
- riscos de disponibilidade, qualidade e dados pessoais;
- fixture sanitizada, teste de contrato e owner interno;
- data da última verificação.

URLs não auditadas não devem ser codificadas como contrato permanente.

## Registro inicial

| Fonte | Escopo pretendido | Prioridade | Estado |
|---|---|---:|---|
| Querido Diário | Diário Oficial do Executivo | P0 | descoberta concluída |
| Diário Oficial da Prefeitura | PDF original e metadados | P0 | catálogo e PDF direto ativos |
| Transparência da Prefeitura | contratos, processos, documentos, RH, fiscal e PDC | P1 | API catalogada |
| Transparência da Câmara | contratos, documentos, RH, atos e atividade legislativa | P1 | API catalogada |
| PNCP | contratações, itens, resultados, contratos, documentos | P1 | documentação inicial |
| SICONFI | demonstrativos contábeis e fiscais | P2 | documentação inicial |
| TCM-BA | dados municipais e prestações | P2 | descoberta |
| Transferegov | parcerias, transferências especiais, pagamentos e execução | P3 | API atual, catálogo histórico, propostas municipais e recorte de emendas por ID implementados; os três autores individuais observados nos rankings federais de 2021-2026 estão ligados a perfis oficiais por crosswalk TSE aprovado; demais CSVs pendentes |
| Tesouro Transparente | transferências constitucionais/legais e emendas | P3 | documentação inicial |
| Transparência Bahia / SEPLAN-BA | transferências a municípios, despesas e emendas estaduais | P3 | ZIP de execução preservado e normalizado como agregado estadual; replay versionado confirmou 70 autorizações territoriais da LOA 2022-2026, sendo 34 em 2026; os 13 autores observados estão ligados a perfis oficiais por crosswalk TSE aprovado, sem confundir autoria histórica, legislatura e Casa atual |
| Câmara dos Deputados | mandatos, proposições, votações e despesas | P3 | API confirmada |
| Assembleia Legislativa da Bahia | parlamentares, comissões e proposições | P3 | API indicada; contrato a descobrir |
| TSE Dados Abertos | candidaturas, resultados e bens declarados | P4 | datasets confirmados |
| TSE Prestação de Contas | receitas, despesas e doadores por candidatura | P4 | dataset confirmado; minimização pendente |
| CGU/Portal da Transparência | CEIS, CNEP, CEPIM, CEAF, acordos e emendas | P4 | API confirmada; token necessário |
| Receita Federal — CNPJ aberto | empresas e QSA | P4 | download em lote; descoberta |
| IBAMA | autos de infração ambiental | bloqueada | fonte confirmada; gate reputacional |
| ANAC/RAB | aeronaves e dados cadastrais | bloqueada | dataset confirmado; finalidade/LGPD pendentes |
| SPU | imóveis da União em Barreiras | P4 | fonte territorial; não é patrimônio privado |
| CNJ/DataJud | metadados processuais sem partes no schema público | bloqueada | gate jurídico |

## Fontes para dívidas e obrigações municipais

O Portal da Transparência da Prefeitura publica `balancetes`,
`pdc-contas-anuais`, `rreo` e `rgf`. Esses recursos são preservados como
documentos-base para localizar empréstimos, precatórios, restos a pagar e
outros passivos.

Nenhum desses documentos, isoladamente, representa o total da dívida do
Município. A consolidação futura exigirá natureza da obrigação, competência,
saldo inicial e final, baixas, retificações e reconciliação com SICONFI e
prestações do TCM-BA. `pdc-relacao-de-divida-ativa` não entra nesse total:
dívida ativa é crédito a receber pelo Município, não obrigação a pagar.

As linhas extraídas desses documentos passam pelo contrato
`finance.public_obligations`. A projeção pública aceita somente estados
`validated` e `reconciled`, preserva período, versão, URL e SHA-256 da evidência
e não calcula dívida consolidada. Um documento preservado sem linha validada
continua visível como evidência em apuração, nunca como obrigação de valor zero.

No balancete mensal, o `Demonstrativo de Despesa Extra` informa os pagamentos
de restos a pagar em três valores: pago até o mês anterior, pago no mês e pago
até o mês atual. O publicador valida deterministicamente a identidade
`anterior + mês = acumulado`, mantém o vínculo com o PDF exato e rejeita a
linha se a seção for ambígua ou se a conta não fechar. Esses valores medem
pagamentos realizados e não o saldo ainda devido pelo Município.

Uma competência só pode aparecer publicamente como “não encontrada no catálogo
oficial” depois que o coletor percorre o catálogo completo de `balancetes`,
preserva todas as respostas HTTP usadas na busca e registra um manifesto
SHA-256 dos artefatos. A mensagem não significa valor zero, nem prova que o
documento nunca existiu: informa apenas que ele não constava no catálogo oficial
na data e hora verificadas. Paginação incompleta, limite atingido, falha de rede
ou campo temporal inválido mantêm a competência como cobertura desconhecida ou
falha; jamais produzem uma declaração pública de ausência.

Para que o inventário não espere a transferência de centenas de PDFs, a coleta
financeira executa duas etapas independentes e idempotentes. Primeiro preserva o
catálogo completo e registra a cobertura mensal. Depois drena até cinco PDFs de
balancetes por execução, retomando do checkpoint seguinte. Assim, um documento
grande ou lento não impede a atualização pública do estado da fonte.

## Catálogo oficial do Diário de Barreiras

- catálogo: `https://pmbarreiras.diariomtransparente.com.br/publicacoes`;
- publicação individual: `/publicacao?referencia=<id>`;
- o catálogo informa edição, título, resumo e data; esses campos não são
  inferidos do PDF;
- o HTML é preservado como `raw.raw_artifact` por SHA-256 e cada publicação
  como `barreiras_diario_publication`, permitindo corrigir a projeção sem
  alterar o histórico bruto;
- cada consulta diária ao catálogo abre uma execução controlada antes da
  autenticação e do HTTP. O retrato só atualiza a saúde da fonte depois que o
  HTML e todas as publicações validadas são preservados; falha de autenticação,
  rede ou persistência permanece registrada como falha, nunca como catálogo
  vazio;
- cada publicação do catálogo ainda sem documento preservado vira um alvo
  explícito de coleta. Uma numeração ausente não interrompe as edições
  posteriores conhecidas;
- o redirecionamento da publicação individual ao PDF só é seguido entre hosts
  oficiais em allowlist, com limite de tamanho, retries e validação `%PDF-`;
- o nome do arquivo não é inferido apenas pelo número: edições extras podem
  usar sufixos, como a edição 4.704 (`diario4704-edicaoextra.pdf`). Por isso, o
  coletor usa primeiro o link individual do catálogo e preserva a URL final do
  redirecionamento como evidência;
- PDF oficialmente anunciado mas indisponível é cobertura `partial`, nunca
  “período vazio”; a edição continua pendente para nova tentativa;
- falha temporária do catálogo não impede OCR, extração e publicação dos
  artefatos que já foram preservados, mas permanece visível como falha da
  execução;
- a fila de processamento prioriza as edições diretas mais recentes e depois
  continua drenando o acervo histórico; PDFs escaneados passam por extração,
  OCR e nova extração na mesma execução;
- se todas as APIs de IA estiverem sem cota, um fallback determinístico ainda
  publica explicações neutras de cabeçalhos oficiais reconhecidos (decretos,
  leis, portarias, avisos, editais, licitações e extratos), sempre com trecho
  literal; ele não calcula valores nem completa informações ausentes. O uso
  bem-sucedido desse caminho é registrado em `audit.assist_diagnostics` como
  `fallback_succeeded`, separado das tentativas dos provedores externos;
- o resumo da Prefeitura e a explicação assistida por IA são exibidos
  separadamente no portal.

## Querido Diário

- API base: `https://api.queridodiario.ok.org.br`;
- host atual de documentos observado: `https://data.queridodiario.ok.org.br`;
- registros históricos podem apontar para
  `s3://okbr-qd-migration//<território>/<data>/<arquivo>`; somente esse bucket,
  com o território `2903201` e caminho sem travessia, é convertido para o host
  HTTPS oficial. A URL S3 original permanece nos metadados derivados e na
  resposta JSON bruta imutável;
- outros hosts de artefato aceitos são cadastrados em allowlist, nunca
  derivados automaticamente da resposta;
- OpenAPI verificada em 30/07/2026: versão `0.19.0`;
- município: Barreiras/BA, `territory_id=2903201`;
- endpoint inicial: `GET /gazettes`;
- limite de cortesia documentado: referência de 60 requisições/minuto; o
  coletor usará 30/minuto por padrão;
- parâmetros temporais atuais: `published_since`, `published_until`,
  `scraped_since` e `scraped_until`;
- paginação: `size` + `offset`;
- ordenação incremental: data descendente ou ascendente conforme backfill;
- `querystring` vazio retorna metadados sem excertos.

Smoke test somente leitura executado em 30/07/2026: HTTP 200, território
`2903201` e contrato mínimo aceito. Testes automatizados continuam sem rede.

O spider oficial `ba_barreiras` declara série a partir de 02/01/2008 e fonte
`https://barreiras.ba.gov.br/diario-oficial`. Ele usa o código IBGE correto,
editions por ano e marca edições extras. Isso é referência de cobertura, não
garantia de ausência de lacunas.

### Estratégia de ingestão

1. Coletar metadados de todas as edições por janela de data, sem filtrar por
   palavras.
2. Preservar a resposta JSON bruta de cada página da API.
3. Baixar `url` e `txt_url` quando presentes, preservando cada conteúdo por
   hash.
4. Deduplicar por identidade da edição e por conteúdo, sem sobrescrever.
5. Só depois pesquisar/classificar atos de nomeação e exoneração.

Não usar apenas a consulta `nomeação|exoneração`: ela pode perder OCR imperfeito,
variações morfológicas e atos sem o termo esperado.

### Testes exigidos

- mudança de schema da resposta;
- múltiplas páginas e página vazia final;
- 429 com `Retry-After`;
- 5xx, timeout e conexão interrompida;
- item duplicado entre páginas;
- edição sem número, PDF ou texto;
- mesmo URL com hash diferente;
- retomada por cursor sem duplicação.

## PNCP

O fluxo começa por **órgãos/unidades vinculados a Barreiras**, não por busca de
fornecedor. A identidade do órgão é confirmada pelo CNPJ `13.654.405/0001-95`,
ano e sequencial oficiais; o nome “Barreiras” isolado não é chave confiável.

As APIs abertas permitem consultar contratações, atualizações globais, itens,
resultados e contratos/empenhos. O manual de integração de 2026 também inclui
histórico e empenhos associados. O coletor:

- mantém fixtures da versão documentada;
- mapeia número de controle PNCP, CNPJ, ano e sequencial;
- percorre todas as páginas por modalidade;
- preserva documentos e histórico de atualização;
- modela orçamento sigiloso sem interpretar valor zero como preço real;
- reconcilia fornecedor por CNPJ mascarado/ausente sem inventar identidade.

A API de consulta pode devolver `204` para uma modalidade e ficar indisponível
para outra na mesma janela. Nessa situação, as respostas válidas são preservadas,
a cobertura fica `partial`, e modalidades falhas ou adiadas permanecem no
checkpoint para nova tentativa. O cursor retroativo só avança por partições
`complete` ou `empty` associadas a uma execução controlada bem-sucedida; uma
resposta auxiliar isolada nunca prova cobertura do período inteiro.

Referências:

- [Dados abertos do PNCP](https://www.gov.br/pncp/pt-br/acesso-a-informacao/dados-abertos)
- [Swagger da API de consulta](https://pncp.gov.br/api/consulta/swagger-ui/index.html)
- [Manual de integração](https://pncp.gov.br/manual/pt-br/latest/singlehtml/)

## SICONFI

Usar o código IBGE `2903201` como chave do ente. A API documenta 5.000 itens por
página e limite de uma requisição por segundo. Valores precisam preservar:

- exercício, período, periodicidade, poder e anexo;
- conta/coluna exatamente como recebida;
- unidade e escala monetária;
- declaração original e eventual retificação.

Não reduzir o SICONFI diretamente a um indicador sem antes guardar as linhas que
o compõem.

Referência: [API SICONFI](https://apidatalake.tesouro.gov.br/docs/siconfi/)

## Transferências e emendas

Usar fontes complementares, sem somar estágios diferentes:

- Transferegov para parcerias, transferências especiais e respectivos eventos
  financeiros;
- Tesouro Transparente para transferências constitucionais/legais e conjuntos
  de emendas;
- Portal da Transparência/CGU para emendas e documentos de despesa;
- Transparência Bahia para recursos estaduais e transferências a municípios;
- API local da Prefeitura para receita e PDC de emendas/transferências.

Primeira projeção pública implementada: a API Gestão de Parcerias do
Transferegov fornece proposta, distribuição, autoria, beneficiário, objeto,
empenho, documento hábil, ordem de pagamento e ordem bancária. Ranking pessoal
e autoria coletiva permanecem separados. Ausência em um endpoint não é
publicada como zero. Metodologia completa em
`docs/PARLIAMENTARY_TRANSFERS_METHODOLOGY.md`.

Para reprocessamentos manuais sem acionar fontes independentes, o workflow
financeiro oferece o recurso `transferegov-only`. Nesse modo, somente o
catálogo, as propostas e os eventos do Transferegov são executados; os
coletores municipais e estaduais ficam suspensos. As execuções agendadas
continuam cobrindo todas as fontes normalmente.

A coleta de propostas é particionada por ano fiscal, de 2021 ao ano municipal
atual, usando simultaneamente `cd_ibge_recebedor=2903201` e `ano_proposta`.
Cada resposta é conferida contra os dois filtros antes de ser preservada. A
cobertura pública distingue `complete`, `empty`, `partial`, `failed`, `blocked`
e `unclassified`: um ano vazio confirmado na API de Parcerias não é publicado
como prova de ausência em outras bases oficiais.

Cada execução anual também mantém partições próprias para distribuições de
recursos, parcerias, empenhos, documentos hábeis e ordens de pagamento. Esses
subrecursos são fechados como `complete` ou `empty` somente depois que todas as
propostas e relações parentais daquele ano foram percorridas sem erro. Uma
falha em qualquer etapa deixa todas as partições ainda abertas como falha; o
painel não herda sucesso da proposta nem confunde recurso não consultado com
recurso oficialmente ausente. Ordens bancárias continuam como registros
derivados da resposta oficial de ordens de pagamento, sem partição fictícia.

### Downloads históricos de transferências discricionárias e legais

O ambiente oficial de downloads expõe uma enumeração XML completa em
`/downloads/dadosgov/?restype=container&comp=list`. Esse catálogo é outra
fonte lógica: não substitui a API atual de Gestão de Parcerias e sua cobertura
não pode ser misturada silenciosamente com ela.

O primeiro contrato monitora oito arquivos nacionais necessários ao rastro do
dinheiro: proposta, proponente, convênio, emenda, empenho, desembolso,
pagamento e termo aditivo. A resposta XML integral é preservada por SHA-256;
cada entrada guarda URL oficial, tamanho, `Last-Modified`, `ETag`, MD5 quando
publicado e tipo. Um arquivo ausente ou um `NextMarker` não consumido impede o
fechamento da cobertura como completa.

Os arquivos não são baixados pelo coletor de catálogo. Alguns ZIPs nacionais
observados em 12/08/2026 ultrapassam 300 MiB. Cada conjunto possui download
controlado, validação e filtragem territorial próprios; o ZIP nacional bruto
permanece privado e não é servido pelo portal.

O primeiro download controlado, `siconv_proposta.zip`, já está operacional. Seu arquivo nacional é
validado por tamanho, ETag, integridade ZIP e contrato CSV; a projeção aceita
somente `COD_MUNIC_IBGE=2903201` desde 2021 como conjunto candidato. Agência, conta, endereço, bairro e
CEP não integram o registro normalizado. A projeção pública também omite CNPJ e
expõe apenas campos necessários à compreensão da proposta e sua evidência. A
proposta não recebe autoria por aproximação de nome.

O código municipal do proponente, isoladamente, não prova que um projeto de
consórcio regional beneficia Barreiras. Por isso, o recorte público exige menção
explícita a Barreiras no objeto ou um destinatário local que não seja entidade
regional. Projetos de consórcio sem destino municipal comprovado permanecem no
bruto e no diagnóstico de cobertura, mas não entram em totais ou rankings.

O segundo download controlado, `siconv_emenda.zip`, é filtrado exclusivamente
pelos identificadores das propostas municipais já preservadas. O retrato
oficial de SHA-256 `f55c98d09538f733bf8b58d6c0f333e0a1da1af12891ef288a22eec5fa769f82`,
coletado e auditado em 13/08/2026, contém nove linhas candidatas ligadas a oito das
69 propostas cujo proponente foi registrado em Barreiras entre 2021 e 2026.
O recorte territorial estrito confirmou 62 propostas e três linhas de emenda;
sete propostas de consórcio e seis linhas de emenda ficaram fora dos totais por
não comprovarem destino em Barreiras. Uma proposta pode possuir
mais de uma emenda; as outras propostas permanecem como "sem emenda identificada
neste arquivo", nunca como autoria inexistente. O nome e o tipo de autoria são
mantidos como publicados pela fonte. CPF de beneficiário bloqueia a projeção;
CNPJ integral permanece somente no ZIP privado, e o registro normalizado guarda
apenas o tipo e os quatro últimos dígitos para diagnóstico.

A projeção pública histórica relaciona cada linha territorialmente confirmada à proposta, mostra autor,
tipo de autoria, valor destinado à proposta, objeto, fonte e hash. Pessoas e
comissões possuem rankings separados. Esta série não publica identificadores
do beneficiário. A API corrente e o arquivo histórico federal agora são
reconciliados pela chave
exata `id_proposta + numero_emenda`. Correspondências contam uma única vez.
Registros exclusivos de uma série são identificados como tal; divergências de
ano, autoria, tipo ou valor ficam preservadas, mas fora de totais e rankings. A
projeção pública mantém URL e SHA-256 de cada série, sem eleger uma fonte
vencedora global. Valor destinado não é apresentado como
empenho, pagamento ou execução.

Se tamanho ou ETag do catálogo e do proxy divergirem durante uma atualização,
a coleta falha de forma explícita e aguarda sincronização; uma versão anterior
não é silenciosamente tratada como o retrato atual.

### Emendas parlamentares estaduais da Bahia

O Portal de Dados Abertos da Bahia publica o conjunto **Emendas Parlamentares
Estaduais**, originado no FIPLAN/SEFAZ-BA, com atualização diária declarada. O
Portal Transparência Bahia mantém painéis separados de dados gerais e execução
orçamentária e financeira. A preservação bruta já possui fonte, endpoint,
parser e partições próprios; dados estaduais não são agregados silenciosamente
aos federais.

O catálogo também publica o
[diagrama oficial das relações entre as views](https://dados.ba.gov.br/dataset/1436b3e7-6594-4683-bfa5-b2e3a6c69e07/resource/f463ff7d-569c-4b48-b1d3-c80f017779df/download/emendas-parlamentares-relacionamento_views.png).
O coletor preserva o PNG como artefato imutável, com URL, data observada, MIME,
tamanho e SHA-256, e registra esse hash no checkpoint da execução. O diagrama
documenta ligações internas entre despesas, liquidações e pagamentos, mas não
oferece uma chave territorial de município.

Os anexos da LOA publicados pela SEPLAN-BA fornecem a chave territorial que o
ZIP diário não possui. O Anexo III cobre município e autor em 2022-2025; o
Anexo I de 2026 também publica município por emenda. Esses PDFs representam
autorização orçamentária e não comprovam empenho, liquidação ou pagamento.
Cada ano é preservado como documento privado, com URL exata, SHA-256 e partição
própria, antes da extração das linhas de Barreiras.

A extração determinística dos anexos 2022-2026 está implementada no worker de
documentos. Ela conserva autor, número, órgão, unidade, objeto, página, trecho
literal, hash da evidência e valor decimal autorizado. O processamento recusa
PDF parcial, hash divergente e mudança de formato; os resultados ficam internos
até o replay de produção ser conferido. A linha territorial precisa declarar
`Barreiras`: citar a cidade apenas no objeto não basta.

O replay operacional de 14/08/2026 indexou as 3.182 linhas do Anexo I de 2026
e confrontou as 34 autorizações de Barreiras com o retrato mais recente da
execução estadual. Dez chaves ocorreram exatamente uma vez nos dois lados.
Vinte e uma autorizações compartilharam a mesma chave com outra linha do anexo
e três não apareceram no retrato de execução. A projeção detalhada de diagnóstico
permanece privada. A API pública expõe valores executados somente para os dez
pares bidirecionalmente únicos e, nos outros 24 casos, publica apenas o motivo
do bloqueio. Colisão e ausência preservam valores nulos, nunca zero. O resumo
público separa o total autorizado nas 34 emendas dos totais de execução do
universo conciliado, para que o cidadão não compare bases diferentes.

O link oficial rotulado como Anexo III da LOA 2021 aponta para o arquivo de
2020. O período fica `blocked`, com a divergência documentada, em vez de receber
um documento do exercício errado. Ausência de valor ou documento será mostrada
como não encontrada na fonte consultada, nunca como zero.

Em 13/08/2026, o servidor `dados.ba.gov.br` apresentou o certificado atual
`Sectigo Public Server Authentication CA OV R36`, mas enviou intermediários de
uma cadeia anterior. O worker mantém a verificação TLS e acrescenta somente a
cadeia OV R36/R46 publicada pela Sectigo, versionada no repositório e conferida
por SHA-256 no workflow. Nenhum modo de TLS inseguro é permitido.

O contrato deverá manter autor, exercício, número, objeto, órgão executor,
beneficiário, município e cada estágio financeiro publicado. A filtragem de
Barreiras será validada contra os campos estruturados do arquivo antes de
qualquer total ou ranking.

Em 13/08/2026, a inspeção do recurso oficial confirmou um arquivo ZIP com
**cinco CSVs** de centralização/descentralização, despesas, liquidação,
pagamentos e processos SEI. Esses cinco arquivos não publicam coluna municipal
explícita nem código IBGE do destino. Por isso, esta primeira integração
preserva o catálogo CKAN e o ZIP integral, registra hash, tamanho, cabeçalhos e
quantidade de linhas, mas **não autoriza atribuição a Barreiras**. Busca textual
por objeto, beneficiário ou unidade não será usada como substituto de uma chave
territorial oficial.

O retrato SHA-256 `b34303a548f6bfc6596eaf5fa684bbee5a1ad749d9d4776962378493e2ae763b`,
verificado em 13/08/2026, contém aspas não escapadas, pontos e vírgulas e
quebras de linha no campo `Objeto` da view de pagamentos. O parser genérico de
CSV permanece estrito. Para essa view específica, a versão `1.2.0` delimita
cada registro somente pelos identificadores estruturados de pagamento,
empenho e execução publicados nas extremidades da linha lógica. O contrato
validou 20.687 pagamentos e 68.990 linhas nas cinco views. Em 32 pagamentos, a
própria fonte omitiu o dígito verificador dos identificadores; a lacuna é
registrada como `missing_check_digit_rows` e nenhum dígito é inferido. Essa
validação fecha a cobertura estrutural do ZIP, mas não normaliza valores, não
autoriza totais e não remove o bloqueio territorial de Barreiras.

Em 17/07/2026, o Transferegov anunciou novo ambiente de APIs e descontinuação do
ambiente anterior em 31/08/2026. O conector deverá apontar para o ambiente novo
e registrar versão do contrato.

Referências:

- [APIs públicas do Transferegov](https://api-publica.transferegov.gestao.gov.br/)
- [Downloads oficiais de dados abertos](https://api-publica.transferegov.gestao.gov.br/downloads)
- [Dados abertos do Transferegov](https://www.gov.br/transferegov/pt-br/ferramentas-gestao/dados-abertos)
- [Comunicado de migração de 2026](https://www.gov.br/obrasgov/pt-br/noticias/2026/comunicado-23-2026-mudancas-nos-acessos-as-apis-de-dados-abertos-do-transferegov-br-e-do-obrasgov-br)
- [Transferências no Tesouro Transparente](https://www.tesourotransparente.gov.br/temas/estados-e-municipios/transferencias-a-estados-e-municipios)
- [Informações de municípios — Transparência Bahia](https://www.transparencia.ba.gov.br/InformacaoMunicipio)
- [Emendas Parlamentares Estaduais — Dados Abertos Bahia](https://dados.ba.gov.br/pt_BR/dataset/emendas-parlamentares)
- [Histórico da LOA e anexos de emendas — SEPLAN-BA](https://www.ba.gov.br/seplan/orcamento/historico-de-loa)
- [Mapa dos painéis de emendas — Transparência Bahia](https://www.transparencia.ba.gov.br/MapaSite/)

## Representação legislativa e eleições

A Câmara dos Deputados possui API REST e downloads oficiais para deputados,
despesas, órgãos, proposições, eventos e votações. A ALBA informa uma API de
parlamentares, comissões, normas, proposições e trâmites; endpoints e condições
ainda precisam de inventário.

O TSE fornece datasets por eleição, inclusive candidaturas e bens declarados.
Em 31/07/2026, o conjunto oficial “Candidatos - 2026” informa frequência diária
e contém recursos separados para candidaturas, informações complementares, bens,
coligações, vagas, motivos de cassação e redes sociais. Cada situação exibida
deve trazer o instante da coleta; anúncio partidário não substitui registro
oficial.

O recurso oficial `consulta_cand_<ano>.zip` é a fonte inicial do identificador
forte privado. O processador lê somente o arquivo da Bahia e somente os
`SQ_CANDIDATO` já vinculados por crosswalk aprovado. CPF e a linha integral da
fonte são cifrados antes da persistência; a projeção redigida conserva apenas
ano, cargo, sequencial, nomes e UF. O arquivo nunca alimenta busca pública por
CPF e não autoriza, sozinho, conclusão editorial ou reputacional.

Cada declaração será vinculada à eleição e candidatura; não será tratada como
patrimônio atual.

O controle operacional mantém partições distintas para composição da Câmara
Federal, vereadores da legislatura atual, Executivo municipal, listagem da ALBA,
perfis estaduais e cada ano eleitoral do TSE. Uma fonte indisponível ou arquivo
ainda não publicado não é apresentado como zero representantes. Na API da
Câmara Municipal, `leis` e `indicacoes` alimentam endpoints de cobertura
separados para que uma coleção saudável não esconda o atraso da outra.

O workflow de representação permite retry manual por fonte. Essa seleção reduz
requisições e tempo de recuperação quando, por exemplo, apenas o HTML da ALBA
fica temporariamente indisponível. As tentativas anteriores permanecem no
controle de cobertura e nos logs; executar novamente somente `state` não altera
o estado nem a data das fontes federais, municipais, eleitorais ou do Executivo.

A prestação de contas eleitoral disponibiliza receitas e despesas de campanha.
Doadores devem ser ligados pelo identificador da candidatura, nunca apenas por
nome+UF. CPF, endereço, conta e outros dados de pessoa natural não entram na
projeção pública sem análise específica de necessidade. O projeto utilizará o
download oficial; não implementará “bypass de WAF”.

Referências:

- [API da Câmara dos Deputados](https://dadosabertos.camara.leg.br/swagger/api.html)
- [Dados abertos da ALBA](https://www.al.ba.gov.br/transparencia/avisos2)
- [Candidatos e bens — TSE](https://dadosabertos.tse.jus.br/group/candidatos)
- [Candidatos — 2026](https://dadosabertos.tse.jus.br/dataset/candidatos-2026)
- [Prestação de contas eleitoral — TSE](https://dadosabertos.tse.jus.br/group/prestacao-de-contas-eleitorais)

## Registros administrativos e patrimônio público federal

O IBAMA publica dados e consulta de autos de infração ambiental. Auto é ato
administrativo sujeito a defesa, recurso, alteração e eventual cancelamento;
não equivale automaticamente a decisão judicial ou condenação definitiva.
Vínculo com perfil pessoal fica bloqueado até definir identificador, situação,
histórico, minimização e revisão.

O Registro Aeronáutico Brasileiro da ANAC possui arquivos abertos e consultas
oficiais. A existência técnica da fonte não demonstra, por si, necessidade ou
proporcionalidade para perfil político. O conector pessoal fica bloqueado até
avaliação de impacto, finalidade pública, campos permitidos, identidade exata e
política de publicação.

Os dados da SPU descrevem imóveis **da União** e podem alimentar o mapa de
presença federal em Barreiras. Eles não provam propriedade particular de agente
político e não integrarão a seção de bens pessoais.

Referências:

- [Consulta e dados de autos — IBAMA](https://www.gov.br/ibama/pt-br/servicos/consultas/autuacoes-e-embargos/autos-de-infracao-ambiental/tutorial-de-pesquisa-de-autos-de-infracao)
- [Dados abertos do RAB — ANAC](https://www.gov.br/anac/pt-br/acesso-a-informacao/dados-abertos/areas-de-atuacao/aeronaves-1/registro-aeronautico-brasileiro)
- [Transparência ativa e dados abertos — SPU](https://www.gov.br/gestao/pt-br/assuntos/patrimonio-da-uniao/perguntas-frequentes-spu/transparencia-ativa-e-dados-abertos-1)

## Sanções e vínculos societários

A API do Portal da Transparência/CGU oferece CEIS, CNEP, CEPIM, CEAF e acordos
de leniência. O consumo requer token por e-mail e respeita limites por horário.
Consultas volumosas devem preferir downloads de dados abertos.

O CNPJ aberto da Receita Federal contém estabelecimentos, empresas e QSA em
arquivos de lote. A API de consulta CNPJ do Conecta gov.br não deve ser
presumida pública para este projeto: a documentação a destina a órgãos e
entidades federais habilitados.

Referências:

- [API do Portal da Transparência](https://portaldatransparencia.gov.br/api-de-dados/)
- [Dados abertos do CNPJ](https://www.gov.br/receitafederal/pt-br/acesso-a-informacao/dados-abertos/cadastros)
- [Metadados do CNPJ](https://www.gov.br/receitafederal/dados/cnpj-metadados.pdf)

## DataJud

A API Pública do DataJud disponibiliza metadados de processos públicos. O
glossário documenta número, classe, assuntos, órgão julgador e movimentos, mas
não partes, nomes ou CPF/CNPJ. Logo, não implementa busca confiável por pessoa.

O termo de uso versão 1.2 limita tratamento de dados pessoais, atribui ao
usuário a responsabilidade pela interpretação, limita a 120 requisições por
minuto sem autorização e exige ciência ao CNJ sobre material derivado divulgado
publicamente. A fonte fica bloqueada para perfis de pessoas até revisão jurídica
qualificada e esclarecimento formal do CNJ.

Referências:

- [API Pública do DataJud](https://datajud-wiki.cnj.jus.br/api-publica/)
- [Glossário público](https://datajud-wiki.cnj.jus.br/api-publica/glossario/)
- [Termo de uso v1.2](https://formularios.cnj.jus.br/wp-content/uploads/2023/11/Termos-de-uso-api-publica-V1.2.pdf)

## Portais locais e TCM-BA

Os dois portais locais possuem APIs oficiais verificadas em 30/07/2026:

- Prefeitura: 51 recursos em
  `https://portaldatransparencia.barreiras.ba.gov.br/api`;
- Câmara: 28 recursos em
  `https://portaldatransparencia.cmbarreiras.ba.gov.br/api`.

Ambas usam `resource`, `limit` e `offset`, mas `count` representa apenas as
linhas da página. Recurso inválido também responde HTTP 200 com JSON de erro.
Datas e valores foram observados como strings; documentação e resposta real já
divergem em alguns campos.

Inventários:

- `docs/sources/PREFEITURA_TRANSPARENCIA_API.md`;
- `docs/sources/CAMARA_TRANSPARENCIA_API.md`.

O TCM-BA e partes não cobertas dos portais permanecem em descoberta. A tarefa do
`source-researcher` será produzir, sem alterar código:

1. inventário de URLs e exportações;
2. identificação do fornecedor do portal;
3. captura de requisições de rede e paginação;
4. períodos cobertos;
5. termos, robots, autenticação e rate limit;
6. amostras sanitizadas;
7. divergências com PNCP/SICONFI/Diário;
8. recomendação de coletor API/download antes de spider HTML.

### Universo privado do Anexo I da LOA 2026

O Anexo I de 2026 possui 374 páginas. A validação integral realizada em
14/08/2026 reconheceu 3.182 linhas estruturadas de 63 autores e manteve as 27
linhas territoriais de Barreiras em uma projeção separada. O universo estadual
fica privado e sem valores ou municípios de terceiros; sua finalidade única é
provar se a combinação autor, órgão, unidade e ação é realmente exclusiva antes
de associar empenho, liquidação ou pagamento a Barreiras.

## Hierarquia em conflitos

Não haverá uma “fonte vencedora” global. Preferência é definida por campo e
finalidade. Divergências permanecem em `source_conflicts`, com as duas
evidências, estado de revisão e resolução versionada.
