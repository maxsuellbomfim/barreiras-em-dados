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
| Transparência Bahia / SEPLAN-BA | transferências a municípios, despesas e emendas estaduais | P3 | ZIP de execução preservado e normalizado como agregado estadual; replay versionado confirmou 70 autorizações territoriais da LOA 2022-2026, sendo 34 em 2026; o conjunto oficial Transferências Especiais possui conector privado com cinco views e 12.169 registros estruturais validados; três pagamentos cujo objeto menciona Barreiras possuem projeção pública minimizada e autoria ligada somente pelo código oficial 4072, período 2019-2023 e perfil institucional; os 13 autores observados na LOA estão ligados a perfis oficiais por crosswalk TSE aprovado, sem confundir autoria histórica, legislatura e Casa atual |
| Câmara dos Deputados | mandatos, proposições, votações e despesas | P3 | API confirmada |
| Assembleia Legislativa da Bahia | parlamentares, comissões e proposições | P3 | API indicada; contrato a descobrir |
| TSE Dados Abertos | candidaturas, resultados e bens declarados | P4 | datasets confirmados |
| TSE Prestação de Contas | receitas, despesas e doadores por candidatura | P4 | dataset confirmado; minimização pendente |
| CGU/Portal da Transparência | CEIS, CNEP, CEPIM, CEAF, acordos e emendas | P3 | ZIP nacional de execução de emendas implementado sem token; APIs de sanções continuam dependentes de chave |
| Receita Federal — CNPJ aberto | empresas e QSA | P4 | download em lote; descoberta |
| IBAMA | autos de infração ambiental | bloqueada | fonte confirmada; gate reputacional |
| ANAC/RAB | aeronaves e dados cadastrais | bloqueada | dataset confirmado; finalidade/LGPD pendentes |
| SPU | imóveis da União em Barreiras | P4 | fonte territorial; não é patrimônio privado |

O diagnóstico público estadual separa o anexo orçamentário da execução. O
catálogo oficial lista o Anexo III de 2021, mas o endereço correspondente entrega
o PDF da LOA 2020; a partição segue bloqueada e nenhum valor é reaproveitado.
Os anexos 2022-2026 estão preservados. A execução territorial é parcial em 2026
e ainda não indexada para 2022-2025, estados que não podem ser exibidos como
valor zero.
| CNJ/DataJud | metadados processuais sem partes no schema público | bloqueada | gate jurídico |

## Fontes para dívidas e obrigações municipais

O Portal da Transparência da Prefeitura publica `balancetes`,
`pdc-contas-anuais`, `rreo` e `rgf`. Esses recursos são preservados como
documentos-base para localizar empréstimos, precatórios, restos a pagar e
outros passivos.

### Recursos municipais verificados em 18/08/2026

Sondas com o contrato exato do coletor (`resource`/`count`/`data`) confirmaram
quatro recursos adicionais no portal da Prefeitura:

- `pdc-convenios-transferencias-realizadas` e `pdc-obras-pdc` têm o mesmo
  formato de catálogo documental dos demais `pdc-*` (título, período, URL do
  PDF) e **entraram na coleta diária e no catálogo público**
  (`public-finance-documents/1.5.0`). O acervo de obras mistura, na própria
  fonte, documentos de outros temas (ex.: convocações de processo seletivo);
  o título literal é preservado sem reclassificação.
- `contratos` retorna linhas estruturadas por contrato: favorecido, CNPJ,
  `valor_contrato` como texto (`"R$ 105.460,50"`), número, objeto, vigência e
  URL do PDF — **implementado em 18/08/2026** com gate de CPF em três
  camadas. `processos` retorna processos licitatórios com objeto, datas,
  valores como texto (`"14237586.12"`) e códigos numéricos —
  **implementado em 19/08/2026**: linhas mutáveis na fonte (a situação
  avança), então a projeção pública deduplica pelo `id` estável e entrega o
  estado mais recente preservado. Situação e resultado não têm legenda
  publicada pela fonte e saem como código literal; modalidade e categoria
  usam a legenda capturada em 19/08/2026 do filtro público do próprio portal
  (17 modalidades, 9 categorias), versionada na camada web e sempre exibida
  com o código ao lado. Valores monetários seguem como texto e não são
  convertidos sem regra determinística versionada.
