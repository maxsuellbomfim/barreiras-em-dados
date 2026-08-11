# Governança de dados

## Classificação das camadas

| Camada | Mutabilidade | Publicação |
|---|---|---|
| Resposta/documento bruto | append-only | privada por padrão |
| Texto/OCR/páginas | nova versão por parser | interna |
| Extração candidata | versionada | revisão |
| Registro normalizado | temporal/versionado | não diretamente |
| Projeção aprovada | substituição auditada | pública |
| Evento de auditoria | append-only | interna |

## Cadeia de custódia

Cada coleta registra:

- fonte e endpoint cadastrados;
- URL solicitada e URL final;
- método, parâmetros/cursor e horários;
- status HTTP e cabeçalhos permitidos;
- versão do coletor e contrato;
- hash SHA-256, tamanho e MIME detectado;
- execução, tentativa e resultado;
- chave do objeto preservado.

Além do manifesto bruto, a partição lógica registra período, quantidade
observada, checkpoint e um estado explícito: `complete`, `empty`, `partial`,
`failed` ou `blocked`. Limite operacional não significa cobertura completa;
zero linhas só significa vazio quando a consulta terminou normalmente. No
PNCP, tetos de backlog ou paginação de itens e contratos produzem `partial` e
registram quais contratações precisam continuar. Uma releitura idempotente sem
novas inserções não é confundida com ausência de dados. O cursor de backlog
evita que as primeiras 50 contratações impeçam indefinidamente a visita das
demais.
Snapshots de representação são separados por casa, endpoint e eleição. Uma
lista incompleta de perfis gera `partial`; arquivo eleitoral ainda não publicado
gera `blocked`; falha de transporte ou autenticação gera `failed`, nunca uma
composição pública falsamente vazia. Leis e indicações possuem cobertura
distinta mesmo quando compartilham a mesma API municipal.
Checkpoints são consumidos somente por workers autorizados. Retomadas automáticas
aceitam cursores tipados e não negativos; valor inválido reinicia a paginação de
forma segura, e uma intervenção explícita do operador prevalece sobre o cursor.

Um registro derivado só é elegível à publicação quando `evidence_items` aponta
para origem bruta preservada e, em atos documentais, para página/trecho.

## Imutabilidade

- `raw_artifacts`, `raw_records` e `audit_events` não admitem UPDATE/DELETE por
  roles da aplicação.
- Conteúdo idêntico pode ser referenciado por várias coletas.
- Mudança no conteúdo cria novo hash e novo artefato.
- Reprocessamento cria novo resultado com `parser_version`; não reescreve o
  anterior.
- Retificação normalizada cria nova versão temporal e vínculo de supersessão.

## Idempotência

Cada operação de ingestão recebe `idempotency_key`. Uma constraint única torna o
upsert atômico. A chave não usa somente URL, porque URLs podem variar sem mudar o
conteúdo ou manter-se estáveis com conteúdo novo.

A sequência de persistência é:

1. validar bytes, tamanho e hash em memória;
2. enviar para chave endereçada por conteúdo sem sobrescrita;
3. restaurar e verificar o objeto;
4. registrar metadados e linhas brutas em uma transação curta.

Artefatos maiores que o limite operacional são preservados em partes imutáveis.
O manifesto registra versão do formato, tamanho e SHA-256 integral, tamanho das
partes e, para cada parte, posição, chave, tamanho e SHA-256. A restauração aceita
somente a sequência e as chaves derivadas deterministicamente do artefato. Uma
parte ausente ou divergente invalida a leitura; partes já gravadas permanecem
para que o retry idempotente possa verificá-las e reutilizá-las.

Falha no passo 4 não apaga o objeto. Um reconciliador futuro identifica objetos
sem referência e decide entre recompor a referência ou mantê-los em quarentena;
expurgo automático não é permitido.

## Qualidade

Dimensões acompanhadas por fonte e campo:

- completude;
- validade de formato/domínio;
- unicidade;
- consistência interna;
- consistência entre fontes;
- atualidade;
- precisão estimada contra amostra anotada;
- rastreabilidade.

Rejeições são registradas com código determinístico. Registros inválidos vão
para revisão/DLQ; não são descartados silenciosamente.

### Obrigações financeiras

- saldo inicial, acréscimos, reduções, pagamentos e saldo final são campos
  distintos e não podem ser somados como se representassem o mesmo estágio;
