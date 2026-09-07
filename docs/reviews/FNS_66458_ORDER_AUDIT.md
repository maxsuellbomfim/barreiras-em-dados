# FNS — três ordens da ação 66458

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
ranking ou atribuição foi alterado. Este lote permanece apenas em custódia
local: a importação privada no Supabase e as demais ordens continuam pendentes.