- `servidores` não é uma API de linhas salariais, mas um catálogo de 200 PDFs
  observado em 21/08/2026, com competências de 2018 a 2026 e relações separadas
  de servidores, estagiários e terceirizados. O catálogo e os PDFs entram na
  preservação privada e idempotente em lotes de até cinco e orçamento agregado
  suave de 64 MiB por execução; nenhum nome, desconto ou valor individual é
  projetado publicamente antes do gate de minimização do ADR 0072. O dreno pode
  ser dirigido por `ano_ref`, `mes_ref` e `tipo` oficiais; para a folha mensal,
  `tipo=1` só é aceito em conjunto com um título oficial de folha de servidores.
  Essa validação dupla é necessária porque a fonte já classificou uma
  `Relação de Estagiários` como `tipo=1`. Registros históricos em que a própria
  fonte omitiu `tipo` só entram quando o título normalizado é exatamente
  `Relação de Servidores`; tanto campo vazio quanto `null` significam tipo não
  informado e passam pelo mesmo gate estrito de título. Relações de estagiários
  e terceirizados continuam
  excluídas mesmo com tipo incorreto; ocorrências antigas já publicadas são
  invalidadas de forma append-only, sem apagar o artefato ou o agregado. Título
  ausente permanece bloqueado por falta de evidência, nunca é presumido. O primeiro
  PDF pode ultrapassar sozinho o teto para impedir inanição da fila; o restante
  é adiado com cobertura `partial`, nunca descartado silenciosamente.
  No recorte observado em 21/08/2026, o catálogo não apresentou uma
  `Relação de Servidores` para abril de 2024. Havia somente relações de
  estagiários e terceirizados, incluindo um documento de terceirizados
  classificado pela fonte como `tipo=1`. O backfill registra essa competência
  como documento regular não localizado e continua os demais meses; não
  publica zero nem usa outro grupo de pessoal como substituto.
  Em amostra `tipo=1` de julho/2026, 133 subtotais do PDF fecharam exatamente
  com o total geral de quantidade, proventos, descontos e líquido. O parser
  agregado não conserva nenhum campo individual; detalhes e hash estão em
  `docs/reviews/STAGE_4_PAYROLL_LAYOUT_REVIEW.md`. A projeção pública mensal
  definida no ADR 0073 retorna somente esses quatro totais, a quantidade de
  subtotais, a fonte, o hash e a versão do parser. Registros `tipo=3` e `tipo=4`
  permanecem fora dessa projeção. O workflow financeiro possui escopo isolado
  `payroll` e seletor opcional `AAAA-MM`; uma falha de leiaute ou integridade é
  registrada para revisão e não bloqueia nem altera as demais competências.
  A seleção operacional de PDFs pendentes e a contagem de uma competência são
  feitas pelas funções privadas do ADR 0075. Elas evitam que as políticas RLS
  da role técnica transformem uma junção válida em fila vazia e falham
  explicitamente quando limite, período ou competência são inválidos. A role
  compartilhada mantém a leitura bruta já necessária aos coletores; o frontend
  não recebe acesso às tabelas nem a essas funções. A leitura pública do
  histórico usa `api.get_public_payroll_months_page`, com até 24 competências
  por chamada e cursor mensal exclusivo. O cursor impede que a ampliação do
  acervo oculte meses antigos e preserva todos os órgãos eventualmente
  publicados na mesma competência; não há paginação profunda por `OFFSET`.
  A cobertura pública usa `api.get_public_payroll_coverage`: ela só declara
  ausência depois de localizar uma partição completa do catálogo oficial e
  distingue `published`, `document_not_found`, `source_conflict` e
  `processing_pending`. O diagnóstico retorna apenas competência, contagens,
  URL HTTPS, hash quando existe PDF preservado, data da conferência e versão da
  metodologia. “Documento não localizado” nunca é convertido em valor zero.
  Múltiplas versões preservadas do mesmo item do catálogo contam como um único
  documento esperado, embora todas permaneçam no acervo bruto append-only.
  Para documentos que trazem a coluna `Regime/Vínculo`, o parser
  `payroll-regime-breakdown/1.0.0` percorre todas as linhas, valida a aritmética
  e exige que os oito grupos permitidos fechem exatamente com o agregado do
  componente. A projeção pública `api.get_public_payroll_regime_breakdown`
  retorna somente competência, código e rótulo do grupo, quantidade, proventos,
  descontos, líquido, quantidade de PDFs e versão metodológica. Nome, CPF,
  matrícula, cargo, lotação e valor individual não atravessam esse contrato.
  Leiaute sem essa coluna significa detalhamento indisponível, não valor zero.
  A distribuição `payroll-compensation-bands/1.0.0` usa somente a folha regular
  e publica seis faixas fixas de provento bruto, contagens, média e maior bruto
  em `api.get_public_payroll_compensation_distribution`. Todas as linhas precisam
  fechar com o total do PDF; 13º e outros componentes não entram nas faixas.
  Nome, matrícula, CPF, cargo, lotação, desconto e líquido individual são
  descartados antes da persistência.

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

