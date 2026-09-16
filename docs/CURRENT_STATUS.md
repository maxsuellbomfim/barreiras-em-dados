# Estado atual do Barreiras 360

Atualizado em **16/09/2026**. Este é o ponto de entrada operacional; o histórico
de decisões e entregas permanece em `docs/ROADMAP.md` e `docs/adr/`.

## Fase atual

### PNCP: fundos de Educação e Cultura corrigidos

A migração `20260916104808_pncp_fund_owner_repair.sql` foi aplicada, e a operação
privada retornou dois reparos. Os contratos `30667266000153-2-000013/2026` e
`50525166000108-2-000062/2026` estão na versão 2 com seus fundos próprios, mantendo
as versões anteriores. Os valores permanecem R$ 30.756,96 e R$ 11.259,12.

A compra-pai oficial é a mesma: `13654405000195-1-000002/2026`. A resposta da API
de resumo manteve três contratos e R$ 253.195,44; o digest da resposta completa
foi idêntico antes/depois. Nenhum empenho, aditivo ou obra dependia das versões
corrigidas. O Fundo Social e o contrato 130/2026 seguem pendentes de importação.

### PNCP: normalização com órgão explícito

A migração aplicada `20260916023040_pncp_explicit_owner.sql` remove a atribuição por
IBGE sozinho. Cada CNPJ precisa resolver um único órgão cadastrado; o código
legado `PREF-BARREIRAS` é aceito explicitamente para a Prefeitura. O controle
PNCP deve corresponder ao CNPJ do registro. O contrato pode apontar para uma
compra de outro órgão cadastrado pela chave oficial, sem inferência por texto.
Correções de órgão ou vínculo geram novas versões, preservando a origem.

Na consulta de produção, somente a Prefeitura estava cadastrada. O Fundo e o
par privado ainda precisam de importação validada. Esta entrega não cadastra
órgãos, não publica esse par e não declara cobertura adicional da fonte.

### PNCP: links corretos para órgãos com CNPJ próprio

O link oficial dos cards passa a ser derivado do controle PNCP completo, sem
substituir o CNPJ do Fundo pelo da Prefeitura. Identificador inválido não gera
link presumido. A consulta de estado atende apenas as chaves suportadas pelo
RPC atual; uma chave de outro órgão não apaga os estados das compras municipais.
Não são alterados valores, dados publicados, permissões ou normalização.

Antes de publicar a compra do Fundo, falta resolver explicitamente seu órgão
no normalizador: o fluxo atual associa compras territoriais ao órgão executivo
principal e busca o contrato-pai sob esse mesmo órgão. Essa premissa não atende
ao par preservado com CNPJs distintos. A integração pública permanece pendente.

### PNCP: preservação privada do vínculo Prefeitura–Fundo Social

O modo manual `municipal_link_evidence` preserva somente o contrato 130/2026
e a compra IN-029/2026 do Fundo Municipal de Assistência Social. Reutiliza o
armazenamento imutável de snapshots, com releitura por hash, sem criar registros
`pncp_contrato`/`pncp_contratacao` nem chamar normalização ou publicação.
Valida controles exatos, CNPJs distintos corretos, IBGE 2903201 nos dois arquivos
e vínculo declarado na fonte. A execução é registrada antes da autenticação.

As tentativas locais falharam no upload privado; não comprovaram preservação.
Depois do PR #761, a execução de produção 35027228347 concluiu o modo isolado
e registrou `validated_artifacts=2`, `publication_authorized=false`, sem ampliar
permissões. A integração pública continua pendente.

### PNCP: lacuna confirmada na descoberta por contratação-pai

A consulta oficial por publicação de 01/01 a 15/09/2026 retornou 40 contratos
municipais em uma página. O inventário contém 39 dessas chaves. O contrato
130/2026 (`13654405000195-2-000023/2026`) é municipal, mas o PNCP o relaciona à
compra `13250888000162-1-000003/2026`, de outro CNPJ. Ele não consta no bruto nem
no normalizado: partir apenas das compras municipais não o descobre.

O script read-only `scripts/audit-pncp-contract-inventory.mjs` compara o catálogo
oficial por período com um inventário de chaves, exige a página integral e
aponta ausências e vínculos divergentes. Não importa, normaliza nem publica.
A compra-pai foi confirmada na nova API oficial: Fundo Municipal de Assistência
Social de Barreiras, CNPJ próprio e IBGE 2903201. Outro CNPJ não significa outro
município. A vinculação ainda requer preservação e tratamento do órgão correto.
Próxima entrega: descoberta por período e cadastro explícito dos fundos municipais,
sem atribuir suas compras ao CNPJ principal nem publicar sem evidência preservada.

### PNCP: estado individual da consulta nos cards

Projeção privada indexada por controle oficial, atualizada junto com a reserva
e o fechamento do coletor. Uma tentativa mais recente pendente substitui sucesso
antigo; evidência malformada ou incompatível não certifica conclusão. A API
limitada a 60 controles retorna somente estado, data e link oficial. A ausência
de observação é desconhecida, não prova de que nunca houve coleta.

Nos cards, consulta concluída, resposta vazia confirmada, resposta inconclusiva,
páginas pendentes, interrupção e indisponibilidade recebem mensagens distintas.
O aviso permanece fora dos detalhes. Falha da consulta de estado não oculta
contratações e valores já publicados. Não há conclusão sobre pagamentos ou
cobertura histórica; nenhum valor financeiro é recalculado.

### PNCP: evidência individual das consultas de contratos

O coletor passa a registrar `control_observations` nas métricas privadas da
execução: identificador oficial, início/fim, resultado e referências/hash das
páginas verificadas. Distingue consulta concluída, lista explicitamente vazia,
resposta inconclusiva, limite de páginas e interrupção. Nenhuma página preservada
significa contagem desconhecida, não zero. Hash incompatível impede conclusão.

Esta base privada alimenta agora a projeção pública individual descrita acima.
As observações só são gravadas quando o fechamento controlado da execução é
persistido. Encerramento abrupto ou falha nesse fechamento conserva a reserva
de pendências, mas não autoriza inferir o resultado individual ausente. Runs
antigos não são retroativamente classificados. Sem migration, acesso novo ou
alteração dos valores públicos. O primeiro run do PR #758 foi auditado: 50
observações correspondentes à seleção prevista, três consultas concluídas e
47 inconclusivas, sem falso vazio. Registros anteriores conservaram seus hashes.

### PNCP: limites dos vínculos explicados nos cards

Os cards de licitações passam a avisar, antes de abrir os detalhes, que os
vínculos publicados não comprovam a coleta de todos os contratos e pagamentos.
As mensagens distinguem vínculos ainda não publicados, preparação e resumo
indisponível. Valores, fontes e cálculos permanecem iguais. A API ainda não
expõe cobertura individual por contratação: esta entrega não classifica uma
consulta específica como vazia, completa ou inconclusiva. Esse é o próximo
passo, com evidência própria por identificador oficial.

### PNCP: resposta inconclusiva não é ausência de contratos

O replay do PR #755 percorreu exatamente as 50 chaves previstas e conservou
os 334 registros brutos e as 306 versões normalizadas anteriores. Preservou
seis novas observações, sem criar versões públicas redundantes. Porém, 47
consultas HTTP 404 ainda eram registradas como vazias. O lote permaneceu
parcial; isso não comprovou inexistência de contratos nem cobertura histórica.

A correção distingue HTTP 404/204 e conteúdo inconsistente de uma lista HTTP
200 explicitamente vazia. A lista vazia precisa ser preservada e relida por
hash antes de concluir a consulta. Páginas repetidas, contagens incompatíveis
e erros após uma página válida mantêm o controle pendente. O lote continua
nas outras chaves e salva a retomada, sem ficar preso à primeira resposta 404.

Contratos válidos de outras consultas continuam chegando à normalização, mas
o gate final reprova o workflow se houve pendências: publicar dados validados
não significa esconder falhas de cobertura. Não há nova dependência, migration
ou alteração de valores públicos. O PR #756 foi mesclado após os checks verdes.
O replay limitado confirmou respostas inconclusivas conservadas como pendência,
normalização independente e reprovação explícita no gate final. Isso confirmou
o tratamento da falha, não a recuperação da fonte; não houve alteração dos
dados públicos nesse replay.

### PNCP: retomada de contratos sem saltos na fila

Reprodução local: numa fila de 120 contratações antigas, o OFFSET avançava
sobre registros que desapareciam da elegibilidade após a preservação. O comando
encerrava como completo tendo percorrido só 70 controles, deixando 50 para trás.
A retomada passa a usar a chave oficial em ordem estável, com cursor versionado;
offset legado reinicia explicitamente, sem presumir uma conversão de posição.

