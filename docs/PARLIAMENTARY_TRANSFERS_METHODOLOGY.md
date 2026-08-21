# Emendas e recursos destinados a Barreiras

## Pergunta pública

Quem destinou recursos a Barreiras, quanto foi destinado e quanto alcançou um
estágio financeiro confirmado pela fonte oficial?

## Métricas

- **valor destinado**: valor associado à emenda na distribuição de recursos;
- **valor empenhado**: valor dos empenhos ligados à parceria da proposta;
- **valor pago confirmado**: ordens de pagamento com situação `Paga`;
- **quantidade de emendas**: distribuições oficiais distintas após deduplicar
  reexecuções do coletor;
- **emendas integralmente pagas**: quantidade em que o pago confirmado é igual
  ou superior ao valor destinado.

Os cálculos usam `numeric(20,2)` no PostgreSQL. IA não soma valores, não ordena
o ranking e não decide autoria.

## Autoria

O tipo publicado no campo oficial da emenda define a seção:

- `Individual` entra no ranking de pessoas;
- `Comissão`, `Bancada` e autoria coletiva entram em ranking separado;
- autoria ausente ou desconhecida não é transformada em pessoa.

Solicitante, recebedor, beneficiário e autor são papéis diferentes. Uma comissão
não transfere crédito individual aos seus integrantes.

## Ligação com perfis políticos

O nome informado pelo Transferegov não é comparado livremente com nomes de
parlamentares. A ligação pública exige um crosswalk aprovado que registre:

- a grafia oficial observada no Transferegov;
- o identificador do perfil oficial na Câmara ou na ALBA;
- uma candidatura oficial já reconciliada com o TSE;
- URLs e nota de evidência que sustentem a decisão.

Variações de grafia podem apontar para o mesmo perfil, mas cada uma precisa de
evidência própria. Autoria sem crosswalk permanece visível no ranking, sem link
para pessoa. Comissões e bancadas nunca são ligadas a um perfil individual.

Para a LOA estadual, o vínculo inicial usa a autoria nominal preservada no anexo
e o perfil individual oficial preservado da ALBA. Em 13/08/2026, oito dos onze
autores do recorte tinham esse vínculo aprovado. Marcone Amaral, Diego Castro e
Capitão Alden permanecem sem link automático até que uma fonte oficial preserve
um identificador compatível com o período da autoria.

## Reconciliação e ausência

Estágios financeiros só são atribuídos ao autor quando a proposta tem uma única
distribuição. Com múltiplas distribuições, o sistema exibe a ambiguidade e não
divide o pagamento por aproximação. Campo ausente significa “não encontrado nos
endpoints consultados”; não significa zero, cancelamento ou inexistência em
outra base.

## Fonte e cobertura inicial

### Cobertura pública anual das emendas estaduais

A RPC `api.get_public_state_amendment_source_coverage` publica somente agregados
anuais e usa a metodologia `state-amendment-source-coverage/1.0.0`. Ela separa
duas perguntas: se o anexo da LOA foi preservado e se cada autorização pôde ser
ligada à execução financeira estadual por chave oficial única. Checkpoints,
erros internos e identificadores pessoais não são expostos.

Em 2021, o link apresentado pelo catálogo da SEPLAN como Anexo III da LOA 2021
aponta para um PDF cuja capa, cabeçalho e LDO identificam a LOA 2020. O período
permanece `blocked`: nenhum valor de 2020 é atribuído a 2021. De 2022 a 2025,
os anexos territoriais foram preservados, mas o índice estadual integral ainda
não cobre esses exercícios; execução financeira permanece nula, nunca zero.
Em 2026, os totais de empenho, liquidação e pagamento abrangem somente as
ligações bidirecionalmente únicas descritas no gate de unicidade abaixo.