### Unidades orçamentárias nos demonstrativos de despesa

O recurso oficial `pdc-resumo-execucao-da-despesa` apresentou 55 PDFs no
catálogo observado em 23/08/2026, cobrindo 2022 a 2026. O catálogo não trouxe
documento de 2021; essa lacuna continua declarada e não é estimada. Auditoria
integral de três layouts confirmou que o cabeçalho de unidade precede as linhas
contábeis: 25 unidades em dezembro/2022, 27 em dezembro/2024 e 29 em julho/2026,
com 1.979, 1.549 e 1.982 linhas de despesa, respectivamente.

O parser `public-expense-pdf/1.4.0` exige um cabeçalho literal de seis a oito
dígitos antes de aceitar cada linha. Ele também reconhece o layout histórico em
que `Fonte` e `Fonte TC` são extraídas sem espaço (`1500` + `1001` aparece como
`15001001`), preservando o token combinado sem inventar uma separação. Nenhum
relatório é validado se os subtotais não cobrirem exatamente as unidades das
linhas. Diferenças de até R$ 0,10, somadas em valor absoluto no documento, são
aceitas apenas como conflito explícito da fonte; acima disso, a publicação é
bloqueada. O mesmo tratamento preserva diferenças entre as linhas e o `Total`
geral impresso. O portal informa escopo, unidade, dois valores, diferença e
documento; não corrige nem estima o balancete da Prefeitura.

A projeção pública só agrega uma competência quando todas as linhas possuem
atribuição e a soma paga coincide exatamente com o total do PDF. Códigos podem
mudar entre exercícios; por isso a visão anual não usa uma lista fixa de
secretarias e nunca transporta a estrutura de um ano para outro. Correções do
parser criam nova versão ligada por `supersedes_id`; a versão anterior permanece
preservada para auditoria.

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

Contrato verificado em 24/08/2026: `GET /ords/siconfi/tt/dca`, com
`an_exercicio=2021` e `id_ente=2903201`, retornou 1.109 linhas em sete anexos
da DCA da Prefeitura Municipal de Barreiras. O coletor preserva cada resposta
JSON por SHA-256, valida paginação, ente, exercício, esquema e identidade
completa da linha, e mantém `valor` como texto decimal. Valor negativo publicado
pela fonte é preservado; não é descartado nem interpretado como erro.

