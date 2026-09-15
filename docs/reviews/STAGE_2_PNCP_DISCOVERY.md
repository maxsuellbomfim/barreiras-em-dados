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

### Retomada por chave — 15/09/2026

O teste de regressão reproduziu 120 pendências antigas: OFFSET processava
001–050 e depois 101–120, fechando com 50 omitidas. O novo cursor usa
`cursor_version=1`, `next_after_control` e `retry_controls`. A consulta ordena
e compara a chave oficial com collation C; a posição não depende do tamanho
atual da fila ou de alterações na data publicada. Ao terminar a varredura,
o cursor volta ao início para novas observações e pendências anteriores.

O lote mantém o teto de 50 controles e 30 páginas por controle. Antes da
primeira requisição é gravada uma reserva não terminal de todos os controles
selecionados. Um erro não perde essa reserva mesmo após gravar artefatos;
checkpoint final remove apenas os controles concluídos. Truncados e retries
conhecidos que retornem sem páginas permanecem parciais. Erro recuperado registra
incidente, conserva o checkpoint e termina com falha; pendências conhecidas
também retornam código não zero. Um lote limitado só pelo teto normal pode
encerrar com código zero, mas a cobertura permanece `partial` e o cursor indica
a próxima fatia — não significa histórico completo.

Offset antigo reinicia de forma conservadora, preservando chaves truncadas
válidas. Uma lista de pendências inválida bloqueia a execução, nunca é descartada
silenciosamente. Controles pendentes atrás do cursor aguardam o fim da varredura
para não impedir o avanço por controles posteriores. Alterações que entram atrás
do cursor serão observadas na próxima volta, não no mesmo retrato.

Limites separados: a interpretação original de HTTP 404/204 e a paginação
interna acima de 30 páginas ainda exigem revisão; este patch não os declara
recuperados nem publica novos fatos financeiros. CI e replay limitado devem
comprovar o cursor e os registros reais antes de fechar a recuperação.

Operação desta entrega: usar apenas o workflow PNCP, cuja concorrência de
produção já serializa as execuções. Não executar o mesmo backlog por CLI
simultaneamente: a reserva ainda não implementa lease ou exclusão distribuída
entre executores de caminhos diferentes. Esta limitação não é resolvida pelo
cursor estável; qualquer expansão para múltiplos executores exige outra revisão.

### Respostas de contratos e prova de vazio — 15/09/2026

O replay `35011311863` do PR #755 confirmou a retomada de 50 controles na ordem
planejada, preservou três páginas/seis observações e não alterou as 306 versões
normalizadas existentes. As 47 respostas HTTP 404 foram chamadas de vazias pelo
conector legado. Não são prova de ausência de contrato; a cobertura continua
parcial, embora o workflow daquela versão tenha terminado verde.

