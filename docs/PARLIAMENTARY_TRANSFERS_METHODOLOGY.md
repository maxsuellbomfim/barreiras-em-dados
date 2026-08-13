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

## Reconciliação e ausência

Estágios financeiros só são atribuídos ao autor quando a proposta tem uma única
distribuição. Com múltiplas distribuições, o sistema exibe a ambiguidade e não
divide o pagamento por aproximação. Campo ausente significa “não encontrado nos
endpoints consultados”; não significa zero, cancelamento ou inexistência em
outra base.

## Fonte e cobertura inicial

Fonte: API pública Gestão de Parcerias do Transferegov, filtrada pelo código
IBGE `2903201`. A cobertura inicial observada contém três propostas de 2025. O
painel crescerá com a coleta recorrente e com fontes federais e estaduais
complementares, mantendo fonte, data e hash da evidência.

Os anos sem proposta nessa API nova significam somente “nenhuma proposta
devolvida por este endpoint para o filtro e a data consultados”. A cobertura
histórica é reconstruída separadamente pelos arquivos oficiais de dados
abertos do Transferegov. O arquivo de propostas já possui projeção pública
própria, mas não altera ranking, totais de emendas nem estados financeiros.

## Cobertura histórica federal

O arquivo nacional `siconv_proposta.zip` é preservado integralmente em área
privada e validado contra o catálogo oficial por tamanho e ETag. A projeção
normalizada mantém apenas propostas cujo `COD_MUNIC_IBGE` seja exatamente
`2903201` e exclui CNPJ, dados bancários, endereço e CEP da API pública. Cada
registro publicado conserva número, ano, situação, objeto, órgão, valores
propostos, URL e hash do ZIP preservado. Proposta não é emenda: esses registros
ampliam a cobertura territorial, mas não entram no ranking de autoria até o
relacionamento com `siconv_emenda.zip` ser comprovado.

Na interface, `valor global proposto`, `repasse solicitado` e `contrapartida
proposta` são mostrados separadamente. Nenhum deles é rotulado como dinheiro
recebido, empenhado ou pago. Ausência de autoria no arquivo de propostas é
exibida como limite da fonte, não preenchida por IA ou semelhança de nome.

## Emendas estaduais da Bahia — próxima trilha

Emendas estaduais serão coletadas e publicadas separadamente das federais. A
fonte inicial será o conjunto oficial **Emendas Parlamentares Estaduais** do
Portal de Dados Abertos da Bahia, alimentado pelo FIPLAN e atualizado
diariamente. O Portal Transparência Bahia será usado como fonte complementar de
execução orçamentária e financeira.

O recorte territorial buscará Barreiras pelo identificador municipal e pelos
campos estruturados de localidade/beneficiário da própria fonte. Cada registro
deverá preservar, quando publicados:

- deputado estadual autor e identificador oficial;
- exercício, número da emenda e objeto;
- órgão executor, beneficiário e município;
- valor indicado, empenhado, liquidado e pago como estágios separados;
- restos a pagar, cancelamentos e impedimentos, sem convertê-los em zero;
- URL, data da coleta, hash e versão exata do arquivo de origem.

O ranking mostrará primeiro fatos comparáveis: valor indicado e valor
efetivamente pago a Barreiras em colunas distintas. Uma emenda anunciada ou
indicada não será descrita como dinheiro recebido. Ausência na base estadual
será exibida como “não encontrada na fonte consultada”, nunca como ausência
definitiva ou falta de trabalho parlamentar.

Fontes oficiais iniciais:

- https://dados.ba.gov.br/pt_BR/dataset/emendas-parlamentares
- https://www.transparencia.ba.gov.br/
- https://www.transparencia.ba.gov.br/MapaSite/