O backfill operacional de 24/08/2026 preservou 5.986 linhas dos exercícios de
2021 a 2025. A consulta de 2026 respondeu HTTP 200 com zero linhas e também foi
preservada; por isso sua partição é `empty`, não `failed` nem um valor financeiro
zero. A cobertura é registrada separadamente por exercício, permitindo que uma
falha anual não apague o resultado dos demais anos e que o painel diferencie
ano completo de ano consultado sem DCA publicada.

A DCA é anual. Ela serve para fechar e reconciliar contas do exercício, mas não
substitui a série mensal nem o detalhamento de empenhos, liquidações e pagamentos
do portal municipal. Em 24/08/2026, a exportação JSON do módulo legado de
despesas municipais para 2021 respondeu erro interno de coluna; essa partição
mensal permanece `blocked`, nunca `empty` e nunca é preenchida por estimativa.
O primeiro corte público anual materializa somente sete linhas literais do
SICONFI: receita bruta realizada, dedução do Fundeb, despesa empenhada,
liquidada e paga, e inscrições de restos a pagar processados e não processados.
A seleção exige igualdade exata de anexo, rótulo, coluna, código e nome da conta;
uma ausência ou duplicidade bloqueia o exercício inteiro. Cada total é
versionado, imutável e vinculado ao registro bruto, ao artefato, ao hash e a um
item de evidência. A projeção pública não calcula receita líquida, saldo,
superávit ou déficit. Esses indicadores continuam dependentes de reconciliação
contábil e da comparação com a série mensal.

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

O ranking por legislatura também expõe a situação anual da fonte. Ele separa
ano com registro, partição oficialmente vazia, coleta incompleta, fonte
bloqueada, documento coletado ainda sem linha validada e ano não coletado. Essa
classificação explica a lacuna operacional; nenhuma dessas categorias autoriza
publicar “R$ 0” como contribuição parlamentar.

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

### Execução federal regionalizada da CGU

O Portal da Transparência publica um ZIP nacional de emendas parlamentares
que não exige a chave da API. O coletor preserva o arquivo integral, valida
host final, caminho, `Content-Length`, `ETag`, `Last-Modified`, membros e
cabeçalhos, e materializa somente as linhas cujo `Código Município IBGE` seja
exatamente `2903201`. O bruto nacional continua privado.

O recorte observado em 16/08/2026 encontrou 15 linhas territoriais, entre 2014
e 2023. Sete pertencem a Carlos Tito e incluem a emenda `202340720005`, de
2023. O código nunca soma empenhado, liquidado e pago como se fossem valores
aditivos. `Pago no exercício`, `restos a pagar pagos` e `restos a pagar
cancelados` permanecem separados; um total efetivamente pago só pode ser
calculado deterministicamente como pago no exercício mais restos a pagar pagos.

O município nessa fonte indica localização da execução orçamentária. Não
prova, isoladamente, repasse direto à Prefeitura, conclusão do objeto ou
regularidade. Anos posteriores a 2023 ausentes no retrato observado ficam
marcados como não encontrados nessa fonte, nunca como valor zero.

Para superar essa lacuna sem fabricar continuidade na série agregada, o
Barreiras 360 também preserva os arquivos anuais **Emendas Parlamentares por
Documento**, desde 2021 até o exercício corrente. Essa segunda série registra
cada empenho, liquidação ou pagamento publicado pela CGU, com data, documento,
autor, favorecido, órgão, ação e código IBGE do local da aplicação. A seleção
territorial continua exigindo `Código Município IBGE = 2903201`.

As duas séries permanecem independentes. Valores da série agregada não são
somados aos documentos, porque representam visões sobre a mesma execução e
poderiam gerar dupla contagem. Na série documental, linhas exatamente
duplicadas são descartadas, mas parcelas distintas do mesmo documento são
preservadas e somadas por código determinístico no estágio correspondente. O
ano do documento fica separado do ano da emenda: um pagamento de 2025 pode se
referir a uma emenda de exercício anterior.

