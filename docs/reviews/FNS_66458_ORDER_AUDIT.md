# FNS — ordens da ação 66458

Consulta em 07/09/2026 UTC (noite de 06/09 em Barreiras). Escopo Fundo a Fundo,
pagamentos de 2025. Não representa cobertura anual nem novos repasses públicos.

Os parâmetros foram derivados dos pagamentos preservados, seguindo o
`ordemBancariaController.js` oficial anteriormente preservado: `anoPagamento`,
`id.ano`, `id.mes`, competência literal, UF, número e tipo do documento.
Não substituir o mês/ano da competência pela data de pagamento.

| OB | Ano/mês do identificador | Competência literal | Resultado |
| --- | --- | --- | --- |
| 002194 | 2024/11 | NOV de 2024 | HTTP 200; lista vazia |
| 005367 | 2024/12 | DEZ de 2024 | HTTP 200; lista vazia |
| 012009 | 2025/04 | FEV de 2025 | Par documental compatível |

As respostas vazias têm `pagina=0`, `total=0`, `totalPaginas=0`,
`itensPorPagina=10`, `dados=[]`. Isso significa somente que esta consulta
não encontrou linhas. Não demonstra inexistência da ordem, ausência do
pagamento ou valor financeiro zero. Não houve tentativa de trocar parâmetros
para obter uma correspondência aparente.

A primeira tentativa foi interrompida após preservar 002194: o script local
esperava paginação positiva. Essa falha está mantida no manifesto. A tentativa
seguinte consultou apenas as duas ordens restantes. O leitor também tratava a
resposta vazia como `invalid_pages`; o teste de regressão reproduziu a falha.
Agora ela é `not_found` (no par, `order_not_found`), com hash e sem autorização
de publicação. Metadados inconsistentes e escopos diferentes continuam bloqueados.

## Custódia e limites

Três respostas cifradas com DPAPI do Windows, URLs solicitada/final,
horários, HTTP, tamanho e SHA-256 registrados. Releitura local confirmou os
hashes antes da interpretação. As duas respostas vazias têm bytes idênticos,
mas pertencem a consultas distintas; não são documentos financeiros duplicados.

- Pagamentos de origem: `ea26d5a1a8da35db2534fa54f6a90b3675457db8b02b57113aaa5b8005db0f59`, linhas 1–3.
- Respostas vazias: `bf06ab5c45ecb0c3fb7d0cc6f1e7e3506abb93b0e995be07f7696be04bd894e1`.
- Resposta 012009: `cb4af842cc9e4b22104d646c17d31e5389552290f17c2ec2bbeab2cdd9195b7d`.
- Manifesto da tentativa interrompida: `4c51708842fb04421cebd24207ea08088b5d42518d35fbc5f54256d2494e1fa9`.
- Manifesto das duas restantes: `5649438f6cc01726122509bacaed65f7ca6f6b1beb217e92d8ff0da44057ae3a`.

O par 012009 tem valor líquido, território e eco temporal compatíveis.
Isso não confirma execução financeira nem autoria de emenda. Nenhum valor,
ranking ou atribuição foi alterado. Os três originais foram posteriormente
importados no armazenamento privado, conforme o registro abaixo.

## Importação e conferência das seis ordens restantes

Em 08/09/2026 UTC (noite de 07/09 em Barreiras), a execução
`1f1d7518-05f2-444f-b458-7f7708c52d19`
registrou as três capturas iniciais em três artefatos e dois objetos privados.
As duas consultas vazias conservaram identidades distintas apesar dos bytes
iguais. Reexecução retornou os mesmos IDs; nenhuma linha financeira foi criada.

O lote seguinte consultou somente as seis ordens restantes, a seis requisições
por minuto. Cada uma retornou uma página completa e um par documental compatível:

