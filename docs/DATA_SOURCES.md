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
