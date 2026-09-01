# Estado atual do Barreiras 360

Atualizado em **01/09/2026**. Este é o ponto de entrada operacional; o histórico
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
despesa. A próxima lacuna objetiva é abril de 2023, que possui receita publicada
mas ainda não fecha a despesa mensal. A auditoria da fonte encontrou o registro
oficial dessa despesa, porém a URL publicada redireciona para o login
administrativo e não entrega um PDF. O portal mantém o mês como `needs_data`,
sem aproveitar como valor a descrição do catálogo. O coletor agora oferece
resgate por competência e falha explicitamente se o documento exato não puder
ser preservado, eliminando o antigo falso verde dessa operação direcionada.
A busca na segunda fonte oficial também deixou de depender da ordem genérica da
fila: a linhagem pelo hash provou que o demonstrativo TCM-BA antes disponível é
de janeiro de 2021, e a coleta documental agora pode exigir simultaneamente a
competência e o código oficial `PCMGE015`. O próximo passo operacional é
preservar esse documento para abril de 2023 e só então comparar sua metodologia
com o demonstrativo municipal ausente. O documento exato já foi preservado e
seu parser SIGA passou por todas as 184 páginas, 2.655 linhas e 25 unidades sem
divergência contábil. A linhagem exata TCM-BA agora reconhece somente a cadeia
registro `PCMGE015` -> preparação -> PDF oficial e rejeita documentos de outra
família. O publicador usa todas as linhas para reconciliar os totais, mas mantém
as descrições analíticas fora da projeção enquanto o texto da fonte contiver
caracteres corrompidos. A próxima operação é aplicar essa migration, publicar
apenas o resumo validado de abril de 2023 e auditar o RPC e a página pública
antes de declarar o fechamento alternativo disponível.