| OB | SHA-256 da resposta |
| --- | --- |
| 023587 | `cd979d1981d3842a1a5c999a49d5be576731741827f4aa9fe7cf9e42f2b3389c` |
| 037894 | `25f322f545c2a1af29b9721790353af9f268202e21ff3e7f0232252c02ac65b5` |
| 048478 | `173a65a0be454ee51e19b5dafb25a48adee7ee4e7a88925578010b11a9fffad2` |
| 059458 | `ea689b6b19677525d1b7b3a54f3ea6936183a586a1206a9d12bd6e4a3748d1c0` |
| 067803 | `7b8aef8ce8f5296d08c58c72f549eeca1511abf40aeb609336491de4dd6278c1` |
| 078184 | `caebd3f3247e5f3d1ac8c4f5446b286199b74ae365a440297c7e21d73a07fc86` |

Manifesto: `7ab3b21847b2c95b8cdc0b426f367e3e735bc668b1aae7b7f1a788147a653798`.
Pagamentos de origem: mesmo hash informado acima, linhas 4–9. A comparação
conferiu escopo solicitado, território, competência e valor líquido, sem
publicação automática e sem inferir autoria ou execução financeira.

A execução `8097c392-2209-4cb9-9ab4-0f62d5f8f231` importou os seis novos
objetos e seis artefatos privados. Nos dois lotes, o controle da importação
foi aberto antes da autenticação/escrita no Storage. Os registros mantêm os
horários reais de aquisição anteriores à importação. Download posterior
comparou bytes, SHA-256 e tamanho com os originais locais; SQL conferiu URLs,
metadados e ausência de registros financeiros. Replay retornou os mesmos IDs.

Resultado desta ação: nove consultas preservadas, oito conteúdos físicos,
sete pares compatíveis e duas consultas sem linhas. Runs e partições continuam
`partial`, `publication_allowed=false`. Não é cobertura completa do FNS de 2025.
As linhas `fns_payment_observation` originais continuam imutáveis e pendentes:
artefato preservado não é aprovação financeira. A etapa seguinte registrou os
diagnósticos separadamente, como descrito abaixo, mantendo as ausências explícitas.

Validação nesta etapa: 76 testes FNS e 678 testes Node aprovados. Nenhum código
de produção, migration, componente público ou ranking foi modificado.

## Comparações privadas imutáveis

O serviço `FNSComparisonPersistenceService` reutiliza os validadores de
pagamento e ordem, sem gravar observações intermediárias. Confere URLs,
escopo, metadados e bytes restaurados dos dois lados antes da primeira escrita.
Só registra uma comparação se houver pagamento único e evidência válida.
Ausência, conflito e rejeição ficam explícitos; nenhuma dessas situações é
convertida em confirmação de execução financeira ou autoria.

O registro `fns_document_comparison` mantém resultado, chave do documento,
versão do método, hash/página/posição do pagamento e URLs/hashes de todas as
páginas usadas. Não contém campos bancários. A identidade inclui o payload
canônico: o mesmo replay não duplica; evidência alterada gera nova versão.
O artefato vinculado é uma interpretação versionada do pagamento já preservado;
não há novo download da fonte nem alteração das observações anteriores.

A simulação sobre os nove pares reais reproduziu sete compatíveis e dois
`order_not_found`. A execução privada `b9797e77-0b0f-4867-b6f6-4c6b03af33a2`
gravou nove comparações. Todos os originais foram relidos do Storage antes
das escritas. O replay real retornou os mesmos artefatos e inseriu zero linhas;
SQL comparou os nove payloads/hashes com os resultados locais esperados.
Uma conexão posterior confirmou run `partial` e publicação bloqueada.

Não foi adicionada consulta pública ou administrativa para esse novo tipo.
Não selecionar automaticamente uma versão antiga se houver evidência mais
nova ou conflitante. O próximo passo é integrar a consulta privada de estado
à evidência corrente e continuar as outras ações. Não altera valores ou rankings.

Validação da implementação: 83 testes FNS, 678 testes Node e Ruff aprovados.
Sem migration, nova dependência ou mudança visual.