Fonte: API pública Gestão de Parcerias do Transferegov, filtrada pelo código
IBGE `2903201`. A cobertura inicial observada contém três propostas de 2025. O
painel crescerá com a coleta recorrente e com fontes federais e estaduais
complementares, mantendo fonte, data e hash da evidência.

Os anos sem proposta nessa API nova significam somente “nenhuma proposta
devolvida por este endpoint para o filtro e a data consultados”. A cobertura
histórica é reconstruída separadamente pelos arquivos oficiais de dados
abertos do Transferegov. O arquivo de propostas já possui projeção pública
própria, mas não altera ranking, totais de emendas nem estados financeiros.

A matriz pública de cobertura por fonte e exercício usa a RPC
`api.get_public_federal_transfer_source_coverage`. Ela não publica checkpoint,
erro interno ou conteúdo bruto: mostra apenas o estado sanitizado e a quantidade
de linhas municipais já normalizadas. `observed` significa linha oficial
encontrada; `empty` significa fonte integralmente consultada sem linha atribuída
a Barreiras; `partial`, `failed`, `blocked` e `unclassified` impedem qualquer
apresentação de zero. As três séries permanecem separadas e nunca são somadas.

Na auditoria de 20/08/2026, a integridade determinística encontrou zero chaves
duplicadas, zero URL insegura, zero hash inválido e zero divergência na fórmula
de pagamento efetivo. O retrato continha 15 linhas na execução da CGU, três
linhas confirmadas no arquivo histórico do Transferegov e três na API atual.
Outras seis linhas regionais excluídas pertenciam a consórcios cujo objeto não
confirmava Barreiras como destino. A ausência de
correspondência entre séries é registrada como diferença de cobertura, não como
erro nem prova de ausência de recurso.

## Cobertura histórica federal

O arquivo nacional `siconv_proposta.zip` é preservado integralmente em área
privada e validado contra o catálogo oficial por tamanho e ETag. A projeção
normalizada forma o conjunto candidato com propostas cujo `COD_MUNIC_IBGE` seja
exatamente `2903201` e exclui CNPJ, dados bancários, endereço e CEP da API pública. Cada
registro publicado conserva número, ano, situação, objeto, órgão, valores
propostos, URL e hash do ZIP preservado. Proposta não é emenda: esses registros
ampliam a cobertura territorial. O relacionamento com `siconv_emenda.zip` usa
somente `ID_PROPOSTA`, nunca semelhança de nomes ou de objetos. O recorte
inicial encontrou nove linhas candidatas ligadas a oito propostas; os demais
registros continuam sem autoria histórica atribuída por essa fonte.

O município cadastrado para o proponente não basta para atribuir a Barreiras um
projeto de consórcio regional. A publicação considera confirmado quando o objeto
menciona Barreiras ou quando o recebedor local não é uma entidade regional.
Consórcios sem destino municipal expresso permanecem preservados, aparecem no
diagnóstico de exclusão e não entram em totais ou rankings. Na auditoria de
13/08/2026, esse controle manteve 62 de 69 propostas e três de nove linhas de
emenda; seis linhas regionais, inclusive objetos que citam Barra/BA, deixaram
de ser atribuídas a Barreiras.

O arquivo de emendas é preservado integralmente em área privada. A projeção
normalizada separa número da emenda, programa, autor publicado, tipo de autoria,
indicador de impositividade e os dois valores informados pelo arquivo. O
identificador integral do beneficiário não integra o registro normalizado:
CPF é recusado, e CNPJ é minimizado para tipo e quatro últimos dígitos. Essa
camada bruta ainda não altera ranking público até passar pela reconciliação de
identidade e pelos estágios financeiros.

Na interface, `valor global proposto`, `repasse solicitado` e `contrapartida
proposta` são mostrados separadamente. Nenhum deles é rotulado como dinheiro
recebido, empenhado ou pago. Ausência de autoria no arquivo de propostas é
exibida como limite da fonte, não preenchida por IA ou semelhança de nome.