Antes de consultar/preservar páginas, uma reserva durável mantém os controles
do lote e pendências anteriores. Interrupção ou falha na gravação final deixa
essa reserva disponível. Páginas truncadas e retries conhecidos com retorno
sem páginas não somem por já existir um artefato. Pendências atrás do cursor
voltam na próxima varredura; não consomem sempre o começo de cada lote.

Testes cobrem 120 controles em três lotes, compras recentes que permanecem
elegíveis, truncamento, falha após preservação, cancelamento e falha de checkpoint.
A correção não certifica cobertura histórica nem redefine HTTP 404/204 como
ausência comprovada. A publicação exige CI verde e conferência operacional de
uma execução limitada antes de declarar recuperação real da fila.

### PNCP: valores com centavos não são ausência na fonte

Após recuperar a lista, a conferência identificou um erro na projeção monetária:
três expressões regulares aceitavam inteiros, mas rejeitavam decimais oficiais.
Na página padrão de 60 contratações, 60 valores estimados e 40 homologados
estavam presentes no registro bruto, porém saíam como nulos na API. Isso fazia
a interface informar ausência indevidamente. Os originais permanecem íntegros.

A correção aditiva troca somente essas três validações por um ponto decimal
literal, preservando valores, filtros, assinatura, permissões e evidências.
Não estima nem soma dinheiro; zero e negativos informados são preservados,
enquanto ausência ou conteúdo inválido não viram zero. A publicação exige testes de regressão e
reconciliação entre o registro bruto, a API anônima e os números visíveis.

O PR #754 foi mesclado e a migração `20260915183000` aplicada. No recorte
padrão, a reconciliação confirmou 60 contratações e 562 resultados sem
divergências dos valores brutos; os demais campos e permissões foram preservados.
A API anônima e o site confirmaram os valores, incluindo R$ 308.568,74 na compra
`13654405000195-1-000039/2026`, com zero distinto de ausência. Celular e desktop
validados; 812 testes Node aprovados, três ignorados, CI Node/Python e Vercel verdes.
Isso encerra o defeito monetário observado, não a coleta semanal parcial.

### PNCP: recuperar a consulta pública de licitações

A RPC pública de contratações estava retornando HTTP 500/57014; receber HTML
200 na rota não comprovava que os registros tinham aparecido. O plano SQL
mostrou uma varredura de toda a tabela bruta para as compras e outra para os
resultados de cada compra. A consulta de 2026 excedeu 20 segundos no diagnóstico.
Dois índices parciais usam as chaves oficiais já consultadas, sem trocar a RPC,
seus filtros, permissões, valores, itens, resultados ou evidências.

No ensaio transacional revertido de 15/09, o corpo da consulta retornou 40
contratações de 2026 em 808 ms. A função real retornou a lista padrão de 60 em
1.074 ms; os índices ocuparam 152 KiB. São medições pontuais, não promessa de
latência nem prova de cobertura histórica. O PR #753 foi mesclado com checks
verdes e a migração `20260915170000` aplicada: 60 chaves distintas, quatro
funções/ACL e 306 versões contratuais preservadas. A API anônima confirmou as
evidências atuais dos seis contratos em três consultas (877/201/176 ms).
O navegador exibiu 60 cards sem aviso de indisponibilidade. Isso encerra o
timeout observado; a leitura de centavos e a cobertura semanal são pendências
separadas, não encerradas por esse resultado.

### PNCP: impedir retorno à versão antiga dos contratos

A auditoria do replay de 15/09 identificou seis contratos oficiais com um
snapshot novo preservado, mas a normalização produziu doze versões: processava
o novo e depois o antigo, deixando os seis contratos na evidência anterior.
Uma migration aditiva seleciona um único snapshot mais recente por chave
oficial antes do limite, preservando histórico e vínculo com o registro bruto.
Snapshots já representados pela versão atual não devem consumir o lote.
O PR #752 foi mesclado e a migração `20260915154500` aplicada em produção.
Foram criadas seis versões corretivas; as 300 versões anteriores permaneceram
inalteradas. As 192 chaves oficiais ficaram reconciliadas, sem divergência do
snapshot mais recente; repetir o lote não criou versões nem fornecedores.
Após a correção do timeout no PR #753, a API pública confirmou os seis contratos
sem duplicação e com as evidências atuais por identificador bruto e hash.

### PNCP: falha cadastral não deve interromper compras independentes

A execução semanal `34865113818` falhou no cadastro em 14/09 antes de consultar
as contratações. A execução verde de 15/09 percorreu outra janela retroativa;
não recuperou o cadastro nem comprova a janela semanal de 07–14/09/2026.
O replay dirigido `34988436563` registrou cobertura parcial: duas modalidades
falharam, onze foram adiadas e nenhuma página foi preservada nessa janela.
Isso não comprova ausência de contratações. A recuperação permanece pendente.

O workflow isola agora a falha cadastral das etapas independentes e mantém
reprovação obrigatória ao final quando cadastro ou itens falham. O novo modo
`registry_only` recupera só órgão/unidades, sem repetir compras ou normalização.
Testes verificam todos os modos, os dois agendamentos e o código de saída real
do gate. A consulta por janela também deve devolver falha quando a cobertura
for parcial, preservando o checkpoint; vazio comprovado permanece distinto.
Nenhuma regra de publicação, valor ou limite da fonte foi alterado.

O PR #751 foi mesclado com checks verdes. O modo `registry_only`, execução
`34989976158`, recuperou órgão e unidades: HTTP 200, dois snapshots existentes
conferidos por hash, zero duplicação. Banco: `registry:current` completo,
execução concluída e zero falhas pendentes desse recorte. A janela semanal
continua parcial. A fila de contratos exige auditoria separada de cursor e
distinção entre HTTP 404, resposta vazia e paginação incompleta.

### Recuperação das coletas financeiras — 15/09/2026

A execução financeira de 15/09 falhou na instalação das dependências de
balancetes e no acesso ao catálogo de Transferências Especiais da Bahia.
A instalação repetida agora usa três tentativas limitadas, sem trocar versões
fixadas nem ocultar o último erro. O conector estadual registra a etapa e uma
categoria de falha sanitizada por tentativa, mantendo os quatro pedidos e o
timeout já existentes. Uma sonda do catálogo retornou HTTP 200 e contrato
válido; isso não comprova preservação nem recuperação da execução completa.
O fechamento exige replay dirigido, conferência dos documentos e, no caso
estadual, normalização e reconciliação pública do mesmo retrato.

O PR #749 foi mesclado e o replay de balancetes `34985731862` concluiu catálogo
e drenagem: 120 documentos existentes, 120 PDFs já preservados, zero falhas ou
duplicações. Banco e API pública confirmaram o resultado. O replay estadual
`34986034919` preservou um ZIP com cinco views e 12.361 linhas, mas a
normalização parou por timeout na autenticação do Storage. Essa etapa recebe
agora até três tentativas somente para falhas transitórias de transporte;
credencial recusada ou sessão incompleta continuam interrompendo sem repetição.
Após o PR #750, o replay `34987498327` concluiu aquisição, normalização e
reconciliação pública do mesmo ZIP. Banco e API confirmaram três pagamentos
territoriais, um autor no ranking, zero pagamentos sem vínculo e zero falhas
pendentes da partição atual. Os seis registros brutos já existiam; não houve
duplicação. Isso não encerra pendências históricas de outras partições.

### Farmácia Popular: exportação CSV da consulta completa

A página de saúde recebe download CSV de todas as páginas da seleção de ano
e estabelecimento. A exportação lê um único retrato revisado no banco, com
limite explícito de 5.000 documentos e 4 MB; excesso ou falha não gera arquivo
parcial. Valores decimais são preservados como texto, com fonte e ressalva de
cobertura parcial em cada linha. Identificadores numéricos e textos interpretáveis
como fórmulas recebem proteção de planilha, explicada na interface.

A nova RPC foi aplicada isoladamente, com histórico transacional. A conferência
da API manteve os 335 documentos públicos de 2021–2026 sem alteração. O leitor
CSV padrão do Python comparou os seis arquivos anuais e dois filtros de 2025
com a projeção pública: nenhuma divergência. Os 763 testes Node, 180 FNS,
contratos, migrations, typecheck e build web passaram. Download por teclado,
fonte de 16 px, controle de 44 px e larguras de 390/1280 px foram conferidos.
A entrega não importa dados novos nem comprova cobertura completa da fonte.

### Farmácia Popular: seleção pública por estabelecimento

