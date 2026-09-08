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