### Série complementar de execução da CGU

O arquivo aberto de emendas do Portal da Transparência é uma série
complementar. Ele é filtrado pelo código IBGE `2903201` e fornece execução
regionalizada mesmo quando a linha não aparece entre as propostas do
Transferegov. A auditoria do retrato publicado em 16/08/2026 encontrou 15
linhas, cinco autorias e exercícios de 2014 a 2023.

Para Carlos Tito, a fonte publicou sete linhas: três em 2020, três em 2022 e
uma em 2023 (`202340720005`). A soma determinística do valor empenhado dessas
sete linhas é R$ 1.956.725,40. O valor pago, calculado exclusivamente como
`pago no exercício + restos a pagar pagos`, é R$ 1.845.798,28. Liquidação,
restos inscritos e cancelamentos não são adicionados a esses totais.

A interface deve chamar essa camada de **execução federal regionalizada para
Barreiras**. Ela não será rotulada como repasse direto à Prefeitura, obra
concluída ou recurso efetivamente usado sem uma fonte posterior que comprove
essas etapas. Pessoas e autorias coletivas terão rankings separados. Cada
linha manterá URL oficial, hash do ZIP, data da coleta e os estágios financeiros
originais.

Na consulta pública, os filtros de parlamentar e ano atuam somente sobre as
linhas oficiais exibidas para conferência. Eles não recalculam nem recortam o
ranking, que permanece produzido deterministicamente sobre todo o acervo
validado. O exercício de 2023 continua pesquisável nessa visão anual, inclusive
com autoria e evidência, mas é identificado como ano de transição e não integra
ranking por legislatura.

A projeção pública dessa série vive em
`territory.cgu_federal_amendment_executions` e é servida pelas RPCs
`api.get_public_cgu_federal_amendment_executions` e
`api.get_public_cgu_federal_amendment_ranking`, exibidas na aba **Execução
federal** de `/recursos`. O ranking ordena pelo valor empenhado
(`ranking_amount_stage = committed`) e mostra o pago efetivo ao lado, sem
misturar estágios. Linhas cujo autor a fonte publica como `Sem informação`
permanecem visíveis na listagem, mas nunca viram posição nominal de ranking.
Cada linha carrega um vínculo por código oficial com a série do Transferegov
(`territory.cgu_transferegov_amendment_links`): o código de 12 dígitos da CGU
equivale ao ano seguido do número de emenda de 8 dígitos do arquivo histórico.
O vínculo apenas rotula sobreposição (`matched_transferegov_unique`,
`not_found_in_transferegov`, `code_unavailable`,
`conflict_non_unique_transferegov`); valores de fontes diferentes nunca são
somados em um mesmo total.

## Emendas estaduais da Bahia — autorização e execução separadas

Emendas estaduais são coletadas e serão publicadas separadamente das federais. A
fonte de execução é o conjunto oficial **Emendas Parlamentares Estaduais** do
Portal de Dados Abertos da Bahia, alimentado pelo FIPLAN e atualizado
diariamente. O Portal Transparência Bahia será usado como fonte complementar de
execução orçamentária e financeira.

O ZIP diário do FIPLAN continua sendo a fonte de execução, mas não contém
município. Seu CSV de despesas agora é normalizado deterministicamente por
exercício, órgão, unidade orçamentária, ação e identificador oficial do autor.
Orçado inicial, orçado atual, empenhado, liquidado e pago permanecem em colunas
separadas e aceitam valores negativos legítimos publicados pela fonte, como
ajustes e estornos. Cada linha conserva o hash do ZIP e o hash da evidência. Um
ZIP sem linhas financeiras, com estrutura alterada ou com bytes divergentes do
hash falha e segue para nova tentativa ou fila de falhas; nunca produz total
zero.