A rota de saúde recebe filtro por estabelecimento dentro do ano escolhido,
com opções paginadas e contagem calculada sobre todas as páginas da seleção.
A referência reutiliza um documento já público, sem expor a chave privada do
cadastro. Nomes iguais permanecem separados; link inválido, revogação ou mudança
da evidência não ampliam a consulta automaticamente. Trocar o ano reinicia o
filtro; retornar de uma página vazia conserva a seleção. A atualização da coleta
continua identificada como anual, antes do filtro.

A migration aditiva foi aplicada isoladamente em 15/09, sem reparar o histórico
remoto anterior. A comparação integral das RPCs públicas de 2021–2026 conservou
os mesmos documentos e hashes; a união das seleções reproduziu cada ano sem
perdas ou duplicatas. Testes reais de banco e renderização, 742 testes Node,
180 testes FNS, typecheck/build web e navegação em 390/1280 px passaram.
Esta entrega não importa pagamentos nem comprova cobertura histórica completa.
Próximo passo de dados: obter o leiaute oficial por estabelecimento/competência
antes de atribuir a Barreiras parcelas recebidas por matrizes, conforme o domínio.

### Farmácia Popular: página vazia não é ausência de publicação

A navegação distingue uma página posterior sem registros (`empty_page`) de
publicação em preparação e falha de consulta. O retorno à primeira página
preserva o ano selecionado. A mudança não altera pagamentos, cobertura,
aprovações ou coletores. A busca de dados por filial identificou uma previsão
de abertura da base DBPOPFARMA em outubro/2026; o leiaute financeiro continua
não comprovado, conforme o documento de domínio.

### Farmácia Popular: limite da lista explicado ao público

A página de saúde passa a explicar, antes dos registros, que a lista de
pagamentos não é o cadastro completo de farmácias. Ausência não prova falta
de repasse ou atendimento, e total de matriz não é atribuído a Barreiras sem
detalhamento por filial. O aviso permanece visível nos estados de preparação
e indisponibilidade, sem alterar valores, contagens ou aprovações. A leitura
foi conferida no desktop e celular; o próximo dado necessário está especificado
no documento de Farmácia Popular: demonstrativo por estabelecimento e competência,
sem dados de pacientes e sem confundir autorização com pagamento.

### Vínculo documental matriz/filial — investigação privada

O leitor de Farmácia Popular agora permite localizar uma linha do cadastro
preservado na coluna exata de estabelecimento do PDF de renovação de 2025.
A saída contém hashes e posições documentais, sem identificadores ou nomes.
Duplicatas e identificadores inválidos bloqueiam a conclusão. O vínculo não
comprova pagamento municipal, histórico de credenciamento ou nome da filial;
não altera o publicador nem o agendamento. Próximo passo: conferir documentos
financeiros da matriz identificada, sem atribuir o total de uma rede a Barreiras.

### Retomada após disputa entre coletas — 14/09/2026

O wrapper de Farmácia Popular agora espera até 15 minutos pela trava exclusiva
da fonte, antes de carregar credenciais ou criar um lote. Isso permite serializar
as tarefas atrasadas que o Windows inicia juntas ao voltar a ficar disponível.
Tempo esgotado é adiamento com código de erro, nunca coleta concluída. Erros de
permissão ou de caminho não são tratados como disputa transitória.
Cada tentativa registra estado, etapa e horários em arquivo local sanitizado,
inclusive antes do coletor. Esse diagnóstico é separado do último relatório
documental; não altera a consulta pública nem afirma cobertura integral.

### Comparação cadastral privada — 10/09/2026

O comparador de Farmácia Popular agora confronta o cadastro XLSX preservado com
o catálogo anual paginado do FNS, por identificador completo. Incompletude ou
evidência inválida impedem conclusões de ausência. A saída privada traz contagens
e posições documentais; não publica nomes, identificadores nem valores novos.
Compara os retratos fornecidos: cadastro atual não comprova credenciamento
histórico, e ausência em uma consulta não prova ausência de pagamento. Ainda não
integra o agendamento; os limites estão no documento de Farmácia Popular.

### Proteção adicional de cobertura — 10/09/2026

O fluxo de Farmácia Popular agora reconcilia explicitamente o tamanho do
catálogo concluído com as observações entregues à publicação. Falta, repetição
de estabelecimento ou ano incompatível interrompem a execução antes de qualquer
importação. Um catálogo vazio só é aceito quando a aquisição também declara
vazio. Isso protege contra perda silenciosa entre etapas; não comprova que
fontes externas ainda desconhecidas estejam cobertas. Os novos testes simulam
essas divergências e verificam que nenhuma publicação foi chamada.

O projeto está em **estabilização do pré-lançamento e construção do rastro do
dinheiro**. A fundação, a coleta preservada do Diário e as primeiras projeções
públicas de atos, finanças, compras, Legislativo e representação já existem.
O trabalho atual não é abrir outra fase ampla: é tornar cobertura, qualidade,
desempenho e leitura pública confiáveis antes do lançamento divulgado.

### FNS: dois vínculos publicados; catálogo das demais ações conferido

A rota `/recursos/saude` consulta o RPC revisado de Farmácia Popular no servidor,
com filtro por ano e páginas de 25 registros. Sem aprovações, mostra pendência;
falha de consulta é indisponibilidade, nunca zero. Não carrega originais privados.
O contrato recusa evidência inválida e registros repetidos. Em 08/09, após
autorização explícita e validação, foram publicados 25 documentos de 2025 de dois
estabelecimentos. Três arquivos privados foram relidos e conferidos por SHA-256;
o replay manteve dois snapshots e 25 documentos distintos. A página em produção
mostrou 25 cartões, com zero divergência entre a projeção e o lote validado.
Não são receitas municipais nem entram nos rankings de emendas. O piloto não
comprova cobertura anual, credenciamento histórico ou execução de serviços.

O inventário adicional desde 2021 identificou 191 documentos aptos à ampliação
e outros 119 com identidade histórica pendente, sem misturar outros programas.
Após autorização específica, os dez arquivos adicionais foram importados e
os 191 documentos aprovados: são 216 pagamentos públicos distintos entre
2021 e 2026. Onze objetos (incluindo o cadastro reutilizado) foram relidos e
conferidos byte a byte e por SHA-256. A comparação integral do novo lote com
a RPC pública encontrou zero divergências; o replay após aprovação conservou
12 snapshots, 216 documentos e 12 decisões. Permanecem 119 documentos com
identidade histórica pendente, fora da publicação. O leitor de catálogo valida
paginação, integridade e escopo antes de fechar a contagem anual de entidades.
Os detalhes e limites constam no documento de Farmácia Popular vinculado abaixo.

Na revisão seguinte, o PDF oficial de renovação cadastral de 2025 resolveu a
identidade institucional dos 119 documentos: sete recortes de quatro instituições,
por CNPJ exato de estabelecimento e matriz, com página e linha preservadas.
Isso não comprova credenciamento em 2021–2023. Após autorização específica,
os sete JSON e o PDF foram importados no bucket privado e relidos byte a byte
e por SHA-256. As migrations foram aplicadas e os 119 documentos aprovados após
conferência integral do plano. O replay manteve 19 snapshots e 19 decisões:
**335 pagamentos públicos distintos**, todos com valores, datas e evidências
correspondentes ao registro preservado. Não restam documentos bloqueados neste
lote de 119; isso não implica cobertura anual completa. Totais por ano:
2021: 108; 2022: 78; 2023: 66; 2024: 41; 2025: 25; 2026: 17.

A página já mostra a contagem publicada de cada ano selecionado, os dois
estabelecimentos conferidos e as datas documentais, com aviso de cobertura
parcial. A contagem e a lista compartilham o mesmo gate de aprovação/linhagem;
nenhum total fica preservado quando o documento deixa de estar aprovado.
O coletor local retomável de Outros Pagamentos preserva páginas cifradas antes
da classificação. A prova de 2026 parou após uma página e retomou as cinco
restantes; isso comprova aquisição, não publicação nem cobertura histórica total.

O executor da atualização automática
relê os originais privados, aceita somente acréscimos compatíveis e confere a
projeção pública antes de confirmar a transação SQL. O comando local agora liga
aquisição retomável, validação, importação e controle de execução. Permissões,
agendamento e execução real foram validados conforme o registro abaixo.

