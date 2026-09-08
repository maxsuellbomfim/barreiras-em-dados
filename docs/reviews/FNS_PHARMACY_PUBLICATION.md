# Farmácia Popular: leitura privada e caminho de publicação

## Publicação operacional verificada — 08/09/2026

O usuário autorizou explicitamente importar os três arquivos no bucket privado
`raw-artifacts` e publicar os 25 pagamentos após validação. A importação e a
publicação foram realizadas; as seções seguintes conservam o histórico dos
contratos e das etapas preparatórias, não um bloqueio operacional vigente.

- Plano: `3b89ed8ebb30358d5f9f8e8a5a8748b2311c1af553f8fb67056b14457fb6aad0`.
- Três objetos relidos byte a byte e conferidos por SHA-256. O primeiro envio
  parou no XLSX recusado pelo bucket; a migration `20260908200000` adicionou
  apenas o MIME específico, com auditoria idempotente, sem tornar o bucket público
  ou ampliar permissões. A retomada reutilizou um objeto e criou os dois restantes.
- Simulação com rollback, importação e replay: três artefatos, dois snapshots,
  25 registros brutos e 25 documentos distintos; zero divergências de linhagem.
- Comparação integral dos payloads e hashes com o plano: 25 correspondências,
  zero divergências. Duas decisões de aprovação após a conferência.
- RPC pública: 25 registros na primeira página, zero na seguinte; nomes,
  datas, valores e hashes conferidos contra o lote. Sem credenciamento histórico.
- Produção `/recursos/saude?ano=2025`: HTTP 200, 25 cartões. HTML sem os marcadores
  de identificadores da requisição, notas de revisão ou campos internos testados.
  Filtro de 2024 exibiu pendência, não zero. Celular a 390 px sem overflow
  horizontal; Tab do seletor alcançou o botão Consultar com foco visível.

Este recorte não representa todos os pagamentos anuais. Os valores pertencem
a estabelecimentos privados, separados das receitas municipais e dos rankings.
Não houve inferência de execução do serviço nem reconciliação com a CGU.
Próximo passo: ampliar o inventário oficial de períodos/estabelecimentos, com
paginação completa e as mesmas validações, antes de afirmar cobertura maior.

## Contrato implementado

`inspect_pharmacy_capture` aceita uma página completa, até 25 registros,
de Outros Pagamentos (tipo 3), no recorte Barreiras/BA. Confere URL solicitada
e final, ano, beneficiário consultado, SHA-256, tamanho, HTTP e paginação.
Parâmetros duplicados, páginas parciais e mistura de modalidades são recusados.
Metadados devem vir do transporte confiável: hash não autentica o emissor.

Somente FARMACIA POPULAR na esfera PRIVADA é interpretada. Outros programas,
inclusive demandas judiciais, não produzem registros nem valores na saída.
Os campos permitidos incluem chave documental privada, data, posição/hash
da evidência e valores documentais. Nomes, identificadores do beneficiário,
contas, agência, processos e texto de rejeição não são devolvidos.

Valores são conferidos com Decimal contra os totais declarados. Repetição
documental, anulação, rejeição ou divergência requerem revisão. Nenhuma linha
repetida é apagada. Competência não é convertida em data de pagamento.
O leitor não cobre múltiplas páginas: precisa de adaptador específico antes
de ampliar esse limite; falha nunca equivale a zero financeiro.

## Bloqueios de publicação

1. O identificador enviado ao FNS é opaco. Quantidade de dígitos ou nome com
   aparência empresarial não comprovam identidade institucional. Conferir
   cadastro oficial do estabelecimento e evidência antes da publicação.
2. O reconciliador atual `fns_cgu_reconciliation` compara emendas do Fundo
   Municipal de Saúde. Seu CNPJ fixo e arquivo anual de emendas não podem ser
   reutilizados para estabelecimentos privados. Ausência naquele arquivo não
   significa ausência do pagamento nem prova que um registro é novo.
3. Verificar a ordem e a identidade documental da fonte antes de deduplicar
   entre bases. Não deduplicar apenas por valor, competência ou nome.

`publication_allowed=false`, `identity_verification=pending` e
`reconciliation=pending` são fixos. Este leitor não escreve no banco nem cria
lançamento financeiro, autorização editorial ou cobertura anual.

## Entrega pública posterior

Seção Saúde dentro de Recursos, separando administração municipal de pagamentos
a estabelecimentos locais. Programa, período, beneficiário institucional,
valor, estágio informado e evidência devem estar explícitos. Não somar esses
pagamentos às receitas municipais ou ao ranking de emendas. Listas paginadas
no servidor; evidências completas somente no detalhe, sem conteúdo bancário.

O adaptador privado `fns_pharmacy_identity` agora cruza o identificador da
requisição de pagamentos validada com o CNPJ do XLSX oficial preservado do
Infoms. Confere dígitos verificadores, hash/tamanho dos bytes, origem registrada,
estrutura limitada da planilha e correspondência única. Nome semelhante não
substitui CNPJ; repetição, mesmo idêntica, exige revisão. Fórmulas, entidades XML,
entradas ZIP repetidas e planilhas adicionais são recusadas. Nenhuma dependência
nova foi adicionada. A origem registrada deve vir da aquisição confiável: não
aceitar esses metadados de um cliente público.

O resultado permitido contém nome institucional, hashes das duas evidências e
linha do cadastro, sem CNPJ, endereço, conta ou valor. O nome é o do cadastro,
não uma inferência de pessoa pelo texto. O cadastro atual não comprova
credenciamento no ano do pagamento; `historical_registration_verified=false`,
`reconciliation=pending` e `publication_allowed=false` permanecem explícitos.

