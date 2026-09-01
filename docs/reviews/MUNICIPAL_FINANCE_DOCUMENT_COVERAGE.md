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
