# Estado atual do Barreiras 360

Atualizado em **02/09/2026**. Este é o ponto de entrada operacional; o histórico
de decisões e entregas permanece em `docs/ROADMAP.md` e `docs/adr/`.

## Fase atual

O projeto está em **estabilização do pré-lançamento e construção do rastro do
dinheiro**. A fundação, a coleta preservada do Diário e as primeiras projeções
públicas de atos, finanças, compras, Legislativo e representação já existem.
O trabalho atual não é abrir outra fase ampla: é tornar cobertura, qualidade,
desempenho e leitura pública confiáveis antes do lançamento divulgado.

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
