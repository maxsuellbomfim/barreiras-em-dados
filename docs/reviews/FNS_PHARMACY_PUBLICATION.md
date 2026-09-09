# Farmácia Popular: leitura privada e caminho de publicação

## Automação em implementação

`assess_refresh` compara duas capturas do mesmo estabelecimento/ano usando os
leitores documentais existentes. A aprovação anterior deve vir do registro
autoritativo, nunca de entrada pública. A regra distingue repetição sem novidade
de acréscimo de documentos; valor, competência, consulta de ordem, remoção,
cadastro diferente ou aprovação ausente impedem o caminho automático. Alterar
apenas serialização ou ordem de linhas não cria documentos. Não calcula totais
nem publica: `publication_allowed=false` permanece obrigatório nesta camada.

Próximas integrações da mesma meta: carregar a aprovação e os originais privados
no worker, registrar execução pelo `CollectionControl` existente, preservar e
reler novas capturas, importar/aprovar atomicamente com conferência da versão
anterior, programar a coleta e exibir atualização/cobertura/pendências públicas.
Novos escopos, inclusive virada de ano, precisam de caminho explícito de identidade;
não podem ser tratados como repetição de outro exercício. Esta regra isolada
**não significa que a atualização automática esteja ativa**.

A migration `20260909040000` acrescenta `source.approve_pharmacy_refresh` para
o próximo passo de persistência. É `security invoker`, sem acesso de frontend
ou novos grants ao coletor. Serializa inserções de snapshots e decisões, exige
baseline imediatamente anterior ainda aprovado, mesma identidade/ano/cadastro,
linhagem completa e conservação dos documentos anteriores. Acréscimos são
permitidos; remoção, alteração ou duplicação entre escopos são recusadas.
Replay devolve a mesma decisão, não cria outra aprovação. A validação SQL não
substitui a releitura dos bytes nem a comparação documental completa no worker.
Essa migration ainda não foi aplicada em produção; falta conectar o worker e
o controle de execução antes de ativar a coleta/publicação programada.

## Cadastro oficial de renovação 2025 — lote publicado