Os PRs #736 e #737 foram mesclados. Em 09/09, após autorização explícita, as
quatro funções privadas foram habilitadas para `collector_worker`, sem acesso
direto às decisões. A execução real de 2026 preservou seis páginas, conferiu
17 documentos de dois estabelecimentos, separou três outros programas e terminou
sem pendências ou acréscimos. O banco permaneceu com 335 documentos/19 decisões.
A consulta pública da atualização confirmou estado completo e data da conferência.
A tarefa `Barreiras360-PharmacyRefresh` está instalada para 07:43 diariamente,
sem janela. A execução pelo Windows Scheduler em 09/09 às 10:32 terminou com
código 0 e os mesmos 17 documentos conferidos, sem acréscimos/pendências.
Depende do computador e da sessão Windows disponíveis; cobre o ano corrente.
Histórico e ambiguidades permanecem separados, sem presumir cobertura integral.

As revisões semanais de 2021–2025 também estão registradas: respectivamente
segunda a sexta, às 08:43. A trava é compartilhada entre os anos para impedir
consultas simultâneas em retomadas; o agendador reintenta até três vezes com
intervalos de 15 minutos. A prova agendada de 2025 em 09/09 às 23:05 terminou
com código 0, quatro páginas e 25 documentos conferidos, sem acréscimos ou
pendências; o site confirmou a conferência. Os anos 2021–2024 estão agendados,
mas isso não comprova uma nova conferência desses anos nem cobertura integral.

O adaptador privado `fns_pharmacy_identity` confere CNPJ válido e único no
XLSX oficial preservado, ligado à captura validada do pagamento. Os dois
estabelecimentos do piloto passaram na conferência local em 08/09. Isso não
comprova credenciamento histórico nem autoriza publicação. O reconciliador
privado agora mantém 25 documentos do piloto e identifica 11 consultas de ordens
compartilhadas, sem unir beneficiários. Repetir as capturas conserva 25 documentos.
A migration `20260908173000` prepara snapshots, documentos e decisões privados
e imutáveis, com RPC pública paginada somente para aprovação vigente e evidência
compatível. Retrato novo pendente impede reutilizar aprovação anterior; revogação
retira a projeção. O importador operacional e a rota estão conectados; duas
decisões registram a revisão do lote autorizado. A migration `20260908200000`
acrescenta o MIME XLSX oficial ao bucket, mantendo privacidade e acessos existentes.

O leitor privado `fns_pharmacy_pages` separa Farmácia Popular do piloto
municipal: valida aquisição, página completa e totais, exclui outros programas
da saída e mantém identidade/reconciliação pendentes. Não publica nem soma
pagamentos aos rankings. Ver [caminho de publicação](reviews/FNS_PHARMACY_PUBLICATION.md).

O leitor `fns_payment_evidence` valida um pagamento e sua ordem bancária no
piloto Fundo a Fundo de Barreiras, com autor e solicitante separados. Os dois
pares preservados de 2025 foram processados sem expor campos bancários. Não
há publicação automática, vínculo de pessoa por nome ou soma adicional à CGU.
O reconciliador `fns_cgu_reconciliation` releu o ZIP anual completo da CGU e
encontrou um candidato único para cada um desses dois pagamentos. Ele bloqueia
conflitos e múltiplas linhas e não autoriza publicação. A chave inclui o hash
do arquivo anual: trocar o retrato exige nova reconciliação. A migration
`20260905040239` implementa registro privado de evidências e decisões imutáveis,
com consulta pública limitada a vínculos aprovados que ainda correspondam à
CGU atual. Nova evidência pendente, revogação ou conflito retiram o vínculo da
consulta. Não há alteração nos valores, na autoria coletiva ou nos rankings.
Carga operacional autorizada em 05/09 confirmou **quatro objetos privados,
quatro artefatos registrados e duas evidências reconciliadas**, sem duplicação
dos objetos ou novos lançamentos financeiros. A recaptura reproduziu os quatro
hashes anteriores; os horários registrados são das novas requisições. O ZIP CGU
atual mudou: a reconciliação foi refeita sobre os bytes preservados e conferidos,
sem reutilizar os IDs/linhas antigos. As evidências apontam para esse retrato.
O piloto e sua execução estão `partial`: não representam cobertura anual.
Após confirmação explícita do usuário, foram registradas duas aprovações em
05/09, conferidas na consulta pública: Neto Carletto no documento OB055607
(R$ 5 milhões) e Pedro Lucas Fernandes no OB059959 (R$ 2 milhões), somente como
“Solicitante informado pelo FNS”. A autoria permanece da Comissão da Saúde;
nenhum lançamento, soma ou ranking foi alterado. O PR #704 foi mesclado e os
dois cartões foram conferidos em produção; desktop e celular validados no preview.
A consulta é limitada
aos pagamentos da página e omite vínculos se a evidência CGU mudar.
O leitor `fns_action_catalog` confere as quatro páginas preservadas: 33 linhas,
28 ações positivas e cinco grupos de valor zero. Os totais reconciliam em
centavos. Nenhuma ação é excluída por não conter “EMENDA” no nome. Este é um
plano de detalhamento, não cobertura dos pagamentos. A captura local adicional
preservou 255 registros das outras 26 ações em 27 páginas, agora registrados
como observações privadas, sem publicação. A ação 61659 diverge R$ 1.493,93 do catálogo atualizado:
uma ordem traz cancelamento parcial apesar de anulação numérica zero. As duas
OBs relacionadas foram conferidas em oito páginas, com uma linha de Barreiras
em cada ordem. Não deduplicar nem somar automaticamente; detalhes em
[`FNS_61659_CANCELLATION_AUDIT.md`](reviews/FNS_61659_CANCELLATION_AUDIT.md).
Faltam as demais ordens e a modalidade Outros Pagamentos. Nenhum valor novo no site.
A ação 66458 teve suas nove ordens consultadas: sete pares são documentalmente
compatíveis; 002194 e 005367 retornaram listas vazias no escopo oficial consultado.
O leitor distingue essa ausência de resposta inválida e não a converte em zero
financeiro. As nove capturas foram importadas no Supabase privado em oito
objetos, com replay sem duplicação e releitura dos bytes. A cobertura continua
parcial; nenhuma soma ou atribuição pública foi alterada. Os nove diagnósticos
foram registrados separadamente como `fns_document_comparison`, com hashes e
URLs dos dois lados, sem sobrescrever as observações originais. O replay inseriu
zero comparações adicionais. Não há aprovação financeira nem leitura pública
desse novo tipo de registro. Ver
[conferência do lote](reviews/FNS_66458_ORDER_AUDIT.md).
O leitor privado de atualidade confere hashes e aquisição mais recente por
consulta, bloqueando versões antigas, conflitos e mudança de paginação. Uma
auditoria SQL somente leitura encontrou as nove comparações correspondentes
ao acervo preservado atual (57 artefatos examinados). Não é nova consulta ao
FNS nem confirmação de execução financeira; ainda não há tela para esse estado.
O comando `audit_fns_comparisons --action-id 66458 --payment-year 2025`
agora executa essa leitura com configuração PostgreSQL existente, transação
somente leitura e histórico consistente. Validado no banco: nove versões
atuais, sete compatíveis e duas ausências; saída `needs_attention` e código 2.
Sem mudança de dados, tela pública ou workflow agendado nesta etapa.
A conferência privada das 14 ordens da ação 62079 (SAMU 192) no retrato
preservado de pagamentos de 2025 foi concluída: 340 páginas de ordens
importadas e 14 comparações atuais e documentalmente compatíveis. A auditoria
independente derivou as 14 ordens do pagamento original, releu 341 objetos,
conferiu hashes e metadados e não encontrou ordens ausentes nem comparações
repetidas. Os lotes adicionais tiveram replay sem novas comparações.
O fechamento vale para esse retrato, não para cobertura anual de todo o FNS
ou execução financeira. Os controles dos lotes continuam `partial` e a
publicação permanece bloqueada. Não houve alteração de valores, autoria ou
rankings públicos. Competências repetidas não foram deduplicadas por data.
Ver [conferência SAMU](reviews/FNS_62079_SAMU_CAPTURE.md).
O diagnóstico `fns_order_pages` agora lê todas as páginas de uma OB e distingue
ausência de Barreiras, ambiguidade, conflito territorial, resposta inválida e
revisão por rejeição. Validado nas oito páginas preservadas: 016551 exige revisão;
018794 tem linha territorial única. Ambos continuam sem autorização de publicação.
O leitor não substitui a validação do par nem comprova sozinho a identidade da OB;
o chamador deve vincular URLs/escopo aos originais antes de integrá-lo ao coletor.
O adaptador `inspect_order_captures` confere URL final oficial, parâmetros da
ordem e competência, página, tamanho solicitado, HTTP e SHA-256 dos bytes.
Mistura de escopos e parâmetros duplicados são recusados. Ainda depende de
metadados capturados pelo transporte confiável; não grava nem publica pagamentos.
O registrador `FNSOrderPersistenceService` usa esse diagnóstico, valida os
metadados de aquisição e relê todos os objetos antes da primeira gravação.
Registra apenas artefatos privados, com replay idempotente e cobertura parcial,
inclusive quando a ordem exige revisão. Não cria registros financeiros.
A releitura local dos oito originais confirmou os hashes e os diagnósticos,
mas os manifestos antigos não registram URL final. Uma nova captura das oito
páginas registrou os metadados completos e reproduziu todos os hashes. O serviço
validou ambas as ordens em simulação. A importação privada subsequente registrou
oito objetos e oito artefatos; o replay retornou os mesmos IDs. Releitura do
Storage e consulta SQL independente confirmaram hashes, tamanhos e URLs.
A execução `e6fe9f01-8641-4cbf-8378-577a96e655d4` permanece `partial`, com zero
registros financeiros e nenhuma autorização de publicação. A OB 016551 continua
em revisão; a 018794 não foi convertida em pagamento público. Nenhuma data ou URL
antiga foi preenchida por suposição. Esses oito artefatos não representam cobertura anual.
O normalizador privado `fns_payment_pages` foi executado localmente nas 27
páginas: preservou as 255 observações das 26 ações, identificou sete competências
de ano diferente do pagamento e manteve a rejeição da ação 61659 em revisão.
Nenhuma chave documental repetida apareceu nesse recorte; IDs compostos iguais
não causaram exclusão de linhas. Valores são somas documentais, não confirmação
de transferência; todas as ordens continuam pendentes de vínculo nessa saída.
A saída foi persistida privadamente, sem publicação, e não resolve a divergência
entre o catálogo e o detalhe da ação 61659.
O comparador `fns_document_link` releu o pagamento e as páginas de cada OB:
016551 (linha 7) continua em revisão; 018794 (linha 9) apresenta par documental
consistente em escopo, competência e valor. Ambos seguem sem publicação.
O normalizador agora também exige ação embutida, esfera municipal e modalidade
Fundo a Fundo compatíveis; os 255 registros passaram nessa verificação.
As 27 páginas foram recapturadas com metadados completos e hashes idênticos.
A execução `b78dc03f-bf5d-43d6-8438-66a29234ed55` registrou 27 objetos, 27 artefatos
e 255 observações privadas. O replay inseriu zero registros e manteve os IDs;
download e SQL conferiram bytes, hashes e payloads. Cobertura permanece parcial,
ordens pendentes e `publication_allowed=false`. Falta obter/conferir as demais
ordens e registrar os resultados dos vínculos, sem transformar compatibilidade
documental em confirmação de pagamento ou autoria.
Escopo e limitações em
[`FNS_2025_SOURCE_DISCOVERY.md`](reviews/FNS_2025_SOURCE_DISCOVERY.md).