Verificação local em 08/09/2026: os dois beneficiários de Farmácia Popular
obtiveram correspondência institucional única usando o XLSX preservado de SHA-256
`8d55072edb40db4d38eb9bd583a62880699928587a83e81c3818625b97efa3b2`
e suas capturas de pagamentos. Não houve upload, escrita no banco ou publicação.
Os 110 testes FNS passaram, incluindo os seis testes novos de identidade.

## Reconciliação privada por beneficiário

`reconcile_pharmacy_captures` recebe até 20 capturas completas e o cadastro
preservado; executa os dois leitores existentes antes de reconciliar. A chave
documental inclui beneficiário, ano, número, data e ação. Uma nova observação
dos mesmos bytes não cria outro documento; bytes diferentes preservam referências
separadas de evidência. Mudança de valores, competência/consulta de ordem ou
conjunto documental entre retratos do mesmo beneficiário/ano exige revisão e
retira todos os candidatos da saída. Não há substituição automática pelo último.

O fingerprint da consulta de ordem usa seus parâmetros oficiais sem paginação.
Compartilhar essa consulta não prova titularidade da ordem nem permite atribuir
seu total a cada estabelecimento. As referências e valores documentais permanecem
por beneficiário. Não há soma financeira no reconciliador nem comparação com CGU:
`cross_source_reconciliation=not_performed` e `publication_allowed=false`.

Conferência local em 08/09/2026 sobre os dois arquivos reais: **25 documentos,
11 consultas de ordens compartilhadas e nenhum conflito**. O replay dos mesmos
arquivos manteve 25 documentos e identificou 25 observações repetidas. Isso não
prova cobertura anual, execução de serviços ou credenciamento histórico. Não
houve novas requisições, upload, escrita no banco ou valores novos no site.

## Registro auditável e limite público

A migration `20260908173000_fns_pharmacy_registry.sql` cria três tabelas privadas:
`source.fns_pharmacy_snapshots`, `source.fns_pharmacy_documents` e
`source.fns_pharmacy_decisions`. Nenhuma recebe acesso de leitura/escrita do
frontend ou da role `service_role`. Inserção exige operador privilegiado;
alteração/exclusão de evidências e decisões são recusadas. Após uma decisão,
o conjunto documental fica fechado; correções exigem um novo snapshot.

O importador ainda necessário deve reler e conferir hashes dos bytes privados,
executar identidade e reconciliação, derivar `scope_key` estável por beneficiário
e ano e registrar `raw.raw_records.record_type=fns_pharmacy_payment`. O payload
normalizado contém `document_key`, `document_date`, `net` (string com duas casas),
`source_row`, `establishment`, `register_row` e `register_sha256`. É ligado ao
artefato do pagamento. Os testes SQL conferem esse vínculo, mas não substituem
a validação do arquivo original nem demonstram execução de serviço.

`api.get_public_pharmacy_payments(ano,offset)` retorna até 25 documentos por
página, com nome institucional, data, valor documental, hashes e data da revisão.
Não retorna IDs privados, CNPJ, URLs com identificadores, notas, contas ou totais.
Sempre informa `historical_registration_verified=false`. O consumidor deve
oferecer a fonte oficial e explicar o significado dos valores, sem somar à
receita municipal ou ao ranking de emendas. Página vazia não comprova zero.

Só o snapshot mais recente de cada escopo pode aparecer: novo retrato pendente
bloqueia fallback. Aprovação exige quantidade completa e linhagem válida;
revogação, mudança da evidência registrada ou chave documental duplicada entre
escopos retiram a projeção. Inserções de documentos e decisões bloqueiam a mesma
linha-pai para serializar a aprovação. A consulta revalida todo o conjunto.

Esta entrega contém schema/RPC e testes com dados sintéticos, não uma carga real
nem aprovação dos pagamentos. Próximo passo: importador idempotente com simulação,
hashes e relatório de conferência, seguido de revisão e conexão da rota ao RPC.
Não usar os totais de uma ordem coletiva como valor de cada farmácia.

## Apresentação preparada

A rota `/recursos/saude`, acessível de Recursos, possui um estado explícito de
publicação em preparação e links oficiais. Não exibe amostras nem converte
pendência em zero. `readPharmacyPublication` faz validações defensivas de uma
futura projeção revisada, com lista de campos permitidos e limite de 25 linhas.
Não é mecanismo de autorização: a aprovação e atualidade precisam ser
estabelecidas pelo servidor/banco, nunca por parâmetros enviados pelo usuário.

A rota agora consulta `get_public_pharmacy_payments` no servidor, sem cache de
aprovações, com ano e página na URL. O piloto inicial abre em 2025; outros anos
podem ser consultados desde 2021. Uma página cheia exige verificar a página
seguinte antes de oferecer navegação. Falhas não são convertidas em lista vazia.
Não há acesso a Storage, dados bancários ou identificadores internos pela rota.

`prepare_pharmacy_import` reexecuta a reconciliação e gera plano privado estável
com hashes, metadados de aquisição e documentos. Recusa mais de um retrato do
mesmo beneficiário/ano no lote. `scripts/sql/import-pharmacy-plan.sql` é template
exclusivo do operador: substituir o marcador por JSON corretamente escapado,
somente após preservar e reler todos os objetos. SQL executa atomicamente, impede
conflitos e reutiliza snapshots já importados, inclusive aprovados. Não contém
decisões de aprovação. Datas de download do cadastro são evidência de aquisição,
não datas de credenciamento. A fonte possui endpoints próprios, sem reutilizar
o endpoint do Fundo Municipal de Saúde.
