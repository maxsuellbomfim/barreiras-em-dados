# FNS — SAMU 192, primeiras três ordens de 2025

Em 08/09/2026 UTC, foram consultadas as ordens 000366, 001796 e 006267
da ação 62079 (SAMU 192 no catálogo FNS preservado). Cada resposta tem
27 páginas; as 81 páginas completas foram preservadas com DPAPI do Windows,
URLs de aquisição/final, horários, tamanho e SHA-256. A coleta respeitou
seis requisições por minuto. Não houve falha de requisição neste lote.
Conteúdo preservado: 256.778 bytes. SHA-256 do manifesto:
`e04b9aacb60277b5cc02d076fee203a679b4623b6bb301ac8140454b7f462a13`.

| OB | Competência literal | Páginas | Conferência |
| --- | --- | --- | --- |
| 000366 | 01/12 em 2025 | 27 | Par documental compatível |
| 001796 | 02/12 em 2025 | 27 | Par documental compatível |
| 006267 | 03/12 em 2025 | 27 | Par documental compatível |

As páginas incluem outros municípios; não são 81 documentos exclusivos de
Barreiras. Os leitores validaram a paginação completa e a correspondência
territorial, temporal e de valor com os pagamentos de Barreiras preservados.
Pagamento de origem: `a9fbe6ef2ef8f6d2f1f7588b3405de63e44afb212c739d2968f2f74d5f0fe1d8`,
página 1, linhas 1–3. Compatibilidade não comprova execução financeira,
autoria de emenda ou autorização de publicação.

## Estado da entrega

- Simulação dos serviços de persistência: 81 páginas válidas e três
  `consistent_documentary_pair`, todos com `publication_allowed=false`.
- Diagnóstico SQL anterior: nenhuma comparação da ação 62079 registrada.
- A primeira tentativa de importação foi bloqueada antes de iniciar. Após
  autorização explícita do usuário para o lote e destino privados, foi retomada
  e concluída, conforme o registro abaixo.
- Os originais locais cifrados foram preservados no diretório operacional
  `.tmp/fns-next-orders-5292ebdca53641c7af3868296d51dcc3`.
- Nenhum valor, ranking ou atribuição pública foi alterado.

## Importação autorizada e verificação

A execução `04c3dd8e-4b68-4e05-9eae-93f29ed343ff` preservou os 81 objetos
no bucket privado `raw-artifacts`, registrou os 81 artefatos de ordens e três
comparações `fns_document_comparison`. O controle foi aberto antes de qualquer
escrita. Os pagamentos de origem já preservados foram relidos; a coleta no
FNS não foi repetida.

Após a carga, o download das 81 respostas coincidiu byte a byte com os
originais locais. SQL conferiu hashes, tamanhos e URLs dos artefatos e os três
payloads/hashes de comparação. A reexecução das comparações retornou os mesmos
artefatos e inseriu zero novas linhas.

O comando `audit_fns_comparisons --action-id 62079 --payment-year 2025`
foi executado posteriormente em conexão independente, somente leitura:
três versões `current_preserved_evidence`, todas `consistent_documentary_pair`,
dentre 141 artefatos FNS examinados. Código 0 significa compatibilidade das
comparações presentes, não cobertura completa da ação ou confirmação de
execução financeira.

O lote continua `partial` e `publication_allowed=false`. Nenhum pagamento,
valor, autoria ou ranking público foi criado ou alterado. Faltam as demais
ordens dessa ação e das outras ações FNS; próximo passo é planejar e coletar
o lote seguinte, sem repetir estas três ordens.

Validação local: 97 testes FNS e 678 testes Node aprovados. Nenhum código de
produção ou migration foi alterado nesta etapa.

## Quarta ordem: 010181

Em 08/09/2026, a quarta ordem foi conferida em 27 páginas completas,
85.695 bytes, preservadas localmente com DPAPI. Manifesto SHA-256:
`697619f9bbed4940aebfaa288d22f6aa300e1c31e480f7d0755210cf56890aed`.
O escopo oficial informa `mes=03` e competência literal `04/12 em 2025`;
ambos foram mantidos, sem substituir um campo pelo outro. O pagamento
correspondente está na linha 4 da página 1 do mesmo original acima.

Após autorização explícita para estas 27 páginas e uma comparação privada,
a execução `0bf0f796-ac7c-412e-81c6-da3e62809b29` importou 27 objetos no
bucket privado e registrou a comparação. Releitura dos bytes e consulta SQL
conferiram o resultado; replay inseriu zero comparações adicionais.

Auditoria independente somente leitura: 169 artefatos examinados, quatro
comparações atuais e documentalmente compatíveis, código de saída 0.
A cobertura continua parcial e a publicação permanece bloqueada. Nenhum
valor, autoria ou ranking público foi alterado.