## O que já está disponível no portal

- Diário Oficial com busca global, paginação, edição permanente, texto literal,
  páginas, fonte e hashes;
- atos oficiais aprovados com evidência e canal público de correção;
- receitas, despesas, fechamentos, obrigações e folha em agregados validados,
  com matriz pública mensal de cobertura de receitas e despesas desde 2021 e
  mapa de fontes que preserva as cadências mensal, bimestral, quadrimestral e
  anual sem criar uma taxa global enganosa; restos a pagar também possuem
  matriz mensal própria, e receitas, obrigações e folha recarregam sua cobertura
  em tempo real quando o HTML inicial não recebe a fonte;
- licitações, processos, contratos, itens, fornecedores e recortes do PNCP;
- leis e proposições da Câmara com autoria publicada e aliases revisados;
- Executivo, vereadores, representantes estaduais e federais, candidaturas e
  votos em Barreiras separados por eleição, cargo e turno;
- emendas e transferências federais e estaduais, mantendo autorização,
  empenho, transferência e pagamento como estágios distintos;
- painel administrativo de revisão, cobertura e falhas das fontes.

## Limitações que permanecem explícitas

- auditoria de 04/09 reproduziu e corrigiu falso avanço do monitor público nos
  primeiros seis dias, término com horário congelado e aceitação de histórico
  ou payload de saúde incoerente; a nova migration preserva o histórico existente;
- o gate de sete dias exige vinte sondagens **agendadas** por dia encerrado.
  Disparos manuais não preenchem essa cobertura. Atrasos do GitHub Actions
  continuam visíveis como cobertura insuficiente, não como disponibilidade comprovada;

- cobertura histórica varia por fonte; período não classificado não pode ser
  apresentado como vazio;
- parte da execução estadual antiga não possui chave oficial suficiente para
  ligação única com as autorizações territoriais;
- o catálogo mensal do TCM-BA é uma fonte privada em validação e não autoriza,
  sozinho, publicar valores financeiros;
- o formulário do e-TCM expirou em todas as tentativas feitas por runners
  hospedados; sua retomada mensal automática usa o executor Windows validado,
  enquanto o GitHub permanece apenas como replay manual e diagnóstico;
- o CDN oficial do TSE passou a responder HTTP 403 a requisições automatizadas
  em runners hospedados; os recortes privados de 2022 e 2024 foram importados
  com sucesso em 18/08/2026, mas o arquivo de 2024 marcou os 20 CPFs do recorte
  como não divulgáveis; o job só repete o download se aparecer uma candidatura
  aprovada ainda sem evidência, sem usar espelho não oficial;
- a API complementar do Querido Diário permanece sujeita a timeout TLS; essa
  indisponibilidade gera aviso e DLQ próprios, enquanto catálogo e PDFs oficiais
  continuam obrigatórios e qualquer falha neles encerra a execução;
- o Transferegov atual reconcilia contagem, contrato e a impressão SHA-256 do
  conjunto normalizado com a projeção pública; cada exercício possui membership
  versionado, de modo que uma linha retirada da fonte sai da visão atual sem
  apagar o histórico bruto; a prova não expõe payloads nem chaves individuais;
- fatos literais aprovados podem ser automáticos, mas identidade ambígua,
  conflito entre fontes e interpretação reputacional exigem revisão;
- o portal continua marcado como pré-lançamento até os gates operacionais e de
  experiência abaixo serem comprovados.

## Gates prioritários

1. Saúde real: endpoints públicos, falhas e cobertura não podem depender de
   respostas estáticas nem selos verdes isolados.
2. Cobertura desde 2021: cada partição deve terminar como completa, vazia,
   parcial, falha ou bloqueada — nunca desconhecida por omissão.
3. Experiência pública: nenhuma página deve transbordar no celular; listas
   grandes usam paginação e carregam o inteiro teor somente no detalhe.
4. Rastro do dinheiro: relacionar origem, órgão, empenho, liquidação, pagamento,
   contrato, fornecedor, objeto e parlamentar somente por chaves oficiais.
5. Evidência: todo total, ranking e aviso de ausência precisa permitir conferir
   fonte, período, metodologia e documento.
6. Prontidão: sete execuções agendadas consecutivas sem falha não tratada,
   sete dias sem HTTP 500 público e CI completo verde antes do lançamento.

## Evidências operacionais recentes

- Auditoria de 04/09: [achados, correções e prioridades](reviews/AUDIT_2026_09_04.md).
  Monitor corrigido e verificado em produção; fontes federais independentes não
  são mais suprimidas por erro do catálogo histórico. A linguagem do Diário
  diferencia consulta indisponível, busca vazia e catálogo sem texto publicado.

- Em 04/09/2026, começou a medição prospectiva do gate de sete execuções
  agendadas do dreno documental do TCM-BA. Cada execução passa a registrar no
  início se veio do Agendador do Windows, do GitHub Actions ou de operação
  manual, inclusive quando falha. O painel só conta lotes identificados como
  Windows Scheduler que baixem de um a dez PDFs e recomponham exatamente os
  contadores do catálogo. O histórico anterior não recebe origem presumida.
- Em 04/09/2026, a drenagem física dos PDFs mensais do TCM-BA avançou de 96
  para 287 documentos preservados em `02/2021`, de um catálogo oficial com
  1.505 itens. A tarefa Windows permaneceu habilitada, serial, limitada a dez
  PDFs por rodada e 30 requisições por minuto. O painel administrativo passou
  a projetar esses contadores como progresso documental sanitizado; catálogo
  completo e download físico parcial continuam estados distintos.
- Em 04/09/2026, a recuperação privada dos candidatos de empenho do TCM-BA
  eliminou a fila histórica: 1.360 de 1.360 PDFs elegíveis foram processados,
  sem ausência, duplicidade, payload inválido ou falha aberta. Dos 242
  candidatos, 14 possuem os quatro campos estritos e 228 permanecem privados
  por informação ausente ou ambígua. O agendamento documental conserva 30
  requisições por minuto, processamento serial e auditoria física, mas passa a
  aceitar até dez documentos por rodada para acelerar a cobertura desde 2021.