- cada obrigação normalizada mantém órgão, período, tipo, versão e registro
  bruto de origem;
- valor negativo em uma obrigação é rejeitado pelo contrato; estornos e
  deduções devem ser modelados no estágio financeiro correto, sem transformar
  automaticamente um sinal negativo em anomalia;
- somente linhas validadas ou reconciliadas entram na RPC pública;
- ausência de linha publicada significa “ainda não reconciliada”, nunca dívida
  zero;
- um total municipal só será elegível depois de eliminar duplicidade entre
  períodos e versões e reconciliar fontes oficiais independentes.

## Conflitos

`source_conflicts` deve preservar:

- campo e entidade afetados;
- valores concorrentes;
- evidência de cada valor;
- gravidade e impacto de publicação;
- estado (`open`, `resolved`, `accepted_difference`, `obsolete`);
- decisão, revisor e metodologia usada.

## Pessoas e minimização

- CPF fornecido por fonte oficial pode ser usado internamente como sinal forte
  de reconciliação, mas nunca como identificador público ou prova isolada;
- o valor indispensável fica cifrado no schema `private`; comparações usam
  HMAC-SHA-256 com chave separada, e o diagnóstico comum vê no máximo os quatro
  últimos dígitos;
- secretários sem CPF em fonte oficial continuam reconciliáveis por cargo,
  órgão, vigência e evidências; fontes obscuras ou vazamentos são proibidos;
- folha pública prioriza remuneração bruta agregada e componentes permitidos;
- descontos pessoais detalhados não entram em projeções públicas;
- documentos brutos são classificados antes de receber acesso público;
- fixtures removem dados pessoais não necessários.

## Identidade e relações

- nome semelhante nunca confirma pessoa ou empresa;
- CNPJ exato pode confirmar pessoa jurídica dentro da validade e da fonte;
- CPF completo não é chave pública e não aparece em projeções;
- divergência entre fingerprints de CPF impede fusão automática e gera
  `source_conflicts` para revisão;
- associação de pessoa natural exige identificador permitido ou revisão humana
  com duas evidências independentes quando houver impacto reputacional;
- toda aresta de relacionamento possui evidência própria, data e validade;
- vínculo societário, contratual, eleitoral ou funcional não implica amizade,
  influência, benefício, coordenação ou culpa;
- candidatos de reconciliação permanecem internos e expiram ou são resolvidos
  por decisão auditada.

## Dados judiciais, eleitorais e sancionatórios

- processo aberto não equivale a condenação;
- classe/assunto não substitui leitura do papel processual e da decisão;
- sanção de pessoa jurídica não é herdada automaticamente por sócio,
  administrador, agente público ou contratante;
- declaração de bens do TSE é um retrato autodeclarado de uma eleição, não
  patrimônio atual;
- datas de início, fim, situação, recurso, retificação e fonte permanecem
  visíveis;
- nova classe de dado reputacional exige avaliação de impacto, base/finalidade,
  minimização, política editorial e revisão jurídica antes da coleta em escala.

## Retenção

| Dado | Política inicial |
|---|---|
| Artefato público bruto | preservação permanente, sujeito a revisão legal |
| Metadado/hash/proveniência | permanente |
| Extrações e versões | permanente |
| Mensagens concluídas | arquivar por 1 ano; revisar custo anualmente |
| DLQ | até resolução e depois arquivar por 2 anos |
| Logs operacionais | 90 dias |
| Logs de segurança/admin | 1 ano |
| Backups | 35 dias + teste trimestral de restauração |

Legal hold e incidente suspendem expiração aplicável. Expurgo autorizado gera
evento de auditoria e não remove hash/proveniência mínima quando legalmente
possível.

## Direitos, correções e contestação

O portal terá canal acessível para correção, contextualização e exercício de
direitos. Solicitações recebem protocolo, análise humana e decisão registrada.
Correção pública indica o que mudou, quando e por quê.

## Base normativa

Esta política técnica não substitui revisão jurídica. Deve ser validada à luz da
[Lei de Acesso à Informação](https://www.planalto.gov.br/ccivil_03/_ato2011-2014/2011/lei/l12527.htm)
e da
[LGPD](https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2018/lei/l13709compilado.htm),
especialmente finalidade, adequação, necessidade, transparência, segurança e
direitos dos titulares.