O diagrama de relacionamento publicado no mesmo catálogo é preservado
separadamente do ZIP. O PNG, sua URL oficial, data de modificação, tamanho,
MIME e SHA-256 passam pelo mesmo contrato imutável. Ele comprova quais códigos
internos conectam despesas, liquidações e pagamentos, mas não apresenta campo
de município. Portanto, o diagrama fundamenta a reconciliação financeira e
também documenta por que a territorialização depende dos anexos da LOA.

A normalização registra obrigatoriamente
`territorial_scope=not_available_in_execution_archive`. Portanto, esses valores
descrevem execução agregada estadual e ainda não são “pagos a Barreiras”. A
chave territorial oficial foi localizada nos anexos da LOA da
SEPLAN-BA: entre 2022 e 2025, o Anexo III organiza emendas individuais por
município e autor; em 2026, o Anexo I publica autor, objeto, município e valor.
Cada PDF é preservado integralmente antes de qualquer extração.

O parser determinístico mantém gramáticas independentes para os anexos de
2022-2025 e de 2026. Cada resultado conserva a página e o trecho literal que
sustentam autor, número, objeto e valor. Valores são decimais, nunca `float`.
CPF/CNPJ presente no texto do objeto não é interpretado como valor; o último
campo monetário isolado da linha territorial é o valor autorizado. Um anexo sem
texto integral ou sem linha comprovada de Barreiras falha e não gera total zero.

Validação local e replay de produção dos PDFs oficiais em 13/08/2026:

- 2022: 2 linhas; R$ 379.200 autorizados;
- 2023: 14 linhas; R$ 1.090.200 autorizados;
- 2024: 13 linhas; R$ 2.245.028 autorizados;
- 2025: 7 linhas; R$ 997.600 autorizados;
- 2026: 34 linhas; R$ 11.198.888 autorizados.

O replay persistiu 70 resultados válidos, com 70 chaves de evidência distintas,
cinco jobs concluídos e nenhuma falha. A projeção pública aceita somente jobs
concluídos, parser e validador fixados, URL HTTPS, hash do PDF, hash do trecho e
estágio `authorized`. Esses números ainda não provam empenho, liquidação,
pagamento ou recebimento pelo Município.

Valor publicado nesses anexos é **autorizado na LOA**. Não significa pagamento,
transferência ou dinheiro recebido por Barreiras. A próxima reconciliação entre
as autorizações territoriais e os agregados normalizados do FIPLAN exibirá, em
colunas independentes:

- deputado estadual autor e identificador oficial;
- exercício, número da emenda e objeto;
- órgão executor, beneficiário e município;
- valor indicado, empenhado, liquidado e pago como estágios separados;
- restos a pagar, cancelamentos e impedimentos, sem convertê-los em zero;
- URL, data da coleta, hash e versão exata do arquivo de origem.

O primeiro ranking estadual mostra apenas o valor autorizado, separado do
ranking federal e acompanhado do objeto, página, trecho literal, URL e hashes.
Grafias equivalentes de autor são agrupadas por normalização determinística de
acentos, pontuação e abreviação `Jr.`. O link para um perfil político aparece
somente quando existe crosswalk privado e aprovado com a ALBA; a normalização,
isoladamente, não cria esse vínculo. Valor efetivamente pago a Barreiras só
entrará em coluna própria após reconciliação com a execução. Uma emenda
anunciada ou indicada não será descrita como dinheiro recebido. Ausência na
base estadual será exibida como “não encontrada na fonte consultada”, nunca
como ausência definitiva ou falta de trabalho parlamentar.

O link oficial rotulado como Anexo III de 2021 aponta para um PDF da LOA 2020.
Por isso, 2021 é registrado como `blocked`: o Barreiras 360 não baixa nem
reclassifica o documento de outro exercício para preencher artificialmente a
cobertura.

### Limite territorial observado em 13/08/2026