- Em 02/09/2026, a tarefa local `Barreiras360-TCMBA-MonthlyCatalog` foi
  instalada para execução diária às 06:17, sem sobreposição e com limite de 30
  requisições por minuto. A primeira verificação autenticada classificou
  agosto de 2026 como `blocked`: o e-TCM ainda não publicou a competência no
  seletor público. Nenhum documento ou valor zero foi fabricado, e a tarefa
  repetirá a consulta diariamente.
- Em 02/09/2026, a execução `33591332973` do Diário passou pelas duas fontes
  oficiais e organizou três edições em 29 documentos integrais e 93 páginas,
  com zero falha de segmentação. A fila otimizada não repetiu o timeout SQL das
  duas execuções agendadas anteriores. A API complementar falhou no handshake
  TLS e foi preservada separadamente, sem contaminar o resultado oficial.
- Na execução `33590214819` da representação, os recortes privados de 2022 e
  2024 reconheceram 20 pessoas já evidenciadas em cada eleição e encerraram sem
  repetir o download bloqueado pelo CDN do TSE.
- Em 04/09/2026, a execução `33828931185`, no SHA `bb37f6c`, comprovou o novo
  gate das fontes federais. A projeção pública reconciliou 15 linhas de execução
  da CGU entre 2014 e 2023, quatro autores classificáveis, 232 documentos entre
  2021 e 2026 e 12 autores documentais. O Transferegov classificou separadamente
  os seis exercícios de 2021 a 2026: somente 2025 apresentou três transferências
  públicas; os demais permaneceram vazios, sem herdar registros antigos. O gate
  também recalculou a ordem dos rankings e bloqueou qualquer RPC truncada.
- Em 04/09/2026, o gate federal passou a exigir também a contagem e a impressão
  SHA-256 exatas dos registros normalizados de cada exercício do Transferegov.
  A impressão é calculada sobre tipo, chave oficial e hash do payload tanto no
  coletor quanto na projeção pública. Assim, uma linha antiga que permaneça na
  projeção, uma linha nova omitida ou um payload divergente bloqueia a
  publicação, mesmo quando os totais públicos coincidem. A RPC de evidência
  expõe somente ano, estado, contagem, hash, data, fonte e metodologia.
- Em 04/09/2026, a projeção atual do Transferegov recebeu manifestos privados
  versionados. Um retrato em andamento não altera o portal; se a execução
  falhar, ele é abandonado, e, se concluir, substitui atomicamente o anterior.
  A migração preserva o estado público existente antes de trocar a view e não
  exclui qualquer registro bruto.
- Em 04/09/2026, a execução de produção `33836165380`, no SHA mesclado
  `bd182a5`, comprovou o contrato novo. Os seis exercícios de 2021 a 2026
  receberam snapshots ativos; 2025 reconciliou 17 registros normalizados e
  os outros cinco anos permaneceram vazios na API atual. O gate público
  conferiu 15 linhas de execução da CGU, 232 documentos federais e os seis
  snapshots antes de encerrar verde. A resposta rápida do portal passa a
  mostrar diretamente o estado e a hora da conferência do ano selecionado.

## Próximo fluxo vertical

O pacote inicial de prontidão pública — saúde operacional real, índice leve do
Diário, inteiro teor permanente, correções responsivas e página pública de
estado — está implementado. A matriz mensal de receitas e despesas e o mapa das
famílias financeiras também estão publicados, distinguindo cobertura
classificada de documento apenas observado e preservando a periodicidade de
obrigações, folha, RREO, RGF e DCA. Restos a pagar e folha agora têm matrizes
mensais navegáveis, atualização em tempo real e acesso contextual à fonte de
cada estado; estagiários e terceirizados continuam separados da folha agregada.
RREO e RGF agora têm calendário público próprio desde 2021: seis bimestres do
RREO e três quadrimestres do RGF por exercício, com distinção entre PDF
preservado, registro apenas catalogado, período vencido não localizado e prazo
ainda aberto. A regra fica visível com links ao Siconfi e ao IBGE, e a página
reconsulta as duas famílias em tempo de execução se o HTML inicial não obtiver a
fonte. A DCA permanece uma trilha anual separada e agora possui matriz pública
desde 2021. A consulta de produção de 01/09/2026 encontrou declarações completas
de 2021 a 2025, com sete métricas validadas em cada exercício; 2026 aparece como
exercício em andamento, não como ausência ou valor zero. A auditoria da série
municipal `pdc-contas-anuais` comprovou que seus seis registros únicos são leis
e fundamentos de controle, não demonstrativos anuais. A interface agora separa
essa base legal da DCA. Quatro DOCX oficiais já estão preservados, tiveram o hash
do arquivo conferido e o texto literal extraído de forma idempotente. A nova
consulta pública pagina apenas esses textos verificados, carrega o inteiro teor
somente no detalhe e mantém fonte oficial e hashes visíveis; os dois registros
somente catalogados continuam identificados como tal, sem conteúdo inventado.
O próximo fluxo é provar essa projeção em produção e retomar a reconciliação
apenas entre fontes que expressem o mesmo conceito e período.

Os documentos financeiros mensais agora também possuem calendário público
próprio desde 2021, comparando Balancete, Execução da Receita e Execução da
Despesa por competência. A consulta de 01/09/2026 encontrou 230 registros no
acervo completo dessas três famílias: 229 PDFs preservados e um documento de
despesa somente catalogado. Sete competências desde 2021 possuem mais de uma
versão observada; elas são identificadas como versões, nunca somadas. A matriz
falha fechada se qualquer família estiver indisponível e descreve lacuna apenas
como documento não localizado no catálogo preservado consultado, nunca como
valor zero. A lista textual foi reduzida aos 36 documentos mais recentes; o
calendário mantém o acesso histórico por competência. O primeiro recorte de
reconciliação encontrou uma lacuna material em todo o ano de 2022: Receita e
Despesa tinham PDFs preservados, mas o layout analítico por fonte da Receita não
era reconhecido. O parser agora separa o código de fonte colado ao último valor,
agrega parcelas do mesmo código apenas quando a descrição coincide e mantém
conflito explícito quando não coincide. Os doze PDFs oficiais de 2022 passaram
pelo parser corrigido. O publicador também deixou de ignorar falhas para sempre
e não pode mais encerrar verde com documentos em `needs_review`. Em 01/09/2026,
o replay controlado foi concluído: os doze fechamentos mensais estão
`operational` no RPC público, cada um com um relatório de receita, 281 rubricas
de receita e um relatório de despesa. A conferência do detalhe mensal também
comprovou URLs oficiais e hashes de linhagem para os documentos de receita e
despesa. A lacuna de abril de 2023 possuía receita publicada, mas ainda não
fechava a despesa mensal. A auditoria da primeira fonte encontrou o registro
oficial, porém a URL publicada redirecionava para o login administrativo e não
entregava um PDF. O coletor passou a oferecer resgate por competência e a
falhar explicitamente se o documento exato não pudesse ser preservado,
eliminando o antigo falso verde dessa operação direcionada.
A busca na segunda fonte oficial também deixou de depender da ordem genérica da
fila: a linhagem pelo hash e pela categoria `PCMGE015` reconhece somente a cadeia
registro -> preparação -> PDF oficial e rejeita documentos de outra família. O
demonstrativo de abril de 2023 passou por 184 páginas, 2.655 linhas e 25 unidades
sem divergência contábil; seu resumo foi publicado e o fechamento público está
`operational`, com uma receita, uma despesa, URLs e hashes verificáveis. A
interface identifica o TCM-BA como fonte oficial distinta do portal municipal.
O comando local de publicação exata exige um SHA-256, um único relatório e zero
falha; lote vazio não recebe selo de sucesso.

Em 01/09/2026, o mesmo gate fechou janeiro e fevereiro de 2021 com os pares
oficiais `PCMGE015` e `PCMGE016`. Janeiro possui um relatório de receita, 248
rubricas e um relatório de despesa. Fevereiro possui um relatório de receita,
253 rubricas e um relatório de despesa. O PDF de receita de fevereiro comprovou
que o SIGA imprime anulações com sinal negativo; a metodologia
`tcm-ba-analytical-revenue/1.1.0` passou a aplicar a soma algébrica e a rejeitar
anulações positivas nesse leiaute. O quadro-resumo oficial fechou em
R$ 45.849.799,31 líquidos no mês e R$ 110.933.618,91 acumulados. A RPC pública
de fevereiro está `operational`: R$ 34.412.345,07 empenhados,
R$ 37.885.590,11 liquidados, R$ 35.611.012,38 pagos e diferença operacional de
R$ 10.238.786,93, expressamente não tratada como superávit fiscal. Os dois meses
mantêm URLs oficiais e hashes distintos de receita e despesa para conferência.
Disparos manuais dos publicadores de receita — e de despesa quando o escopo é
explicitamente `expenses` — falham se não houver artefato elegível. Uma rotina
agendada sem pendência continua sendo um `no-op`, não uma falha da fonte.

