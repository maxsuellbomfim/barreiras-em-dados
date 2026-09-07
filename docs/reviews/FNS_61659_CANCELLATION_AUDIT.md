# Conferência FNS da ação 61659 — 06/09/2026

## Resultado

Foram preservados localmente, com DPAPI CurrentUser e SHA-256 de reabertura,
255 registros de pagamento das 26 ações adicionais, em 27 páginas. A captura
não equivale a normalização, registro no Supabase ou publicação.

A comparação encontrou uma diferença de R$ 1.493,93 na ação 61659:

| Recorte oficial | Bruto | Descontos | Líquido |
| --- | ---: | ---: | ---: |
| Catálogo atualizado | 54.466.271,01 | 69.428,00 | 54.396.843,01 |
| Soma das 15 linhas do detalhe | 54.467.764,94 | 69.428,00 | 54.398.336,94 |

As quatro páginas do catálogo atual reproduzem os totais do catálogo anterior.
O detalhe de pagamento publica um total geral que coincide com suas 15 linhas,
mas não com o catálogo. Não se trata apenas de comparar duas datas de captura.

## Ordens conferidas

As ordens 016551 e 018794 foram consultadas em todas as quatro páginas cada
(10, 10, 10, 5 linhas). Cada resposta abrange 35 municípios; há exatamente uma
linha Barreiras/BA, código FNS 290320, por ordem. As requisições usam anoPagamento
2025, mes 04 e ano 2025 do identificador do pagamento, competência Única em
2025, UF BA e tipo OB. O mês de competência não foi trocado pelo mês do crédito.

- **016551**, documento de 02/06/2025: R$ 1.493,93 e motivo de rejeição com
  mensagem explícita de cancelamento parcial, tanto no pagamento quanto na OB.
- **018794**, documento de 12/06/2025: R$ 1.493,93 e motivo de rejeição vazio.
- No detalhe do pagamento, `valorAnulacao` é zero em ambas.
- Ambas pertencem ao processo 25000.064601/2025-38, mas são documentos distintos.

Excluir aritmeticamente o valor da linha sinalizada reproduz o catálogo. Isso
é compatível com o catálogo desconsiderá-la, mas **não prova substituição entre
as ordens**, nem autoriza alterar retroativamente os originais ou chamar a
segunda linha de duplicada. Tampouco prova irregularidade ou execução física.

## Consequência para o processamento

O leitor de pares existente já bloqueia `motivoRejeicao` não vazio em qualquer
lado, mesmo com anulação numérica zero. Um teste sintético explícito protege
essa combinação, inclusive contra vazamento do texto recebido em exceções.
Nenhuma regra de soma ou ranking foi modificada.

O leitor ampliado deve preservar os dois registros, a situação textual e a
divergência numérica. Não deve aceitar apenas a primeira página da OB nem
deduplicar somente pelo identificador composto do pagamento. É necessário
separar competência, data de pagamento e documento SIAFI e registrar conflitos
sem convertê-los em pagamentos efetivos ou emendas automaticamente.

## Rastreabilidade local

### Diagnóstico paginado implementado

`inspect_order_pages` recebe a sequência completa dos originais de uma OB,
na ordem das requisições. Confere contagem, tamanho das páginas, metadados
estáveis, hashes repetidos, código territorial e nome. Não escolhe a primeira
ocorrência se houver outra linha de Barreiras, mesmo idêntica. Recusa conflito
entre nome, código e UF. Rejeição não vazia gera `review_required`, sem devolver
texto bruto ou um valor publicável. A ausência gera `not_found`, nunca zero.

Na execução sobre as oito páginas reais preservadas, 016551 retornou
`review_required` e 018794 retornou `unique_territorial_row`, valor documental
1.493,93. Todos os resultados têm `publication_allowed=false`; linha única não
é pagamento confirmado, emenda identificada ou aprovação editorial. Os hashes
das quatro páginas acompanham cada diagnóstico válido. Não há rede, gravação
no banco nem alteração do leitor estrito de pares existente.

O corpo dessa API não comprova a identidade global da OB. O diagnóstico só
pode ser integrado à persistência após o chamador validar URL, parâmetros,
datas, escopo e hash dos originais. Ainda falta o fluxo de múltiplos pagamentos
e sua reconciliação; não converter o resultado em candidato CGU diretamente.

Manifestos das capturas complementares (SHA-256):

- primeira página das duas OBs e quatro páginas do catálogo:
  `f3fbe249d333008512647b9acf9ece946e0d046b07de4b7e9fc66846f6e563f9`;
- seis páginas restantes das OBs:
  `8cb07e62cb6556182b7af1328d79852b089789175fd4d5621f4cb8ff986b852f`.

