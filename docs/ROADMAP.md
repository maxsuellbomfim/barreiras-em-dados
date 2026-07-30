# Roadmap

## Regra de progressão

Uma fase só termina quando testes, segurança, qualidade de dados, documentação,
limitações e recuperação de falhas estiverem estáveis. “Código escrito” não é
critério de saída.

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
6. exibir apenas status interno da coleta.

Gate:

- replay produz os mesmos registros sem duplicar;
- modo local é restrito a desenvolvimento/teste e detecta adulteração;
- 429/5xx/timeout/circuit breaker/DLQ testados;
- lacunas e última coleta visíveis;
- restauração de um artefato por hash comprovada;
- antes de staging, bucket privado, grants e backup do provedor são revisados.

## Etapa 1B — Documento e extração candidata

- páginas e texto canônico;
- identificação determinística de candidatos;
- extração de nomeação/exoneração;
- pessoa, cargo, órgão, data e vigência com incerteza por campo;
- amostra anotada e métricas;
- fila de revisão.

Gate:

- precisão/revocação mínimas definidas com especialista;
- nenhum candidato publicado;
- trecho e offsets reproduzíveis;
- PDFs hostis e OCR falho tratados.

## Etapa 1C — Revisão e publicação

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

Gate:

- unidade/escala contábil verificadas;
- totais reconciliáveis e determinísticos;
- períodos e retificações preservados;
- explicações populares revisadas por especialista.

## Etapa 4 — RH, concursos, diárias e obras

Entradas independentes, cada uma com política de minimização e gate próprio.
Folha não será simplesmente importada e publicada integralmente.

## Etapa 5 — Anomalias

Ativar apenas regras operacionais de baixo risco. Regras financeiras ou
reputacionais exigem amostra anotada, especialista, revisão legal/editorial e
ADR adicional.

## Backlog deliberadamente adiado

- busca semântica/embeddings;
- chatbot;
- grafo societário;
- ML complexo;
- múltiplos municípios;
- broker externo;
- microsserviços por domínio.