Referências:

- [Download de emendas parlamentares](https://portaldatransparencia.gov.br/download-de-dados/emendas-parlamentares)
- [Download de emendas por documento](https://portaldatransparencia.gov.br/download-de-dados/emendas-parlamentares-documentos)
- [Consulta de emendas por documento](https://portaldatransparencia.gov.br/emendas/consulta-por-documento)
- [Dicionário de dados de emendas](https://portaldatransparencia.gov.br/dicionario-de-dados/emendas-parlamentares)

### Emendas parlamentares estaduais da Bahia

O Portal de Dados Abertos da Bahia publica o conjunto **Emendas Parlamentares
Estaduais**, originado no FIPLAN/SEFAZ-BA, com atualização diária declarada. O
Portal Transparência Bahia mantém painéis separados de dados gerais e execução
orçamentária e financeira. A preservação bruta já possui fonte, endpoint,
parser e partições próprios; dados estaduais não são agregados silenciosamente
aos federais.

A projeção pública de cobertura do arquivo estadual expõe somente exercício,
quantidade de linhas, quantidade de autores distintos, URL, data e hash do
snapshot. Como o arquivo não contém município nem número individual da emenda,
ela registra `territorial_key_unavailable_in_source` e não publica total
financeiro municipal. A ausência de um ano nessa projeção significa que o
snapshot não comprovou aquele período — não significa execução zero.

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

Em 17/07/2026, o Transferegov anunciou novo ambiente de APIs e descontinuação
do ambiente anterior em 31/08/2026. **Resolvido em 18/08/2026**: o Comunicado
23/2026 confirma que o ambiente que permanece é exatamente
`api-publica.transferegov.gestao.gov.br` — o único que este repositório usa
nos quatro conectores (parcerias, catálogo e arquivos históricos). Os hosts
descontinuados (`repositorio.dados.gov.br/seges/detru`,
`docs.api.transferegov.gestao.gov.br`, `api.obrasgov.gestao.gov.br`) nunca
foram referenciados. Verificação: sondas HTTP 200 na API de parcerias com a
query real, no catálogo Azure (`restype=container&comp=list`) e no ZIP
histórico, além de execução completa do workflow em produção no mesmo dia.
O contrato verificado ficou registrado no config dos endpoints
(migration `record_transferegov_environment`).

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
de leniência. O consumo desses endpoints requer token por e-mail e respeita
limites por horário. Isso não se aplica ao ZIP público de emendas usado pela
coleta em lote. Consultas volumosas devem preferir downloads de dados abertos.

**CEIS e CNEP implementados em 18/08/2026**: o coletor `collect_cgu_sanctions`
consulta os dois cadastros **somente por CNPJ de fornecedor já publicado**
(união dos resultados PNCP e dos contratos municipais), autenticado pelo
secret `TRANSPARENCIA_API_KEY` no GitHub Actions, com intervalo de 1,2s entre
requisições. A API expõe CPF integral em `sancionado.codigoFormatado` para
pessoas físicas; por isso o parser descarta pessoa física antes de
materializar, a projeção pública (`api.get_public_supplier_sanctions`) exige
documento de 14 dígitos e o cliente web invalida o lote se qualquer documento
fora do CNPJ chegar. O painel público enquadra o resultado como espelho do
cadastro na data da consulta — sanções podem estar sub judice e nada é
afirmado como culpa.

**CEPIM e acordos de leniência implementados em 19/08/2026** no mesmo
coletor e corredor (`cgu/sancoes/`): CEPIM via `cnpjSancionado` (o DTO expõe
`cpfFormatado`; o mesmo gate de pessoa física se aplica) e
`acordos-leniencia` via `cnpjSancionado`, materializando o acordo apenas
para a empresa cujo CNPJ foi consultado. **CEAF permanece fora por
definição**: é cadastro de pessoas físicas expulsas consultado por CPF, o
que o gate de dados pessoais do projeto veda.

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
