# API do Portal da Transparência da Câmara

- Observada em: 30/07/2026
- Publicador: Câmara Municipal de Barreiras
- Catálogo: <https://portaldatransparencia.cmbarreiras.ba.gov.br/dados-abertos/>
- API: `https://portaldatransparencia.cmbarreiras.ba.gov.br/api`

## Situação

Fonte oficial e pública, sem autenticação observada. O catálogo documenta 28
recursos e utiliza a mesma família de portal da Prefeitura. Não foram
localizadas licença, versão da API, limite de requisições ou SLA.

Aplicam-se os mesmos limites conservadores: no máximo 10 requisições por minuto
até acordo com o publicador, backoff, cache, identificação do coletor e
preservação de cada resposta.

## Contrato observado

- raiz bem-sucedida: `resource,count,data`;
- paginação por `limit` e `offset`;
- `count` representa apenas as linhas retornadas;
- recurso ausente/inválido retorna HTTP 200 com raiz `error`;
- sucesso precisa de validação do corpo;
- resposta sem `ETag`, `Last-Modified`, CORS ou rate limit observável;
- cache explicitamente desabilitado pelo servidor.

## Recursos prioritários

| Recurso | Conteúdo | Filtros documentados | Uso |
|---|---|---|---|
| `contratos` | contratos e aditivos | `numero`, `limit`, `offset` | reconciliar PNCP |
| `processos` | processos licitatórios | `numero`, `limit`, `offset` | contratação |
| `licitacoes` | atos e PDFs | `titulo`, `limit`, `offset` | preservar documentos |
| `servidores` | catálogo de folhas em PDF | `ano`, `mes`, `tipo` | descoberta de RH |
| `atos-oficiais` | decretos e portarias | `ano`, `mes`, `tipo` | atos da Câmara |
| `indicacoes` | indicações legislativas | `titulo`, `autoria` | acompanhamento factual |
| `sessoes-legislativo` | sessões, pauta, ata, frequência e votação | `numero` | atividade legislativa |
| `pdc-relacao-dos-fiscais-de-contrato` | documentos de fiscais | não confirmado | controle contratual |

Indicação é uma proposição/solicitação legislativa; não deve ser apresentada
como obra executada, promessa cumprida ou obrigação assumida pelo Executivo.

## Tipos e divergências

Campos de identificador, data, valor e estado foram observados como strings,
com opcionais `null`. Exemplos de divergência entre documentação e resposta:

- `indicacoes`: documentação usa `autor`; resposta usa `autoria`;
- `sessoes-legislativo`: documentação simplifica para `url`; resposta possui
  `url_pauta`, `url_ata`, `url_frequencia` e `url_votacao`;
- contratos usam campos não prefixados, diferindo do exemplo apresentado.

O coletor deve validar o contrato vivo, preservar campos aditivos e nunca
transformar erro de schema em página vazia.

## Documentos

Na amostra verificada, PDFs de contratos, licitações, servidores, atos e sessões
ficam no próprio host
`portaldatransparencia.cmbarreiras.ba.gov.br`. Mesmo assim, downloads exigem
allowlist, limite de bytes, inspeção de MIME, hash, antivírus e processamento
isolado.

## Recursos catalogados

O snapshot sanitizado completo está em
`fixtures/sources/camara-transparencia/catalog-observation.json`.

## Oportunidades de produto

- linha do tempo de sessões com pauta, ata, frequência e votação;
- busca de indicações por autoria, situação, assunto e bairro, quando a
  normalização permitir;
- ligação factual entre indicação, resposta oficial, contratação e obra,
  mantendo cada relação como confirmada, inferida ou ainda não verificada;
- histórico de atos, contratos, fiscais e folhas documentais.

## Pendências antes do conector

1. confirmar termos, contato técnico e limite de consumo;
2. medir cobertura e atualização dos 28 recursos;
3. preservar fixtures reais sanitizadas;
4. definir identidade de sessão e indicação;
5. separar ausência de documento de documento ainda não publicado;
6. revisar nomes de pessoas e frequência com política editorial/LGPD;
7. reconciliar contratações com PNCP e finanças com TCM-BA.

## Implementação da atividade legislativa

O workflow semanal preserva `leis` e `indicacoes` em execuções independentes.
A projeção `api.get_camara_legislative_items` unifica os dois recursos e
normaliza autoria, protocolo, situação, data e link do documento. Links
relativos são resolvidos apenas para o host oficial da Câmara. A autoria é
texto declarado pela fonte: não há associação automática a um vereador por
semelhança de nome.
