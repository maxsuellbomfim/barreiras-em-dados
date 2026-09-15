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

## Atualização operacional — 15/09/2026

As seções acima registram a descoberta de 01/08, não o estado atual de implantação.
Os coletores de compras, itens, contratos e a normalização já existem.

- A execução semanal `34865113818` parou após quatro timeouts no cadastro do
  órgão. A consulta semanal não executou. A janela 07–14/09/2026 foi inferida
  do agendamento/código e recebe replay explícito, não foi presumida coletada.
- A execução retroativa `34835690380` concluiu compras de 13/07–11/08/2024,
  mas falhou nos contratos após respostas HTTP 503. O sucesso `34957780144`
  consultou compras de 13/06–12/07/2024 e outra fatia de contratos; não prova
  sozinho a retomada do controle exato que falhou.
- O workflow passa a tratar a etapa cadastral com `continue-on-error` e
  `steps.collect_registry.outcome` no gate final. Isso permite as etapas
  independentes sem converter falha cadastral em workflow bem-sucedido.
- `registry_only` consulta apenas órgão e unidades. Os modos anteriores e os
  dois agendamentos mantêm seus escopos. Falhas de preparação não são ignoradas.
- A verificação operacional exige partição final e execução coerentes,
  listas de modalidades falhas/adiadas/truncadas vazias e evidência preservada.
  Fonte vazia, fonte indisponível e consulta não executada não são equivalentes.

Replay da janela semanal: `34988436563`. Banco conferido: cobertura parcial,
modalidades 1 e 2 falhas, 3–13 adiadas, zero páginas/novos registros.
A etapa devolveu sucesso apesar da cobertura parcial; o comando passa a
devolver saída não zero nesse caso, após persistir o checkpoint e o evento.
Cobertura completa e consulta comprovadamente vazia continuam retornando zero.
A recuperação cadastral foi confirmada na execução `34989976158`, após PR #751:
órgão e unidades HTTP 200, dois snapshots já existentes conferidos por hash,
partição completa e zero falhas pendentes. Não recupera a janela semanal.
Próxima auditoria delimitada: estabilidade da retomada por cursor dos contratos.
Não interpretar `next_offset=0` de uma fatia como cobertura de todo o histórico.
