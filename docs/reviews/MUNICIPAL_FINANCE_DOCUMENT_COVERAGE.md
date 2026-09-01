# Cobertura dos documentos financeiros municipais

## Consulta auditada

Em 01/09/2026, a projeção pública `api.get_public_finance_documents` foi
consultada separadamente para as famílias mensais. A consulta retornou:

| Família oficial | Registros | PDF preservado | Somente catálogo | Competências com versões |
| --- | ---: | ---: | ---: | ---: |
| Balancetes | 119 | 119 | 0 | 6 no acervo completo; 5 desde 2021 |
| Execução da receita | 56 | 56 | 0 | 2 |
| Execução da despesa | 55 | 54 | 1 | 0 |

Os registros de balancete anteriores a 2021 permanecem preservados, mas o
calendário público começa em 2021, conforme o recorte histórico do portal.

O único registro mensal somente catalogado é o **Demonstrativo Analítico de
Despesa — abril de 2023** (`document_id`
`9d3b403d-ebab-4385-9846-92b1c08a57ec`). A API oficial informa a competência,
o título e a descrição, porém a URL de documento publicada redireciona para o
login administrativo e não devolve um PDF. A execução direcionada
`33542347455` comprovou a falha como `SourceContractError`; por isso o mês
permanece `needs_data` e nenhum valor foi inferido da descrição do catálogo.

## Regra pública

- cada célula representa uma família e uma competência, nunca um valor;
- duas versões para a mesma competência não são somadas nem descartadas;
- a célula abre a versão preservada mais recente e informa quantas versões
  foram observadas;
- documento catalogado e PDF preservado são estados distintos;
- após trinta dias do fim da competência, uma lacuna recebe o texto
  “Não localizado no catálogo preservado consultado”;
- essa lacuna não significa valor zero, inexistência definitiva ou prova de
  omissão da Prefeitura;
- se uma das três consultas falhar, a matriz inteira fica indisponível e não
  classifica ausências com dados parciais.

## Limite

Este calendário comprova presença documental. Ele não extrai, soma ou compara
valores de receita, despesa ou balancete. A publicação de números continua
dependendo de extração determinística, reconciliação da competência e vínculo
com o PDF preservado.

## Recuperação direcionada

O workflow `collect-finance-documents.yml` aceita uma
`finance_reference_month` no formato `AAAA-MM` junto de um recurso financeiro
documental. Nesse modo, o coletor seleciona somente a competência solicitada e
exige que todos os documentos correspondentes sejam preservados. Ausência no
catálogo, HTML no lugar do PDF, limite parcial ou falha de download terminam o
workflow com erro explícito; não há selo verde sem evidência.

Como segunda fonte oficial, o inventário privado do TCM-BA foi consultado pelo
hash do único demonstrativo analítico de despesa já classificado. A linhagem
comprovou que esse PDF pertence a **janeiro de 2021** (`PCMGE015`), não a abril
de 2023. O coletor TCM-BA agora aceita seleção dirigida por competência e código
oficial de categoria. A recuperação de abril deve usar `04/2023` + `PCMGE015`;
o arquivo somente poderá apoiar uma reconciliação depois de preservação, hash,
texto e equivalência metodológica, sem substituir silenciosamente a fonte
municipal quebrada.