O ZIP oficial atualmente contém cinco CSVs, porém não publica coluna municipal
explícita nem código IBGE nos cabeçalhos. A preservação desse retrato da fonte
não autoriza atribuição a Barreiras, cálculo de total municipal ou inclusão em
ranking. Termos como “Barreiras” no objeto ou no nome de uma unidade são apenas
texto e não constituem chave territorial determinística. A cobertura será
registrada como retrato estadual preservado e o recorte municipal permanecerá
bloqueado para o ZIP isolado. Os anexos anuais da LOA agora fornecem a chave
territorial oficial para valores autorizados; a ligação com empenho, liquidação
e pagamento ainda depende de reconciliação verificável com a execução.

A view estadual de pagamentos observada em 13/08/2026 não segue integralmente
as regras de escape de CSV. Ela é preservada por hash e processada por uma
gramática exclusiva que usa os identificadores estruturados de pagamento,
empenho e execução para separar os registros, sem alterar o campo `Objeto`.
Esse contrato validou 20.687 pagamentos; 32 deles conservam a ausência de
dígito verificador publicada pela própria fonte e geram aviso auditável. O ZIP
passa a ter 68.990 linhas estruturalmente validadas e cobertura técnica
`complete`. Isso não torna os valores elegíveis à publicação: nenhuma das
cinco views contribui isoladamente para totais financeiros ou rankings. A
atribuição municipal exige reconciliação determinística com a chave territorial
dos anexos da LOA e preservação da evidência de cada ligação.

A fonte oficial também apresentou a cadeia TLS incompleta em 13/08/2026. O
coletor não desativa a validação: usa exclusivamente o intermediário OV R36 e o
cross-sign R46/USERTrust publicados pela Sectigo, preservados no repositório e
verificados por hash antes da execução.

### Gate de unicidade estadual da LOA 2026

Para 2026, a reconciliação exige unicidade no **anexo estadual inteiro**. O
worker indexa privadamente cada linha estruturada do Anexo I, inclusive as que
não pertencem a Barreiras, mas conserva nesse índice somente autor, número da
emenda, órgão, unidade, ação, páginas e hashes de evidência. Município e valor
de outros territórios não são normalizados nem publicados.

Uma chave só poderá ligar a autorização de Barreiras à execução estadual
quando ocorrer uma única vez em todo o anexo e uma única vez no retrato
correspondente da execução. Colisão em qualquer lado mantém empenho,
liquidação e pagamento bloqueados para publicação territorial.

### Resultado do primeiro replay de reconciliação

Em 14/08/2026, o workflow oficial reprocessou o Anexo I de 2026 e persistiu
3.182 linhas de escopo privado. O diagnóstico das 34 autorizações destinadas a
Barreiras encontrou:

- 10 pares `matched_bidirectional_unique`, com uma ocorrência na LOA e uma na
  execução;
- 21 casos `blocked_non_unique_loa_key`, nos quais a combinação publicada se
  repete de 2 a 76 vezes no anexo estadual;
- 3 casos `not_found_in_execution_source`, com uma ocorrência na LOA e nenhuma
  no retrato de execução;
- nenhum caso de duplicidade no lado da execução entre as 34 autorizações.

A view `territory.bahia_state_loa_execution_reconciliation` é privada e não é
exposta pelo PostgREST. Mesmo internamente, empenhado, liquidado, pago e a
evidência da execução são retornados somente nos dez pares únicos. Nos outros
24 registros, esses campos permanecem nulos e o status explica o bloqueio. A
projeção pública `api.get_public_bahia_state_loa_execution` conserva essa mesma
regra: publica os estágios apenas nos dez pares e retorna valores nulos, nunca
zero fabricado, nos demais. A função de resumo calcula os totais em SQL e
separa explicitamente o total autorizado nas 34 emendas do universo comparável
das dez ligações confirmadas. A interface não produz ranking de execução com
essa cobertura parcial.

