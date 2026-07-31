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
| Diário Oficial da Prefeitura | PDF original e metadados | P0 | via QD; origem direta a validar |
| Transparência da Prefeitura | contratos, processos, documentos, RH, fiscal e PDC | P1 | API catalogada |
| Transparência da Câmara | contratos, documentos, RH, atos e atividade legislativa | P1 | API catalogada |
| PNCP | contratações, itens, resultados, contratos, documentos | P1 | documentação inicial |
| SICONFI | demonstrativos contábeis e fiscais | P2 | documentação inicial |
| TCM-BA | dados municipais e prestações | P2 | descoberta |
| Transferegov | parcerias, transferências especiais, pagamentos e execução | P3 | documentação inicial |
| Tesouro Transparente | transferências constitucionais/legais e emendas | P3 | documentação inicial |
| Transparência Bahia | transferências a municípios, despesas e emendas estaduais | P3 | descoberta inicial |
| Câmara dos Deputados | mandatos, proposições, votações e despesas | P3 | API confirmada |
| Assembleia Legislativa da Bahia | parlamentares, comissões e proposições | P3 | API indicada; contrato a descobrir |
| TSE Dados Abertos | candidaturas, resultados e bens declarados | P4 | datasets confirmados |
| CGU/Portal da Transparência | CEIS, CNEP, CEPIM, CEAF, acordos e emendas | P4 | API confirmada; token necessário |
| Receita Federal — CNPJ aberto | empresas e QSA | P4 | download em lote; descoberta |
| CNJ/DataJud | metadados processuais sem partes no schema público | bloqueada | gate jurídico |

## Querido Diário

- API base: `https://api.queridodiario.ok.org.br`;
- host atual de documentos observado: `https://data.queridodiario.ok.org.br`;
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

O fluxo futuro deve começar por **órgãos/unidades vinculados a Barreiras**, não
por busca de fornecedor. A identidade do órgão será confirmada por CNPJ e
unidade; o nome “Barreiras” isolado não é chave confiável.

As APIs abertas permitem consultar contratações, atualizações globais, itens,
resultados e contratos/empenhos. O manual de integração de 2026 também inclui
histórico e empenhos associados. Antes de implementar:

- congelar fixtures da versão documentada;
- mapear número de controle PNCP, CNPJ, ano e sequencial;
- implementar todas as páginas;
- preservar documentos e histórico de atualização;
- modelar orçamento sigiloso sem interpretar valor zero como preço real;
- reconciliar fornecedor por CNPJ mascarado/ausente sem inventar identidade.

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

Em 17/07/2026, o Transferegov anunciou novo ambiente de APIs e descontinuação do
ambiente anterior em 31/08/2026. O conector deverá apontar para o ambiente novo
e registrar versão do contrato.

Referências:

- [APIs públicas do Transferegov](https://api-publica.transferegov.gestao.gov.br/)
- [Comunicado de migração de 2026](https://www.gov.br/obrasgov/pt-br/noticias/2026/comunicado-23-2026-mudancas-nos-acessos-as-apis-de-dados-abertos-do-transferegov-br-e-do-obrasgov-br)
- [Transferências no Tesouro Transparente](https://www.tesourotransparente.gov.br/temas/estados-e-municipios/transferencias-a-estados-e-municipios)
- [Informações de municípios — Transparência Bahia](https://www.transparencia.ba.gov.br/InformacaoMunicipio)

## Representação legislativa e eleições

A Câmara dos Deputados possui API REST e downloads oficiais para deputados,
despesas, órgãos, proposições, eventos e votações. A ALBA informa uma API de
parlamentares, comissões, normas, proposições e trâmites; endpoints e condições
ainda precisam de inventário.

O TSE fornece datasets por eleição, inclusive candidaturas e bens declarados.
Cada declaração será vinculada à eleição e candidatura; não será tratada como
patrimônio atual.

Referências:

- [API da Câmara dos Deputados](https://dadosabertos.camara.leg.br/swagger/api.html)
- [Dados abertos da ALBA](https://www.al.ba.gov.br/transparencia/avisos2)
- [Candidatos e bens — TSE](https://dadosabertos.tse.jus.br/group/candidatos)

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

## Hierarquia em conflitos

Não haverá uma “fonte vencedora” global. Preferência é definida por campo e
finalidade. Divergências permanecem em `source_conflicts`, com as duas
evidências, estado de revisão e resolução versionada.
