# Etapa 2 — descoberta da fonte PNCP para Barreiras

## Resultado operacional e cobertura

Saída 2 identifica lote com todas as seleções observadas em estados validados
(`query_complete`, `empty_confirmed`, `awaiting_source_publication`), sem páginas
truncadas, ainda com retentativas. O workflow mostra aviso e resumo de cobertura
parcial; pendências herdadas não são declaradas resolvidas. Saída 1 e exceções
mantêm falha. Nenhum estado do banco é convertido para completo por esse aviso.

## Reserva explícita por lote

`selected_query_controls` separa as compras selecionadas da união de retentativas
herdadas. É preservado antes da primeira requisição e no fechamento, inclusive
interrupções. A projeção usa a seleção explícita (até 50 controles); na ausência
do campo ou formato inválido mantém a reserva conservadora legada. Observações
continuam exigindo as mesmas evidências. Não reinterpreta cursores históricos:
as 47 pendências diagnosticadas precisam de nova consulta ou revisão separada.

## Indicador público de publicação pendente

A migration `20260921194000` amplia a projeção existente sem alterar os registros
brutos, retentativas ou cobertura. Valida a referência privada e o caminho da
compra antes de aceitar `awaiting_source_publication`. API mantém apenas quatro
campos públicos: controle, estado, data e fonte; nenhum corpo/hash é exposto.
Reprojeta apenas execuções com o novo estado, respeitando reservas mais recentes.
O frontend informa que ausência de publicação no PNCP não prova inexistência
do contrato em outras fontes. Aplicação em produção precisa de verificação
separada; checks de código não comprovam migração nem exibição pública.

## Preservação privada do diagnóstico municipal

O coletor transporta o corpo HTTP 404 apenas quando mensagem, status e caminho
confirmam a declaração explícita da fonte. Escopo inicial: CNPJ da Prefeitura
`13654405000195`, correspondente às 74 pendências auditadas. Reutiliza snapshots
privados com leitura de volta e SHA-256; nenhum `pncp_contrato` é criado.
`control_observations.response_evidence` referencia ID/hash/status do artefato;
o corpo não vai para logs ou mensagens de erro. `awaiting_source_publication`
depende de persistência bem-sucedida; falha no Storage interrompe a execução.
Retentativas e cobertura parcial permanecem: este PR não muda o gate geral
para verde nem autoriza afirmação pública de inexistência do contrato.

## Diagnóstico de 404 explícito — 21/09/2026

A consulta oficial da compra `13654405000195-1-000040/2026` respondeu HTTP 404
com a mensagem exata “Não há contrato publicado no PNCP para esta contratação.”
O diagnóstico `source_reports_no_published_contract` exige mensagem exata,
status 404 no corpo e caminho oficial correspondente à compra consultada,
sem redirecionamento para outro host/caminho. Outros 404 permanecem genéricos.
Isso não comprova inexistência de contrato fora do PNCP. Continua sendo
`PncpContractsResponseError`: a fila mantém o controle para reconsulta e não
declara cobertura vazia/completa. Não há nova publicação nem remoção de dados.
O corpo dessa sondagem não foi importado; este diagnóstico operacional não
substitui evidência preservada para conclusões públicas.

## Consulta alternativa limitada — 21/09/2026

No GitHub Actions, `Coletar cadastro PNCP` oferece `publication_evidence`.
Preencher `replay_since`, `replay_until` (até sete dias inclusivos) e
`publication_page` (1–100). O modo não executa outros coletores, normalização
ou publicação, mesmo se `publish_social_fund` estiver marcado. Falha nesta
etapa reprova o job, sem `continue-on-error`. A trava de concorrência PNCP
existente permanece compartilhada. Datas e página passam por variáveis de
ambiente com argumentos entre aspas, nunca interpoladas no código shell.

Com as credenciais técnicas já configuradas, a execução manual privada é:

```powershell
python -B -m barreiras_collectors.commands.collect_pncp_publication_evidence --since 2026-09-01 --until 2026-09-07 --page 1
```

- Consulta oficial `/api/consulta/v1/contratos`, somente CNPJ da Prefeitura,
  por **data de publicação**, não pelo ano do contrato ou da compra.
- Uma página de 50 registros por execução; janela máxima de sete dias;
  página máxima 100. Sem cron ou publicação automática.
- Reutiliza preservação privada por hash e leitura de volta do Storage.
  HTTP indisponível/204/404 não se torna ausência comprovada. Vazio exige
  resposta JSON 200 com totais explícitos e coerentes.
- Controle começa antes da autenticação do Storage. Partição inclui janela
  **e página**; `complete` refere-se exclusivamente à página preservada.
- `next_page` permite retomada manual. `window_complete=false` permanece
  inclusive na última página: ainda falta reconciliar as páginas, mudanças
  na fonte, controles repetidos entre páginas e vínculo oficial com a compra.
- Não cria registros de contrato consumidos pelo normalizador. O contrato
  antigo publicado agora não é descartado. Vínculos entre órgãos distintos
  exigem evidência posterior; não são inferidos desta consulta.

Próximo gate operacional: resposta oficial preservada e validada, seguida de
reconciliação integral de uma janela pequena antes de qualquer publicação.

## Auditoria de descoberta por período — 15/09/2026

### Preservação dirigida do par validado

Comando `python -B -m barreiras_collectors.commands.collect_pncp_municipal_link_evidence`;
no workflow PNCP, modo manual `municipal_link_evidence`. Sem argumentos livres,
o escopo é fechado às duas URLs oficiais do contrato 23/2026 e compra 3/2026 do
Fundo. Não expande os agendamentos nem executa outros coletores/normalização.

Usa `PncpRegistryPersistenceService` como snapshot de evidência privada (não
cadastro normalizado). O recurso recebe prefixo `municipal-link:` no metadado;
o schema técnico `pncp-registry-snapshot` e o corredor de Storage já existentes
são reaproveitados. Os bytes integrais são preservados sem reescrever campos;
upload idempotente e releitura por SHA-256 antecedem a validação cruzada.
Não cria registros brutos consumíveis pelo normalizador financeiro.

Partição `municipal-link:13654405000195-2-000023/2026`, sob `registry-api`, registra
o começo antes de autenticar ou consultar a fonte. Conclusão significa **dois
artefatos privados validados**, não cobertura histórica ou publicação. O
checkpoint liga os dois artefatos por ID/hash e mantém `publication_authorized=false`.
Falha preserva evidências eventualmente já gravadas, mas não fecha a partição
como completa. Identidade/link divergente, hash incorreto ou redirecionamento
inesperado bloqueia a validação. O par fixo foi escolhido pela auditoria abaixo;
não é algoritmo genérico de inferência por semelhança de nome/objeto.

Tentativas locais nesta etapa falharam no Storage (HTTP 400). A consulta
administrativa de permissões também foi negada à role local. Nenhuma permissão
foi ampliada. A conclusão operacional depende do replay isolado em produção e
da conferência dos metadados e da partição; testes verdes não comprovam upload.