Para manter a consulta pública previsível, o resultado dessa view é copiado
atomicamente para o snapshot privado
`territory.bahia_state_loa_execution_reconciliation_snapshot` ao fim de cada
processamento. Os endpoints públicos leem o snapshot indexado e nunca refazem
o cruzamento de JSON bruto durante a requisição. O snapshot não altera regras,
valores ou evidências: é somente uma projeção operacional versionada e
auditável da mesma reconciliação determinística.

Um `R$ 0,00` dentro de um par confirmado é um valor publicado pela fonte no
retrato coletado. Fora de um par confirmado, ausência de valor significa
“não atribuído com segurança”, e não pagamento zero.

### Limite histórico de 2022 a 2025

Os anexos territoriais encontrados para 2022 a 2025 identificam a autorização,
o autor, o órgão, a unidade e o valor destinado a Barreiras, mas não publicam o
mesmo conjunto de identificadores usado pelo arquivo estadual de execução. Em
14/08/2026, a auditoria determinística tentou as combinações disponíveis —
inclusive autor, órgão, unidade e valor — nas 34 autorizações normalizadas desses
anos. Nenhuma combinação resultou em correspondência única.

Por esse motivo, o sistema não usa semelhança nominal para atribuir execução.
Essas emendas recebem publicamente o status
`official_link_key_unavailable`: a autorização e sua evidência permanecem
visíveis, enquanto empenho, liquidação, pagamento e evidência de execução ficam
nulos. Isso representa uma limitação documental da ligação entre as fontes, não
valor zero e nem prova de que o recurso não foi executado.

### Linha do tempo nos perfis dos representantes

Os perfis oficiais ligados por crosswalk aprovado recebem uma linha do tempo
anual das emendas estaduais destinadas a Barreiras. A autoria acompanha o ano
da LOA, mesmo quando o parlamentar hoje exerce mandato em outra Casa. A página
não transforma o cargo atual em cargo retroativo.

Cada exercício apresenta dois universos distintos:

- **todas as emendas territoriais do autor**: quantidade e valor autorizado na
  LOA para Barreiras;
- **subconjunto conciliado**: quantidade, valor autorizado comparável,
  empenhado, liquidado e pago somente das emendas com ligação bidirecional
  única ao retrato financeiro estadual.

Quando nenhuma emenda possui ligação única, os estágios de execução ficam
nulos e a interface informa que não foi possível atribuí-los com segurança.
Quando a conciliação é parcial, a quantidade bloqueada é exibida e não entra
nos valores de execução. Cada ano liga ao catálogo de emendas, objetos,
páginas, documentos e hashes correspondentes. Essa linha do tempo não é um
ranking de desempenho e não mede, isoladamente, o trabalho parlamentar.

### Correção de layout do Anexo I de 2026

O PDF oficial de 2026 organiza a tabela por autor. Em sete linhas, a extração
de texto embutido anexou a coluna `Município` ao final do objeto ou separou
letras de `Barreiras`. Uma leitura independente pelas coordenadas das colunas
confirmou 34 linhas destinadas ao município, no total autorizado de
R$ 11.198.888. O parser 1.2.0 reconhece somente a ocorrência territorial no fim
da linha, imediatamente antes do valor. Uma menção a Barreiras dentro do objeto
seguida de outro município continua excluída. A versão 1.1.0 permanece no
histórico bruto; o novo job cria resultados versionados, sem sobrescrita.

| Emenda | Autor publicado | Página | Valor autorizado recuperado |
|---:|---|---:|---:|
| 2583 | Hassan | 94 | R$ 200.000 |
| 1276 | Luciano Simões Filho | 172 | R$ 100.000 |
| 5724 | Marcone Amaral | 203 | R$ 1.548.747 |
| 2006 | Robinson Almeida | 301 | R$ 20.000 |
| 5794 | Robinson Almeida | 314 | R$ 7.800 |
| 5795 | Robinson Almeida | 314 | R$ 4.800 |
| 142 | Samuel Júnior | 328 | R$ 300.000 |

