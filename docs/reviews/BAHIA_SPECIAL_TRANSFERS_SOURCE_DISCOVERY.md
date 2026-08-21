# Descoberta controlada — Transferências Especiais da Bahia

Data da verificação: 21/08/2026.

## Resultado

O Portal de Dados Abertos da Bahia publica o conjunto oficial
**Transferências Especiais**, atualizado em 20/08/2026. O catálogo CKAN aponta
para um ZIP de 554.925 bytes com cinco views. O conector valida URL, recurso,
tamanho, MIME, membros, cabeçalhos, limites de descompressão e hashes antes da
persistência.

| View | Linhas validadas | Chave observada |
|---|---:|---|
| centralização/descentralização | 3.861 | `num_codigo`, `num_codigo_exec`, `num_codigo_liqu` |
| despesa | 1.129 | emenda, exercício, autor, ação e estágios financeiros |
| instrumento de captação | 226 | instrumento, valor e assinatura |
| liquidação | 2.777 | `num_codigo_liqu` |
| pagamento | 4.176 | pagamento, empenho e `num_codigo_exec` |

Total estrutural validado: **12.169 registros**. O manifesto não contém linhas,
valores individuais nem amostras do campo `CNPJ_CPF_CREDOR_PAGAMENTO`.
O ZIP integral fica em corredor privado, endereçado por SHA-256.

## Imperfeição do CSV oficial

A view de pagamentos contém aspas não escapadas dentro do campo `Objeto`. Um
parser permissivo a fragmenta em 4.198 linhas aparentes. O fallback do Barreiras
360 não corrige nem reescreve o objeto: recupera apenas os limites de 4.176
registros que apresentam simultaneamente ID de pagamento com 18 ou 19 dígitos,
código estruturado de execução e URL oficial de pagamento no final. Quinze IDs
com 18 dígitos permanecem como aviso auditável da fonte.

## Evidência territorial localizada

Somente três pagamentos possuem a palavra literal `Barreiras` no objeto. O
relacionamento oficial entre `num_codigo_exec` e `num_codigo` conduz cada um a
uma única linha de despesa:

| Emenda publicada | Autor publicado | Pagamento | Objeto territorial |
|---|---|---:|---|
| 40720003/2021 | Tito | R$ 594.841,25 | peças e acessórios para poços em Barreiras |
| 40720005/2021 | Tito | R$ 75.300,00 | peças e equipamentos para poços em Barreiras |
| 40720005/2021 | Tito | R$ 86.763,50 | peças e equipamentos para poços em Barreiras |

O total dos três pagamentos é R$ 756.904,75. Isso comprova pagamentos estaduais
cujo objeto menciona Barreiras; isoladamente, não comprova transferência direta
à Prefeitura, recebimento municipal ou conclusão física do objeto.

O nome `Tito` ainda não é ligado automaticamente a uma pessoa. A view também
não declara, em campo próprio, se a autoria pertence à esfera federal ou
estadual. O número da emenda, o exercício e outras fontes oficiais deverão
resolver identidade e esfera antes de qualquer inclusão em ranking.

## Normalização determinística

O parser `bahia-special-transfer-payment/1.0.0` restaura a view de pagamentos
pelos limites estruturados já validados na coleta e descarta CPF/CNPJ e nome do
credor antes de criar qualquer resultado. CPF ou CNPJ eventualmente escrito no
próprio objeto também é mascarado na evidência normalizada; o original continua
somente no ZIP privado. O vínculo usa apenas
`num_codigo_exec` da linha de pagamento, `num_codigo_exec`/`num_codigo` da view
de centralização e `num_codigo` da despesa. Várias liquidações da mesma despesa
são preservadas como uma lista; mais de uma despesa distinta para o mesmo
pagamento bloqueia a extração.

No ZIP preservado em 21/08/2026, o replay local produziu exatamente três
candidatos, somando R$ 756.904,75 por decimal exato. O valor de GCV não foi
publicado nessas três linhas e permanece nulo, nunca convertido em zero. O
processamento registra job versionado, hash do ZIP e hash de uma evidência
sanitizada por pagamento. Um resumo técnico versionado também registra zero
candidatos quando isso ocorrer, sem confundir fonte processada com fonte ainda
não processada. A projeção pública continua bloqueada até a autoria `Tito` ser
reconciliada com pessoa, esfera e período por fonte oficial.

## Estado de publicação

- bruto: elegível para preservação privada;
- manifestos: elegíveis para auditoria administrativa;
- três pagamentos candidatos: normalização implementada, pendente de execução
  remota e reconciliação de autoria;
- ranking e totais públicos: bloqueados até reconciliação determinística;
- CPF/CNPJ: proibido em projeção pública, logs, erros e manifestos.

## Fontes oficiais

- https://dados.ba.gov.br/pt_PT/dataset/transferencias-especiais
- https://dados.ba.gov.br/api/3/action/package_show?id=transferencias-especiais
- https://dados.ba.gov.br/dataset/f2ecd7fa-24ce-4be2-80d5-08e2c11e3e1c/resource/809f9b7d-c252-482d-9c92-f2169d48c29c/download/transferenciasespeciais.zip
- https://dados.ba.gov.br/dataset/f2ecd7fa-24ce-4be2-80d5-08e2c11e3e1c/resource/c99d7839-230d-4f74-bf15-d89a6e92ca8c/download/transferencias-especiais_relacionamento_views.png
