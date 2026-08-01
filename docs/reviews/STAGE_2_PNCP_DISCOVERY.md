# Etapa 2 — descoberta da fonte PNCP para Barreiras

Data: 01/08/2026. Pesquisa somente leitura contra a API pública, sem coleta.

## Confirmado ao vivo

- **Órgão cadastrado e validado**: `GET
  https://pncp.gov.br/api/pncp/v1/orgaos/13654405000195` →
  `MUNICIPIO DE BARREIRAS`, esfera `M`, `statusAtivo: true`, validado em
  2021-07-28. O CNPJ confere com o cabeçalho do Diário Oficial preservado.
- **Unidades**: `GET .../orgaos/13654405000195/unidades` → **57 unidades**,
  incluindo secretarias, fundos e gabinetes.
- **Contratações**: `GET https://pncp.gov.br/api/consulta/v1/contratacoes/
  publicacao?dataInicial=AAAAMMDD&dataFinal=AAAAMMDD&cnpj=…&
  codigoModalidadeContratacao=6&pagina=1&tamanhoPagina=N` → paginação por
  `totalRegistros`/`totalPaginas`/`data[]`; **23 pregões eletrônicos em
  2026** com objeto, número e `valorTotalEstimado` (ex.: pregão 001,
  fornecimento de alimentos, R$ 290.506,50 estimado).

## Qualidade da fonte (achados que a coleta deve preservar, não corrigir)

- unidades **duplicadas** com códigos distintos (ex.: quatro variações de
  "Prefeitura", dois "Gabinete do Prefeito", secretarias repetidas com e sem
  sufixo "2026");
- fundos marcados `statusAtivo: false` convivendo com equivalentes ativos;
- códigos de unidade em formatos heterogêneos (`000000004`, `020201`, `2910`,
  `983363`);
- **anomalia relevante**: a unidade `2` aparece como "Prefeitura Municipal de
  Coração de Maria" — outro município — sob o CNPJ de Barreiras. Reforça a
  regra do roadmap: reconciliação sem fonte vencedora global, e nenhuma
  agregação por unidade antes de revisão.

## Pendente de verificação (próximas sondagens)

- endpoint de contratos (`/api/consulta/v1/contratos`) respondeu com forma
  inesperada aos parâmetros testados — confirmar nomes de parâmetros e
  paginação na especificação oficial antes de codificar;
- demais modalidades (dispensa, inexigibilidade), atas de registro de preços
  e documentos anexos;
- limites de taxa e cabeçalhos de cortesia da API de consulta.

## Pré-requisitos técnicos para a primeira coleta

- a identidade técnica do Storage está restrita ao prefixo
  `querido-diario/gazettes/` por check constraint em
  `audit.storage_workload_identities`; coletar PNCP exigirá migration
  ampliando o modelo de prefixos (um por fonte) e, idealmente, uma
  identidade técnica própria por coletor;
- cadastrar fonte/endpoint PNCP no seed (`source.data_sources` /
  `source.source_endpoints`);
- menor fatia sugerida (sequência do roadmap): preservar como bruto o
  cadastro do órgão e das unidades (snapshot versionado por hash), sem
  interpretar nem publicar.

## Fora de escopo desta descoberta

Comparação de preços, alertas de sobrepreço e qualquer publicação — a Etapa
2 publica apenas depois de itens/contratos com evidência e histórico, e
comparações de preço ficam explicitamente para fase posterior.