O retrato preservado contém 14 ordens: quatro conferidas e importadas neste
fluxo, dez ainda pendentes. Há ordens distintas nas competências 09/12 e 10/12;
isso não permite concluir duplicidade. Próxima ordem: 013631.

## Quinta ordem: 013631

Após autorização explícita, a execução
`e4e19605-9f26-454d-aeba-48224130d83d` importou 27 páginas completas
(85.695 bytes) da ordem 013631 e registrou uma comparação privada.
Manifesto SHA-256:
`aac8e322b36eedffd78794b44173502928f319e5a682abdea2eafebc7216acff`.
O pagamento correspondente está na linha 5 da página 1 do original já citado.
Os arquivos foram relidos byte a byte; SQL conferiu os metadados e o registro.
A reexecução inseriu zero comparações adicionais.

Auditoria independente somente leitura: 197 artefatos examinados, cinco
comparações atuais e documentalmente compatíveis, código 0. Isso não comprova
execução financeira, autoria ou cobertura anual. Nenhum valor público alterado.
Estado deste retrato: cinco ordens importadas e nove pendentes de conferência.
Próxima ordem: 018188. Não deduplicar as ordens pela competência.

## Captura consolidada das nove ordens restantes

As nove ordens restantes foram capturadas integralmente, em dois lotes locais
cifrados, com limite de seis requisições por minuto. Os serviços de validação
releram os originais e encontraram nove pares documentalmente compatíveis,
todos com publicação não autorizada. Isso não comprova execução financeira.

| Ordem | Páginas completas |
| --- | ---: |
| 018188 | 27 |
| 025203 | 29 |
| 036136 | 29 |
| 046416 | 29 |
| 054370 | 29 |
| 061706 | 2 |
| 061703 | 2 |
| 061633 | 29 |
| 070640 | 29 |

Primeiro lote: 145 páginas, 460.180 bytes; manifesto SHA-256
`a1f6284dd2323d484c5def8b46271a72489e3ad606b377f9869c3092f857d405`.
Segundo lote: 60 páginas, 189.065 bytes; manifesto SHA-256
`424a7b7adc244cf6d53cd2789c8f830804ecf27cdf476de28e4315d60db30011`.

O envio das nove restantes foi inicialmente bloqueado antes de executar.
Após autorização explícita consolidada para as 205 páginas e nove comparações,
os dois lotes foram importados no bucket privado. A primeira tentativa autorizada
parou antes de gravar porque o namespace local excedia o tamanho permitido;
o identificador foi encurtado com hash das ordens e a execução foi repetida.

| Execução | Páginas importadas | Comparações | Novas comparações no replay |
| --- | ---: | ---: | ---: |
| `3c64d426-4ed0-480f-b90c-6f4d142db332` | 145 | 6 | 0 |
| `6fbd5c7e-0914-44e5-83e3-b84a7b4082a9` | 60 | 3 | 0 |

Os arquivos foram relidos byte a byte; SQL conferiu hashes, tamanhos, URLs e
payloads das comparações. Não foram criados lançamentos financeiros públicos.

Auditoria independente anterior à importação relê o pagamento original do
bucket, deriva as 14 ordens esperadas, confere escopos e recompõe os pares
a partir dos bytes. Confirmou cinco ordens no banco, nove ausentes, nenhuma
versão repetida, 135 páginas de ordens e 136 objetos com SHA-256 revalidado.
O resultado é PARTIAL, não fechamento de cobertura. Nenhum valor público mudou.

Depois da importação, o comando oficial `audit_fns_comparisons` encontrou
14 comparações atuais e compatíveis entre 411 artefatos examinados, código 0.

## Fechamento verificado do retrato

A auditoria independente final baixou novamente os objetos privados e derivou
as ordens esperadas dos bytes do pagamento original, em vez de confiar em uma
contagem pré-fixada de registros. Conferiu hashes, tamanhos, URLs, escopos e
atualidade; recompôs cada comparação com os leitores existentes.

- Resultado: PASS; 14 ordens esperadas e 14 verificadas.
- Nenhuma ordem ausente e nenhuma versão de comparação repetida.
- 340 páginas de ordens verificadas; 341 objetos com SHA-256 recalculado,
  incluindo a página de pagamentos de origem.
- 14 pares documentalmente compatíveis; publicação não autorizada.
- 97 testes FNS e 678 testes Node passaram; `git diff --check` sem erros.

Isso fecha a conferência documental privada deste retrato de 2025, não a
cobertura anual do FNS. As partições operacionais permanecem `partial`;
nenhum estágio financeiro, autoria ou ranking público foi criado ou alterado.
As competências repetidas continuam com suas ordens distintas. A próxima
frente é verificar os demais recortes FNS e a modalidade Outros Pagamentos,
sem somar essas observações aos lançamentos financeiros já publicados.