Março de 2021 também foi fechado pelo mesmo caminho exato. O demonstrativo de
receita `PCMGE016`, hash
`801a3453c993655f67ecaa3d386ede1408f3e56f93af9b81ae52d55d645cb1de`,
publicou 253 rubricas e R$ 41.163.050,37 líquidos no mês. O demonstrativo de
despesa `PCMGE015`, hash
`736629dee3e3b048922dc797b90be73c867011ab06281e12d27362c5168cedfa`,
possui uma única linhagem oficial e publicou R$ 10.165.224,76 empenhados,
R$ 37.659.408,60 liquidados e R$ 38.079.191,26 pagos. A RPC pública está
`operational`, com diferença operacional de R$ 3.083.859,11, expressamente não
tratada como superávit fiscal. A página pública foi conferida após a
revalidação e contém os dois hashes oficiais.

Abril de 2021 foi fechado em seguida. O `PCMGE016`, hash
`a03473494c68539b9dcb3f4a5e937c8c87fb54d1a947b7198d58ccb341500b41`,
publicou 253 rubricas e R$ 44.375.565,85 líquidos no mês. O `PCMGE015`, hash
`940264e715a77bc79a8936edfe030d0b78c8bb4911c2e78b5e515b415bf8f4fe`,
possui 184 páginas com texto embutido, uma única linhagem oficial e zero
pendência de revisão. O fechamento público está `operational`, com
R$ 14.765.663,26 empenhados, R$ 36.366.146,44 liquidados,
R$ 38.361.003,05 pagos e diferença operacional de R$ 6.014.562,80. O RPC e a
página pública contêm os dois hashes e as URLs oficiais.

Maio de 2021 completou a sequência. O `PCMGE016`, hash
`7d30f74cd109be527e4e0f3348bc42246073a9c79c3892b15a431c271d12d057`,
publicou 253 rubricas e R$ 43.876.720,05 líquidos. O `PCMGE015`, hash
`76dcf9924fdc997545a4747ee8325cd6741c4acfb080b1fc2b7692f64e1905c4`,
possui 188 páginas com texto embutido e uma única linhagem oficial. O detalhe
público está `operational`, com R$ 14.728.786,14 empenhados,
R$ 42.783.737,60 liquidados, R$ 36.046.119,18 pagos e diferença operacional de
R$ 7.830.600,87. O RPC e a página pública exibem os dois hashes oficiais.

Junho de 2021 também está `operational`. O `PCMGE016`, hash
`d786cec704c19bc74f28df3bf3ae9fe1085b39597940cb13c56ad28e332ad269`,
publicou 253 rubricas e R$ 42.715.255,06 líquidos. O `PCMGE015`, hash
`77993ec0980b45059746d7c4a981dabc868390699756f27bb7a617f5766e40f2`,
possui 191 páginas com texto embutido e uma única linhagem oficial. O detalhe
mostra R$ 26.263.437,98 empenhados, R$ 42.635.614,97 liquidados e
R$ 46.240.117,71 pagos. A diferença operacional é negativa em
R$ 3.524.862,65 e não recebe rótulo de déficit ou irregularidade. Uma primeira
chamada direta do RPC atingiu o timeout; o retry imediato respondeu em 1,19 s,
e a página pública permaneceu disponível com os dois hashes. A ocorrência deve
continuar monitorada, sem ser ocultada pelo cache da aplicação.

Julho de 2021 está `operational` com os dois documentos oficiais. O
`PCMGE016`, hash
`5adaf8beff64b177aaf647d50b49768532ecea9063f26aef871f1c04f17735bd`,
publicou 253 rubricas e R$ 45.999.611,58 líquidos. O `PCMGE015`, hash
`5b914f82c687dc320dbb1311dcc0db8d73479250c5ce55a5333f3aeaf52f0682`,
possui 193 páginas com texto embutido e uma única linhagem oficial. O detalhe
mostra R$ 25.912.406,60 empenhados, R$ 48.284.964,74 liquidados e
R$ 48.806.026,83 pagos. A diferença operacional é -R$ 2.806.415,25, sem
inferência de déficit ou irregularidade. O RPC respondeu em 3,26 s e a página
pública apresentou os dois hashes e estado operacional.

Agosto de 2021 foi fechado sem recorrer a contagem esperada zero: o catálogo
oficial possui 1.901 documentos e a recuperação dirigida preservou somente os
dois demonstrativos necessários. O `PCMGE016`, hash
`4ef96cb127ee9ef28336dc65def6768b6db386ffb6e2f963bb41f72c41152109`,
publicou 257 rubricas e R$ 48.274.758,65 líquidos. O `PCMGE015`, hash
`f89462d45ee0b8af43ef72410f9163c25860d9727940922c376dc019af17f755`,
possui 195 páginas com texto embutido e uma única linhagem oficial. O detalhe
está `operational`, com R$ 26.576.384,38 empenhados,
R$ 49.861.914,42 liquidados, R$ 48.795.152,19 pagos e diferença operacional de
-R$ 520.393,54, sem inferência fiscal. O RPC respondeu em 3,25 s e o HTML
público contém os dois hashes.

Setembro de 2021 está `operational`. O `PCMGE016`, hash
`b13747c202d73705512460b3be77e2a9609e4d21a178ed673387dbec6045aab8`,
publicou 257 rubricas e R$ 44.763.733,75 líquidos. O `PCMGE015`, hash
`82f79a0a2609f2173b2357f8e48b7e0473fa411345d45df113f5c662fd806573`,
possui 198 páginas com texto embutido e uma única linhagem oficial. O detalhe
mostra R$ 15.701.545,06 empenhados, R$ 46.068.615,27 liquidados e
R$ 49.096.461,68 pagos. A diferença operacional de -R$ 4.332.727,93 não recebe
interpretação fiscal. O RPC respondeu em 2,96 s e a página pública exibiu os
dois hashes e o estado operacional.

O quarto trimestre completou a cobertura financeira mensal de 2021. Em outubro,
os hashes oficiais de receita e despesa são, respectivamente,
`e26c1bac553193c5094d2dd6ae532c744ee43bc58342e4369b313e01e479e0b8` e
`40e32b553abfcba6758caeb2cc2a8923adb700548b1b3047bb5b7c16fba4ed79`.
O detalhe publicou 257 rubricas, R$ 60.168.967,09 de receita líquida,
R$ 31.445.477,25 empenhados, R$ 49.132.763,62 liquidados e
R$ 49.397.681,61 pagos. Em novembro, o catálogo foi fechado como `complete`
com 1.941 documentos. Os hashes
`343271fcf5816997494a9764a501a8b46cb231673ba89325965d19b4b37afb03` e
`7ca53ea083ff9bec242758c898e0c1adddc23027772b744086ccf20ae1cef29c`
publicaram R$ 49.571.690,49 de receita líquida, R$ 17.452.174,63 empenhados,
R$ 50.943.193,81 liquidados e R$ 48.221.282,65 pagos. Em dezembro, os hashes
`9b5e6b498f2f192b532ae9b7658b49d970e1b44367a9dbadaf230334a0ac044e` e
`938b9f3ebd98cebf985035de3efcf95eebdf31bf4fd38ade55b228efcfe43cb4`
publicaram R$ 75.029.545,36 de receita líquida, R$ 42.384.090,96 empenhados,
R$ 88.780.398,98 liquidados e R$ 81.717.613,72 pagos. Os três meses estão
`operational`, com um documento de cada tipo e páginas públicas em HTTP 200.

Novembro comprovou outra variação oficial do SIGA: as categorias de primeiro
nível podem possuir simultaneamente saldo `a maior` e saldo `a menor`, enquanto
o total geral apresenta apenas o saldo líquido consolidado. A metodologia
`tcm-ba-analytical-revenue/1.2.0` preserva a igualdade exata das quatro colunas
financeiras básicas, valida cada saldo individual e exige que `a maior - a menor`
seja idêntico entre categorias e total. Não há compensação silenciosa de
receita ou anulação. O replay exato de texto por SHA também passou a reler e
revalidar um PDF já processado sem duplicar o job.