As sete linhas somam R$ 2.181.347. O valor autorizado de Marcone Amaral para
Barreiras em 2026 passa a quatro emendas e R$ 7.449.799. O total de
R$ 10.324.979 exibido no cabeçalho do parlamentar inclui outros municípios e,
por isso, não entra integralmente no recorte territorial de Barreiras.

## Ranking por legislatura e esfera

A página de Recursos publica até dez autorias individuais encontradas por
legislatura, sempre em painéis separados para a Câmara dos Deputados e para a
Assembleia Legislativa da Bahia. O agrupamento usa períodos oficiais registrados
em `political.legislative_terms`; a projeção pública é a RPC
`api.get_public_parliamentary_legislature_rankings`.

A página Quem decide conserva somente o resumo individual da legislatura atual
nos perfis vinculados por identificador oficial e conduz a comparação completa
para Recursos. Assim, identidade e mandato não se confundem com a análise do
dinheiro destinado ao município.

As métricas não são intercambiáveis:

- no recorte federal, a posição é determinada pelo valor **destinado** a
  Barreiras na série reconciliada do Transferegov;
- no recorte estadual, a posição é determinada pelo valor **autorizado** nos
  anexos da LOA da Bahia para Barreiras;
- empenho, liquidação e pagamento são exibidos separadamente e nunca alteram a
  posição desse ranking;
- somente autoria individual participa. Comissões, bancadas e outras autorias
  coletivas permanecem nos recortes próprios.

As fontes atualmente preservadas informam o exercício financeiro, mas não uma
data individual confiável para toda emenda. Como as legislaturas mudaram em
fevereiro de 2023, o exercício de 2023 é classificado como transição e fica fora
dos rankings por legislatura. A plataforma usa apenas anos civis completos: 2020
a 2022 para a 56ª Legislatura federal e a 19ª estadual; 2024 a 2026 para a 57ª
federal e a 20ª estadual. Isso evita atribuir retroativamente uma emenda ao
mandato errado.

O perfil oficial relacionado é apenas um vínculo de identidade e navegação. Se
uma pessoa passou da ALBA para a Câmara dos Deputados, a emenda continua
classificada pela esfera da fonte e pelo exercício em que foi publicada.
Ausência de perfil associado não remove a autoria do ranking. Ausência de
pagamento localizado é mostrada como limitação da fonte, nunca como valor zero.

Na verificação de produção de 14/08/2026, as 56ª e 57ª legislaturas federais
reuniram três autores individuais no recorte coberto: Cláudio Cajado, Rogéria
Santos e Ricardo Maia. Os três possuem ligação explícita entre a grafia do
Transferegov, o perfil oficial da Câmara e um crosswalk TSE aprovado. A ligação
serve para identidade e navegação; a posição continua sendo calculada somente
pelos valores oficiais do recorte da legislatura.

Este indicador mede somente recursos destinados ou autorizados para Barreiras
encontrados nas fontes cobertas. Ele não mede sozinho todo o trabalho do
parlamentar, não avalia mérito, não é uma nota de desempenho e não prova
execução do recurso. Quando a cobertura oficial tiver menos de dez autores, a
interface exibirá somente os nomes efetivamente encontrados.

Fontes oficiais iniciais:

- https://dados.ba.gov.br/pt_BR/dataset/emendas-parlamentares
- https://www.ba.gov.br/seplan/orcamento/historico-de-loa
- https://www.transparencia.ba.gov.br/
- https://www.transparencia.ba.gov.br/MapaSite/
- https://www2.camara.leg.br/transparencia/prestacao-de-contas/contas-da-camara/ano-de-2019/informativo-para-a-sociedade-2019
- https://www2.camara.leg.br/atividade-legislativa/comissoes/grupos-de-trabalho/57a-legislatura/
- https://www.al.ba.gov.br/midia-center/noticias/32631
- https://www.al.ba.gov.br/midia-center/noticias/55953