Os manifestos incluem URL exata, horários, HTTP, tamanho e hash de cada resposta.
Originais ficam cifrados na pasta operacional local `.tmp`, fora do Git.
Fonte: consulta detalhada oficial em https://consultafns.saude.gov.br/#/detalhada,
rotas `consulta-detalhada/detalhe-acao` e `detalhe-ordem-bancaria`.
Nenhum dado bancário, original sensível ou novo vínculo público integra esta entrega.

### Integração ao registro privado

O serviço `FNSOrderPersistenceService` reutiliza os contratos de captura,
Storage e repositório já existentes. Valida a sequência completa, URLs de
requisição e resposta, escopo, HTTP, tipo, tamanho, hash e horários com fuso;
relê todos os objetos antes de registrar o primeiro artefato. Uma falha de
integridade bloqueia o lote inteiro antes das gravações. Falha posterior no
banco exige replay: as gravações são individualmente idempotentes, não uma
transação única. As chaves incluem escopo, página e hash; não confundem ordens
distintas que eventualmente devolvam bytes iguais.

Cancelamento, ausência e conflito territorial podem ser preservados como
originais para revisão. Nenhum registro financeiro é produzido e a cobertura
continua parcial. O leitor estrito de pares permanece separado e inalterado.

A execução local do adaptador sobre oito originais reabertos por DPAPI
reproduziu os oito hashes e os dois diagnósticos anteriores. Os manifestos,
porém, não contêm URL final da resposta, somente URL solicitada. Portanto
essa execução comprova consistência com as requisições registradas, não todos
os requisitos de importação. Nenhuma gravação real no Supabase foi feita;
era necessária nova captura com metadados completos. Os originais anteriores
permanecem preservados, sem horários ou URLs completados por suposição.

A recaptura subsequente das oito páginas, limitada a seis requisições por minuto,
registrou URLs solicitada e final, horários, HTTP, tipo, tamanho e hash. Todos
os oito hashes reproduziram os originais anteriores. O serviço validou quatro
páginas de cada OB em simulação com repositório em memória: 016551 segue em
revisão e 018794 com linha territorial única. Não houve escrita no Supabase.
Os bytes foram novamente cifrados com DPAPI e reabertos para conferir SHA-256.
Manifesto da nova captura:
`a084b8786db7e3b24d429a0767f4b4ded99ea7eee29364341cffc0b349d704fa`.

### Importação privada concluída

Execução `e6fe9f01-8641-4cbf-8378-577a96e655d4`, partição
`pilot:2025:orders:016551-018794`, no endpoint `payment-order-detail`:

- oito objetos novos no prefixo privado `fns/payments/2025/sha256/`;
- oito artefatos registrados pelo serviço já mesclado;
- replay real devolveu exatamente os mesmos oito IDs;
- download pós-registro confirmou bytes, SHA-256, tamanho, HTTP e tipo;
- consulta SQL independente confirmou oito artefatos, URLs inicial/final
  correspondentes à captura e zero linhas em `raw.raw_records` para esses IDs;
- execução e partição permaneceram `partial`, com `publication_allowed=false`.

O controle foi aberto antes da autenticação no Storage e da primeira escrita.
A carga usou os bytes recapturados e os horários reais, sem nova requisição ao
FNS e sem reescrever os originais antigos. Não houve lançamento financeiro,
aprovação editorial, alteração de autoria ou soma adicional no portal.
Os diagnósticos foram mantidos: 016551 exige revisão; 018794 tem linha territorial
única, o que não basta para publicá-la como pagamento confirmado.

Próximo passo: normalizar as páginas de múltiplos pagamentos e relacioná-las
às ordens por chaves documentais completas, mantendo o cancelamento e a
divergência do catálogo explícitos. Os 255 registros adicionais não estão
normalizados nem publicados por esta importação.

### Normalização local das páginas de pagamento

O leitor privado `fns_payment_pages` processou as 27 páginas preservadas e
conferidas por hash: 255 observações em 26 ações, sem excluir nenhuma linha.
Sete observações têm ano de competência diferente do ano do pagamento. A chave
documental inclui ação, escopo da OB, processo e data; nenhuma chave se repetiu
nesse recorte, apesar dos identificadores compostos repetidos na fonte.

A ação 61659 continua `review_required` pela rejeição de uma linha; as outras
25 tiveram estrutura normalizada. Isso não comprova execução financeira nem
reconciliação com o catálogo: o total documental inclui a linha rejeitada e
não deve ser exibido como total efetivamente pago. Anulação numérica, motivo de
rejeição e equilíbrio bruto/desconto/líquido são avaliados separadamente.

Cada observação mantém página, posição e hash original, com campos bancários
excluídos da saída. Nenhuma ordem é automaticamente vinculada: todas saem com
`order_verification=pending` e `publication_allowed=false`. O chamador ainda deve
vincular cada conjunto ao escopo de aquisição e persistir os resultados privados.
Esta execução não criou linhas no banco nem adicionou valores ao site.