A auditoria transversal de 2021 retornou `PASS` em 12 de 12 competências. Cada
mês tem exatamente um relatório e um documento oficial de receita e despesa,
valores não nulos e estado `operational`. Os 24 artefatos possuem 24 hashes
distintos, tamanho positivo, HTTP 2xx, MIME PDF e zero job financeiro aberto ou
falho. As doze rotas `/financas/2021-MM` responderam HTTP 200 e identificaram a
competência solicitada. Esses snapshots mensais não foram somados como total
anual, pois representam estágios e conceitos cuja agregação exige metodologia
própria.

Após a mesclagem desse fechamento, a API pública foi consultada novamente em
01/09/2026. A matriz confirmou 60 de 60 competências `complete` entre janeiro
de 2021 e dezembro de 2025, sempre com um relatório de receita e um de despesa.
Em 2026, sete competências estavam completas. Agosto permanecia sem relatório
validado e setembro aparecia da mesma forma, embora a competência ainda estivesse
em andamento. A interface agora converte somente a ausência da competência
corrente ou futura em `not_due`; lacunas anteriores, relatórios parciais e
registros em revisão continuam visíveis. Assim, falta de publicação não é
antecipada antes do fim da competência nem convertida em valor zero.

Em 02/09/2026, a série documental federal da CGU foi retirada do HTML integral
da aba de execução. A API pública confirmou 232 movimentos entre 2021 e 2026 e
agora entrega no máximo 25 por página, com busca e filtros de ano do documento,
autoria e fase financeira calculados sobre todo o catálogo. O ranking permanece
em consulta separada e nenhum total, estágio ou fonte foi combinado para obter
essa redução de payload. O carregador comum de Recursos também passou a respeitar
a aba escolhida: execução da CGU e comparação por legislatura não disparam a
carga legada das demais fontes; federal atual, arquivo histórico e Bahia consultam
somente suas próprias famílias. Uma falha de uma origem deixa de atrasar ou
ocultar outra origem que esteja saudável.

Na mesma data, o detalhamento estadual deixou de carregar até 200 autorizações
e outras 200 linhas de execução em toda abertura. Uma RPC única passou a
entregar somente 12 autorizações visíveis e as ligações de execução que
pertencem a elas, enquanto ranking e resumo continuam calculados no universo
completo e em consultas separadas. A conferência viva de 2026 encontrou 34
autorizações, distribuídas em páginas de 12, 12 e 10 registros, sempre com a
mesma quantidade de linhas correspondentes da execução. Autorização,
empenho, liquidação e pagamento continuam sem soma entre estágios.

Em 03/09/2026, o estudo estadual recebeu busca textual e filtros server-side por
parlamentar e situação da execução. A busca ignora caixa e acentos e exige que
todos os termos estejam presentes, mesmo quando há palavras intermediárias. A
conferência viva de 2026 manteve 34 autorizações no catálogo, sete autores e dez
autorizações com execução confirmada; `Marcone Amaral` mais `ônibus escolar`
retornou somente a emenda 5724. A interface distingue a quantidade filtrada do
acervo anual, e os filtros não alteram o ranking nem os totais financeiros do
ano.

Também em 03/09/2026, a auditoria das 24 autorizações de 2026 sem ligação
individual separou três situações. Quatorze emendas, somando R$ 750.200,00
autorizados, formam quatro chaves cujas ocorrências estaduais pertencem
integralmente a Barreiras; a execução pode ser mostrada somente para cada grupo,
sem rateio por emenda e sem entrar no ranking individual. Outras sete emendas,
somando R$ 850.600,00 autorizados, dividem cinco chaves com outros municípios e
continuam bloqueadas. Três emendas para o Ministério Público, somando
R$ 700.000,00 autorizados, não aparecem no retrato de execução consultado; a
interface registra ausência na fonte, nunca valor zero.

Ainda em 03/09/2026, a validação pública dessa entrega revelou timeout nas
consultas estaduais: a view da LOA aceitava duas versões do extrator, mas os
índices existentes cobriam cada versão separadamente, levando o PostgreSQL a
varrer aproximadamente 55 mil resultados JSON por requisição. Um índice parcial
combinado e outro para os pagamentos estaduais especiais reduziram, na medição
viva, o estudo da LOA de cerca de 2,4 s para 190 ms, o ranking da LOA de 3,6 s
para 246 ms e os pagamentos especiais de 2,1 s para 127 ms. A página pública
voltou a responder sem o aviso de indisponibilidade e passou a exibir os quatro
grupos de execução, sem alterar contratos nem valores de origem.

A fonte normalizada da LOA estadual agora também possui snapshot privado e
indexado, atualizado pelo mesmo worker antes da reconciliação. Em 03/09/2026,
a fonte canônica, o snapshot e a projeção estável apresentaram os mesmos 70
registros e o mesmo SHA-256 do conteúdo integral ordenado; a reconciliação
manteve 70 linhas e quatro grupos. Cada atualização confere contagem e hash e
aborta com rollback se houver divergência. Os testes também simulam perda de
linha e alteração de valor, preservando a última versão íntegra nesses casos.
Nas medições SQL individuais, o estudo de 2026 caiu de cerca de 190 ms para
22,6 ms e o ranking de 246 ms para 34 ms; esses tempos não representam a
latência total da página. O catálogo de 2026 mantém 34 autorizações, sete autores
e a emenda 5724 de Marcone Amaral com R$ 1.548.747,00 **autorizados**, sem
reclassificação como pagamento.

Os pagamentos estaduais especiais também passaram a usar snapshot privado e
indexado, atualizado na mesma transação da extração, inclusive nos replays
idempotentes. A migração `20260903170000` foi aplicada em 03/09/2026 após testes
e duas revisões independentes. A conferência viva manteve três pagamentos e
SHA-256 integral idêntico entre fonte canônica, snapshot e view estável.
Um replay isolado posterior preservou um novo ZIP oficial, mas manteve os mesmos
três candidatos e o mesmo SHA-256 semântico
`8170ec6f3937fe6b24c6ca9936209e6525d3b98c4710139998358509e96636ae`.
Nos três pagamentos, somente o hash do arquivo-fonte e a data da coleta
mudaram. A migração `20260903233000` separa esses dois sinais no evento de
auditoria: o hash semântico identifica mudança nos fatos, enquanto o hash de
linhagem comprova a cópia exata de cada nova preservação.
O ranking conserva os três pagamentos de 2022 relacionados a duas emendas de
Tito, somando R$ 756.904,75 **pagos pelo Estado da Bahia**, cujo objeto menciona
Barreiras. Isso não comprova recebimento pela Prefeitura nem entrega de obras,
e não é somado à LOA, à CGU ou ao Transferegov. Autoria e vínculos federais
continuam consultados dinamicamente. Nas medições SQL individuais, a consulta
de pagamentos passou de 41,9 ms para 12 ms e o ranking de 16,7 ms para 1,5 ms;
esses tempos não medem a página inteira. A página de Recursos respondeu HTTP
200 com os valores e a seção próprios preservados.
Em 03/09/2026, a etapa estadual recebeu um gate público depois de cada
normalização. A execução não pode mais terminar verde apenas porque preservou
ou processou um arquivo: ela consulta novamente as RPCs sem cache e exige
cobertura estadual válida, os mesmos exercícios entre LOA e execução e
reconciliação exata entre cobertura anual, pagamentos e ranking das
transferências especiais. O hash publicado pela execução e pelos pagamentos
precisa ser o mesmo do arquivo que o coletor acabou de baixar; na LOA, os seis
estados anuais e a hora da tentativa precisam corresponder à execução atual.
Um PDF da LOA preservado sem linha territorial pode aparecer como `empty`,
sem ser confundido com fonte bloqueada. Pagamentos e ranking são lidos por
paginação determinística, portanto o gate não fica limitado aos primeiros 200
pagamentos ou 50 autores. Nenhum nome ou valor foi fixado no código. A prova
viva anterior à mesclagem
encontrou seis exercícios estaduais, 4.234 registros agregados na fonte de
execução, três pagamentos territoriais em um ranking e cinco exercícios da LOA
observados; 2021 continuou bloqueado, sem virar zero. O próximo fluxo menor é
executar os modos estaduais após a mesclagem e conservar como evidência os
eventos do novo gate, antes de estender a mesma prova às demais fontes.
Na primeira execução controlada, o catálogo estadual ficou indisponível nas
quatro tentativas; na repetição, a preservação terminou, mas a seleção da fila
de normalização excedeu os 15 segundos permitidos pela role. A consulta passou
a exigir resultado válido do tipo correto e recebeu índices parciais para ZIP,
manifesto e estado do job, evitando varredura integral do acervo.