O PDF nacional do Ministério da Saúde foi preservado e lido integralmente:
425 páginas, 33.049 linhas cadastrais, 4.745.940 bytes, SHA-256
`66509552e1bf89ac6ced0ce5dd9d2ac6bce018ad6b8e1cf80a31846e8088ef57`.
Fonte: [renovação cadastral 2025](https://www.gov.br/saude/pt-br/composicao/sectics/farmacia-popular/renovacao-de-estabelecimentos-participantes/empresas-credenciadas-para-realizar-a-renovacao-2025/view).
Dois leitores independentes e inspeção visual dos nomes confirmaram quatro
instituições por identificador exato de estabelecimento, igual ao da matriz.
A coluna de razão social é da matriz: filiais diferentes não são resolvidas
automaticamente. Nomes quebrados em mais de uma linha são conservados completos.

| Página / linha de dados | Instituição | Documentos por ano |
| --- | --- | --- |
| 44 / 56 | COMERCIAL FARMACEUTICA V.L.A LTDA | 2021: 2 |
| 385 / 25 | REDE DROGARIAS ULTRA POPULAR LTDA | 2021: 10 |
| 56 / 9 | D DOS SANTOS DE JESUS COMERCIO DE MEDICAMENTOS LTDA | 2021: 24; 2022: 23; 2023: 24 |
| 366 / 50 | PRODUTOS FARMACEUTICOS MASCARENHAS LTDA | 2021: 24; 2022: 12 |

Plano privado validado: sete snapshots, 119 documentos, oito arquivos (sete
JSON e um PDF), hash `1c5ffeafd65545ea62dacf9f77ad0a2022f7d3e97b1bdff1f63d5a6d159a8745`.
O cadastro de 2025 resolve identidade institucional, **não credenciamento
histórico em 2021–2023**. Não há inferência de execução nem soma com emendas.
O leitor restringe origem, MIME de persistência, SHA-256, tamanho, página e linha;
o importador e o gate SQL preservam o caminho XLSX anterior e a aprovação separada.

Após bloqueio inicial, o usuário autorizou explicitamente os sete JSON e o PDF,
bem como a publicação após validação. Oito objetos criados e relidos byte a byte
e por SHA-256. As duas migrations foram aplicadas, seguidas de simulação com
rollback, importação e replay. A auditoria encontrou 119 esperados, 119 presentes,
119 com payload/hash/linhagem correspondentes e 119 chaves distintas.
Sete decisões de aprovação foram registradas. Novo replay manteve 19 snapshots,
19 decisões e 335 documentos distintos. A comparação da projeção pública
integral, incluindo os 216 anteriores, encontrou 335 correspondências de nome,
data, valor e ambos os hashes; todos conservam credenciamento histórico falso.
Não resta bloqueio de identidade neste lote de 119. A cobertura continua parcial:
2021: 108; 2022: 78; 2023: 66; 2024: 41; 2025: 25; 2026: 17.
A página pública de 2021 confirmou 108 pagamentos de seis estabelecimentos,
paginação de 25 e aviso de cobertura parcial. Originais e identificadores
permanecem privados; os pagamentos não entram nas receitas nem nas emendas.

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

### Inventário histórico conferido em 08/09/2026

As seis primeiras páginas anuais do catálogo oficial de Outros Pagamentos
foram preservadas localmente com criptografia do Windows, hash e metadados.
Todas declararam uma única página. O leitor `inspect_entity_catalog` confirmou
escopo territorial, integridade, paginação, totais e ausência de identificadores
repetidos. Seu resultado é privado e não classifica entidades como farmácias.
O leitor aceita múltiplas páginas completas e exige contagem estável; páginas
ausentes são `partial`, nenhuma captura é `not_collected`, e vazio declarado
é `empty`. Não há publicação ou inferência de identidade nesse leitor.

Os detalhes das 22 entidades-ano fora de 2025 foram consultados uma vez, com
intervalo de dez segundos, HTTP 200 e preservação criptografada local. O recorte
2025 já preservado foi reutilizado; seu catálogo foi recapturado com hash igual.
Cada detalhe declarou uma única página de até 25 registros. A conferência
documental e cadastral existente produziu o seguinte inventário:

| Ano | Entidades no catálogo de Outros Pagamentos | Entidades com Farmácia Popular | Documentos do programa | Aptos pelo cadastro preservado | Identidade histórica pendente |
| --- | ---: | ---: | ---: | ---: | ---: |
| 2021 | 6 | 6 | 108 | 48 | 60 |
| 2022 | 5 | 4 | 78 | 43 | 35 |
| 2023 | 3 | 3 | 66 | 42 | 24 |
| 2024 | 3 | 2 | 41 | 41 | 0 |
| 2025 | 3 | 2 | 25 | 25 | 0 |
| 2026 | 5 | 2 | 17 | 17 | 0 |

Contagens são por entidade/ano, não pessoas únicas entre anos. O ano 2026 está
em andamento. Seis entidades-ano de outros programas foram excluídas da
publicação de Farmácia Popular, sem exibir nomes ou conteúdo desses registros.
Os 119 documentos com identidade pendente não foram considerados errados ou
inexistentes: o cadastro atual não resolve a identidade histórica desses casos.

O plano adicional validado contém dez capturas de pagamento, o cadastro já
preservado e 191 documentos, SHA-256
`f4e1f0549362d5f0daa802f7497e393b98c06cb874fa6fc9e7f55bdb68761fdd`.
O envio adicional inicialmente foi bloqueado por falta de autorização específica,
sem representar falha da fonte ou cobertura vazia. Após autorização explícita
em 08/09/2026, as duas execuções foram retomadas e o lote foi publicado:

- Dez objetos criados e o cadastro reutilizado; onze objetos relidos byte a byte
  e conferidos por SHA-256, sem ampliar acesso ao bucket privado.
- Simulação com rollback, importação e replay; 191 payloads e hashes conferidos,
  zero divergências, seguidos de dez decisões de aprovação.
- RPC pública conferida em todas as páginas de 2021 a 2026: os 191 documentos
  adicionais correspondem ao plano em nome, data, valor e hashes, sem divergência.
- Total público: 216 documentos e 216 chaves distintas. Por ano: 48 (2021),
  43 (2022), 42 (2023), 41 (2024), 25 (2025) e 17 (2026).
- Replay após aprovação conservou 12 snapshots, 216 documentos distintos e
  12 decisões. Não houve nova aprovação nem duplicação no replay.
- Produção de 2021 exibiu 25 cartões na primeira página e 23 na segunda,
  sem link para uma terceira página inexistente.

Os 119 documentos com identidade histórica pendente continuam excluídos.
O cadastro atual não prova credenciamento histórico; estes pagamentos não são
receita municipal, emendas ou comprovação de execução. As capturas realizadas
não substituem um coletor durável com retomada automática. Próximos passos:
exibir metadados de cobertura publicada por ano e implementar essa retomada,
sem chamar o recorte atual de cobertura histórica completa.

### Contagem pública por ano

A migration `20260909001000` compartilha o mesmo gate de evidência entre a lista
e `api.get_public_pharmacy_coverage(ano)`. A contagem inclui todas as páginas,
não apenas as 25 linhas visíveis. Revogação, novo retrato pendente, duplicação
ou evidência incompatível também retiram o documento da contagem. O RPC retorna
somente contagens, datas e estado: `partial` com documentos publicados, `pending`
sem aprovação. Nunca afirma cobertura anual completa ou zero na fonte.

A interface distingue indisponibilidade dessa contagem, mostra estabelecimentos
com identidade conferida e explica que os extremos das datas não comprovam
coleta contínua. A conferência viva preservou os 216 documentos publicados.

Em produção, 2021 mostra 48 pagamentos de dois estabelecimentos. A versão nova
preservou o fingerprint integral da projeção pública
`7af550f9a04f40cf2dd0a6fc60315d7a` (MD5 usado apenas para comparação SQL, não
como hash de custódia). Desktop a 1280 px e celular a 390 px foram inspecionados
visualmente e não apresentaram overflow horizontal.

### Aquisição privada paginada e retomável

`collect_fns_other_payments_local` substitui a coleta operacional descartável
por um comando versionado. Exemplo, com `PYTHONPATH=workers/collectors/src`:

```text
python -m barreiras_collectors.commands.collect_fns_other_payments_local --year 2026 --directory .tmp/pharmacy-2026-snapshot-01 --max-requests 20
```

Repetir o mesmo comando retoma as páginas faltantes: relê, decifra e confere
as capturas existentes, sem refazer suas requisições. Uma atualização da fonte
exige outra pasta de snapshot; nunca sobrescrever os originais antigos. A pasta
não deve entrar no Git nem ser compartilhada. O comando não usa credenciais
Supabase e não faz upload, normalização ou publicação.

- Registra a execução antes da primeira requisição; estado parcial/falha retorna
  código diferente de zero. Logs contêm somente ano, contadores e estado.
- Limite de seis requisições por minuto, timeout de 45 segundos e três tentativas
  com backoff para falhas transitórias. Orçamento de até 100 requisições por
  invocação, 100 páginas por recurso e 128 MiB de arquivos locais por snapshot.
- Catálogo completo e detalhes são paginados, com escopo/quantidades consistentes,
  tamanho limitado, SHA-256 e read-back. Hash identifica bytes, não autentica a
  fonte. Aquisição via HTTPS oficial é verificada separadamente.
- Windows DPAPI CurrentUser, escritas atômicas cifradas e lock exclusivo impedem
  duas instâncias na mesma pasta. Nenhuma janela auxiliar é aberta.
- `complete` significa somente que as páginas declaradas pela fonte naquele
  retrato foram preservadas. Não significa que todos os pagamentos são Farmácia
  Popular ou publicáveis. `empty` só se refere ao catálogo oficialmente vazio.
- Detalhes com múltiplas páginas ficam privados: o publicador documental atual
  continua recusando esse caso até reconciliação dos totais entre páginas.

Prova operacional em 09/09/2026 UTC: primeira invocação limitada a uma requisição
terminou `partial`, com uma página. A retomada fez cinco requisições e terminou
`complete`, com seis páginas preservadas para cinco entidades do catálogo 2026.
O replay conferiu as mesmas seis páginas com zero requisições. Passaram 130
testes FNS (incluindo DPAPI e lock no Windows), Ruff e 692 testes Node.
Não houve upload ou alteração pública nessa prova. Os 119 documentos históricos
sem identidade comprovada continuam fora da publicação; isso é uma limitação
explicitamente registrada, não um motivo para inferir identidade por nome.

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