Endpoint confirmado no [manual de integração](https://pncp.gov.br/manual/pt-br/latest/contrato_empenho/consultar_contratos_ou_empenhos_de_uma_contratacao.html):
o endereço do coletor por contratação está correto. Na contratação 40/2026,
HTTP 404 veio com mensagem explícita de que não há contrato publicado no PNCP
para aquela contratação. Isso não comprova inexistência de contrato fora do
PNCP e não permite reclassificar outras respostas 404 sem examinar sua evidência.

Sondagem da API `/api/consulta/v1/contratos`, `cnpjOrgao=13654405000195`,
`dataInicial=20260101`, `dataFinal=20260915`, página 1, tamanho 500: 40 registros,
uma página, zero páginas restantes. Os 40 controles são distintos e municipais.
Confronto com inventário normalizado: 39 presentes e um ausente. Inclui o
contrato 153/2024 publicado em 2026; ano da chave não substitui data de publicação.

A consulta individual oficial confirmou o contrato **130/2026**, controle
`13654405000195-2-000023/2026`, órgão Município de Barreiras, unidade Secretaria
Municipal de Administração, objeto Jornada Social de Barreiras, valor global
informado R$ 28.780. O vínculo publicado pela fonte é com a contratação
`13250888000162-1-000003/2026`; `frutoAdesao=false`, ata nula. Não interpretar
automaticamente como adesão nem corrigir o CNPJ. SQL read-only confirmou ausência
no bruto e normalizado. A busca exclusivamente pelas compras de Barreiras omite
contratos municipais com contratação-pai externa. Este diagnóstico não altera
totais públicos nem autoriza afirmar execução/pagamento.

A consulta da compra-pai no endpoint antigo retornou HTTP 301 com mensagem
indicando o novo endereço `/api/consulta/v1/orgaos/{cnpj}/compras/{ano}/{sequencial}`.
No endereço indicado, a resposta confirmou o controle exato
`13250888000162-1-000003/2026`, órgão **Fundo Municipal de Assistência Social**,
unidade **Fundo Municipal de Assistência Social 2026**, município Barreiras e
IBGE **2903201**. Objeto Jornada Social de Barreiras, inexigibilidade IN-029/2026.
Assim, é outro CNPJ municipal, não prova de compra de outro município nem de erro
do vínculo publicado. A auditoria mantém `cross_organization_links` em revisão
porque compara CNPJs, não infere pertencimento territorial sem cadastro/evidência.
Próxima implementação deverá preservar ambos os registros e representar o Fundo
como órgão próprio, sem reescrever seu identificador como se fosse o da Prefeitura.

### Repetir a auditoria sem escrita remota

Preparar JSON com chaves do inventário, via consulta somente leitura:

```sql
select distinct c.external_id as contract_control,
       p.external_id as procurement_control
from procurement.contracts c
left join procurement.procurements p on p.id=c.procurement_id
where c.external_id like '13654405000195-2-%';
```

```powershell
node scripts/audit-pncp-contract-inventory.mjs 20260101 20260915 caminho/inventario.json
```

Uma única consulta de até 500 registros e até 366 dias, timeout de 60s. Não usa
credenciais. Saída contém apenas chaves oficiais, contagens e diagnósticos, nunca
fornecedores, identificadores pessoais ou valores. Código 0: chaves coincidem no
recorte; 2: revisão necessária; 1: resposta incompleta/inválida/indisponível.
Não pagina automaticamente: subdividir o intervalo se exceder uma página.
`MATCH` não comprova cobertura histórica, igualdade de valores ou publicação
autorizada. Nenhuma resposta de erro pode ser tratada como lista vazia.

Próximo passo: preservar o catálogo por período e seus documentos antes de
publicar recuperações; manter pai externo separado do cadastro de compras locais.

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
O lote consultado contém apenas controles do CNPJ atualmente atendido pelo RPC;
outros órgãos não invalidam os estados elegíveis, mas permanecem sem observação
individual disponível. O limite de 60 chaves distintas vale antes desse filtro.
O link principal do card, por sua vez, usa o CNPJ, ano e sequência do controle
oficial da própria compra, nunca o CNPJ fixo da Prefeitura. Essa construção de
URL não valida pertencimento territorial, identidade do órgão ou publicação:
tais verificações continuam sendo responsabilidade da ingestão/normalização.
A consulta de estado não usa cache para não reapresentar sucesso durante uma
reserva nova. O card mostra data no horário de Barreiras e ressalta que conclusão
da consulta não comprova execução, pagamento ou cobertura de todo o histórico.