## Perfil individual de contribuições por legislatura

Cada autoria presente no ranking por legislatura possui uma página pública
própria. A projeção
`api.get_public_parliamentary_legislature_contributions` recebe esfera, número
da legislatura e a chave normalizada exata do autor. Ela não pesquisa por
semelhança nominal e não mistura legislaturas, esferas ou anos de transição.

A página apresenta até 25 registros por vez e conserva:

- número e exercício da emenda;
- objeto e beneficiário quando publicados pela fonte;
- valor destinado no recorte federal ou autorizado no recorte estadual;
- empenho, liquidação e pagamento em campos independentes;
- situação da reconciliação entre as fontes;
- URL oficial, hash SHA-256, página e trecho literal quando disponíveis;
- chave auditável e versão da metodologia.

No recorte federal, a fonte atualmente usada pela projeção não publica
liquidação individual nesse contrato; a interface diz isso expressamente em
vez de inferir o estágio. No recorte estadual, valores de execução aparecem
somente quando a chave oficial é única nos dois lados. Uma chave ambígua, não
localizada ou inexistente permanece nula e recebe uma explicação documental.

Os totais do perfil são calculados no PostgreSQL sobre todo o recorte antes da
paginação. A aplicação apenas formata os decimais publicados pela RPC; não
recalcula o ranking e não usa IA para somar valores. O perfil mede somente as
emendas para Barreiras encontradas nas fontes cobertas. Não é nota geral de
desempenho parlamentar, não comprova pagamento e não comprova execução de obra
ou serviço.

## Diagnóstico de cobertura e cards da legislatura atual

A RPC `api.get_public_parliamentary_legislature_coverage` publica, por esfera e
legislatura, contagens agregadas de emendas, autores, objetos, beneficiários,
estágios financeiros, conciliações e evidências oficiais. Ela não declara que o
acervo está completo: descreve apenas o que foi observado nas fontes já
preservadas. A interface informa essa ressalva junto ao ranking.

A RPC anual `api.get_public_parliamentary_legislature_year_coverage` cruza os
registros do ranking com o controle de coleta da fonte correspondente. A versão
`parliamentary-legislature-year-coverage/1.1.0` distingue:

- `observed`: há ao menos um registro individual com valor e evidência;
- `source_empty`: a partição oficial foi consultada e não publicou registro no
  recorte contratado;
- `collection_incomplete`: a última coleta ficou parcial ou falhou;
- `source_blocked`: a própria fonte apresenta impedimento documentado, como o
  link da LOA 2021 que aponta para o arquivo de 2020;
- `collected_no_record`: o documento foi preservado, mas nenhum registro
  individual chegou ao ranking validado;
- `not_collected`: não existe partição classificada para aquele ano.

Somente `observed` possui contagem positiva. Todos os demais estados preservam
contagem zero apenas como cardinalidade do ranking atual, nunca como afirmação
de que o parlamentar destinou zero reais ou de que a fonte oficial não possui
outros documentos.

Campo não oferecido pela fonte permanece `null` e recebe o estado
`not_published_in_source`. Em particular, o recorte federal atual não oferece
liquidação individual nesse contrato, enquanto o anexo estadual não oferece um
beneficiário estruturado. Esses casos não podem ser convertidos em zero.

Nos cards dos deputados atuais, o resumo da legislatura aparece somente quando
o ranking possui crosswalk aprovado e coincidem exatamente esfera, ID externo
do perfil oficial e período da legislatura. Semelhança de nome nunca basta. O
card apresenta posição, quantidade, valor destinado federal ou autorizado
estadual e pagamento localizado, além do link para todas as evidências daquela
autoria. Como o ranking público possui até dez posições por legislatura, a
ausência do resumo no card significa apenas que o perfil não está nesse top 10
com ligação oficial aprovada; não significa ausência de emendas ou de trabalho.