O [manual oficial de contratos por contratação](https://pncp.gov.br/manual/pt-br/latest/contrato_empenho/consultar_contratos_ou_empenhos_de_uma_contratacao.html)
confirma o endpoint e as chaves de vínculo, mas não estabelece que HTTP 404/204
certifique inexistência de contratos. A política conservadora desta entrega é:

- HTTP 404/204: resposta inconclusiva, motivo/status/página registrados, controle
  mantido em `retry_controls`. Não publica zero e não remove fatos anteriores.
- HTTP 200 com lista vazia explícita: preservar corpo, URL, hash e cursor; só
  depois de conferir a persistência pode resolver a pendência daquela consulta.
  É observação do recurso naquele momento, não cobertura de todo o histórico.
- Envelope paginado: validar metadados explícitos e contagens; não presumir
  uma página quando faltam metadados, nem descartar itens de tipo inválido.
- Página repetida, mudança de paginação ou quantidade incompatível: manter
  parcial e conservar as páginas válidas já recebidas, sem duplicar a repetida.
- O teto segue 50 contratações/30 páginas. Respostas inconclusivas não impedem
  avançar a chave; retries atrás do cursor voltam após a varredura. Falha de
  Storage/banco ou erro transitório esgotado continuam interrompendo com
  checkpoint recuperável, sem alargar tentativas ou limites da fonte.

O evento `collector_pncp_contratos_inconclusive` distingue motivo, código HTTP
e página. `collector_pncp_contratos_empty_confirmed` só existe após preservação
da resposta vazia. As métricas conservam `response_issues` e `empty_controls`;
o checkpoint reutiliza a lista durável de pendências. Itens e resultados não
têm sua interpretação alterada por esta entrega.

A normalização pode aproveitar registros válidos apesar de respostas parciais
em outros controles. `collect_contracts.outcome` entra obrigatoriamente no gate
final; a execução não fica verde apenas porque a normalização concluiu.
O próximo replay será dirigido e auditado contra os hashes anteriores. Resposta
inconclusiva deve produzir `partial`/falha explícita, não uma promessa de fonte
recuperada. Nenhum registro antigo ou migration aplicada foi reescrito.

### Cards públicos: ausência de vínculo não comprova ausência na fonte

O replay dirigido após o PR #756 confirmou a manutenção das respostas
inconclusivas como pendências, com falha explícita no gate final e sem alteração
dos dados públicos. Não confirmou recuperação da fonte.

O aviso de cobertura fica visível antes dos detalhes de execução financeira.
As mensagens de vínculos ainda não publicados, preparação e indisponibilidade
usam linguagem simples. Possíveis causas são apresentadas como possibilidades,
nunca como diagnóstico individual. Os valores vinculados continuam iguais.

A API atual não inclui cobertura por controle PNCP. Portanto os cards não
declaram HTTP 404/204, vazio confirmado ou completude por contratação. Uma
projeção auditável por identificador oficial é necessária para esse próximo
passo. Testes renderizam o componente real nos quatro estados, preservam o
link oficial e verificam que o aviso não fica escondido em detalhes fechados.

### Observações individuais, versão 1 (escopo privado)

`source.collection_runs.metrics.control_observations` recebe no fechamento
controlado um registro por contratação efetivamente tentada, até o teto de 50.
O escopo `pncp_contracts_query` nunca representa todos os pagamentos, contratos
históricos ou documentos de outras fontes.

- `query_complete`: paginação validada e páginas preservadas; não atesta cobertura histórica.
- `empty_confirmed`: a consulta respondeu explicitamente vazia e a evidência foi preservada.
- `inconclusive`: resposta insuficiente, incluindo 404/204 ou paginação inconsistente.
- `partial`: limite de páginas atingido.
- `interrupted`: erro de coleta/persistência; mensagem da exceção não integra a observação.

Cada observação contém controle, início/fim UTC, motivo/status/página da resposta
inconclusiva quando conhecidos e páginas efetivamente preservadas. Cada página
referencia artefato, SHA-256, número, HTTP e quantidade observada. O hash retornado
pela persistência precisa coincidir com o corpo coletado. Corpos, chaves de bucket
e credenciais não são copiados. `records_preserved` conta linhas observadas mesmo
quando o artefato já existia; sem página verificada permanece `null`, nunca zero.

Não há observação inventada para controles selecionados mas não tentados. A
reserva anterior à coleta mantém esses controles retomáveis. Se o processo for
encerrado abruptamente ou o fechamento falhar, as observações podem não ter sido
gravadas: o consumidor futuro deve respeitar a tentativa pendente e não apresentar
uma observação antiga como prova da conclusão da tentativa mais recente.

Esta entrega não altera API, UI, normalização, permissões ou migrations. A próxima
projeção pública deverá resolver artefatos/controles, validar o esquema versionado,
considerar a tentativa mais recente e expor só estado/data/fonte necessários ao
leitor, sem varrer os JSON brutos a cada card. A primeira execução operacional da
versão nova foi auditada após o PR #758: a seleção de 50 controles coincidiu com
as 50 observações, três com evidência de consulta concluída e 47 inconclusivas.
O gate final conservou a falha parcial; isso não é recuperação da fonte.

### Projeção pública de estado por contratação

`source.pncp_contract_query_status` é uma projeção privada de última tentativa,
não substitui o histórico de execuções e artefatos. Um trigger da execução
normaliza as reservas e observações; leituras públicas usam a chave primária,
sem varrer o JSON bruto. A migração inicial reconstitui as execuções elegíveis.
Execuções sem `control_plane=true` ou fora do endpoint PNCP de contratos são
ignoradas. Reprocessar uma execução antiga não substitui uma tentativa nova.

Reserva de controle pendente limpa a data/conclusão anterior. O fechamento da
mesma execução pode substituí-la por observação validada. Falha no fechamento
deixa a reserva pendente, não recupera sucesso antigo. Controles apenas herdados
na lista de pendências continuam pendentes, sem data de consulta inventada.

Observações precisam de versão/escopo, datas dentro da execução, contagens
coerentes e páginas consecutivas. Artefatos devem existir com SHA-256 e HTTP200
compatíveis, schema de contratos e cursor do mesmo controle. Duplicatas ou
inconsistências resultam em `unknown`, sem impedir a preservação de outros fatos.

`api.get_pncp_contract_query_status(text[])` atende até 60 controles municipais
por chamada e expõe somente controle, estado, data e link oficial. Referências
internas/hashes permanecem privados. Sem observação válida, `unknown` significa
verificação individual não disponível, jamais não-coletado comprovado.

O cliente valida cardinalidade, duplicatas, controles, estados, data e origem do
link. Falha de RPC produz aviso de indisponibilidade sem remover os contratos.
A consulta de estado não usa cache para não reapresentar sucesso durante uma
reserva nova. O card mostra data no horário de Barreiras e ressalta que conclusão
da consulta não comprova execução, pagamento ou cobertura de todo o histórico.
