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

## Conflitos

`source_conflicts` deve preservar:

- campo e entidade afetados;
- valores concorrentes;
- evidência de cada valor;
- gravidade e impacto de publicação;
- estado (`open`, `resolved`, `accepted_difference`, `obsolete`);
- decisão, revisor e metodologia usada.

## Pessoas e minimização

- pessoa não é identificada internamente por CPF publicado;
- documento fiscal, quando indispensável para reconciliação autorizada, fica
  cifrado/restrito e deriva apenas marcador/últimos dígitos necessários;
- folha pública prioriza remuneração bruta agregada e componentes permitidos;
- descontos pessoais detalhados não entram em projeções públicas;
- documentos brutos são classificados antes de receber acesso público;
- fixtures removem dados pessoais não necessários.

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
