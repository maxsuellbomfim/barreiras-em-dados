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

O bloco oficial de autoria `4072` foi ligado, apenas para 2019-2023, ao perfil
institucional 197438 da Câmara dos Deputados, que identifica o nome parlamentar
Tito e o nome civil Carlos Tito Marques Cordeiro. O vínculo usa código, período
e fontes institucionais; não usa semelhança nominal e não se estende a outros
exercícios.

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
não processada. A projeção pública aceita somente linhas validadas e a autoria
entra no ranking apenas após a reconciliação oficial descrita acima.

O processamento `bahia_special_transfer_payments_v3` também produz uma
cobertura anual sanitizada do retrato integral. Para cada exercício publicado
no ZIP a partir de 2021, ela registra somente a quantidade total de pagamentos
da fonte e a quantidade cujo objeto contém a palavra territorial literal
`Barreiras`. O analisador confere o arquivo inteiro, inclusive linhas anteriores
ao marco de cobertura do Barreiras 360; a projeção anual, porém, respeita
explicitamente o intervalo declarado de 2021 em diante. Nome, CPF/CNPJ e demais
campos do credor não entram nesse resultado. Essa contagem é diagnóstico de
cobertura: não representa quantidade de emendas, valor pago, receita recebida
pela Prefeitura nem completude histórica. A mudança para `v3` provoca um único
replay idempotente dos artefatos já processados e corrige a inclusão indevida
de 2020 em um contrato cujo início declarado é 2021.
A RPC `api.get_public_bahia_special_transfer_annual_coverage` expõe somente
essas contagens e a linhagem do retrato mais recente. A tabela intermediária
permanece inacessível aos papéis públicos.

## Estado de publicação

- bruto: elegível para preservação privada;
- manifestos: elegíveis para auditoria administrativa;
- três pagamentos: normalizados com schema e validação versionados;
- ranking e totais públicos: habilitados somente nesta fonte, após
  reconciliação determinística do código 4072 no período 2019-2023;
- cobertura anual do retrato: pública como contagem de linhas, nunca como soma
  financeira ou declaração de completude histórica;
- nenhuma soma com LOA, CGU ou Transferegov; coincidências servem apenas para
  auditoria por código;
- CPF/CNPJ: proibido em projeção pública, logs, erros e manifestos.

## Fontes oficiais

- https://dados.ba.gov.br/pt_PT/dataset/transferencias-especiais
- https://dados.ba.gov.br/api/3/action/package_show?id=transferencias-especiais
- https://dados.ba.gov.br/dataset/f2ecd7fa-24ce-4be2-80d5-08e2c11e3e1c/resource/809f9b7d-c252-482d-9c92-f2169d48c29c/download/transferenciasespeciais.zip
- https://dados.ba.gov.br/dataset/f2ecd7fa-24ce-4be2-80d5-08e2c11e3e1c/resource/c99d7839-230d-4f74-bf15-d89a6e92ca8c/download/transferencias-especiais_relacionamento_views.png
