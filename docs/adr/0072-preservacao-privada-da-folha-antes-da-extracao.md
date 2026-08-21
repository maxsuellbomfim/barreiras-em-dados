# ADR 0072 — Preservação privada da folha antes da extração

- Estado: aceita
- Data: 2026-08-21

## Contexto

O recurso oficial `servidores` da Prefeitura não entrega linhas salariais em
JSON. Ele publica um catálogo de PDFs que, na observação de 21/08/2026, contém
200 documentos de 2018 a 2026 e mistura relações de servidores, estagiários e
terceirizados. Esses arquivos podem conter dados pessoais e leiautes diferentes
por competência.

Sem preservar o documento exato, não é possível calcular com segurança quantos
vínculos existem, o custo mensal da folha ou a divisão entre efetivos e
comissionados. Publicar integralmente o PDF como uma tabela também exporia
campos desnecessários e trataria formatos distintos como se fossem equivalentes.

## Decisão

O recurso `servidores` entra na fila financeira já serializada, porque usa a
mesma credencial técnica e o mesmo orçamento limitado de conexões. Cada
execução:

1. preserva o catálogo completo como evidência bruta;
2. revisita o catálogo desde o início e ignora documentos cujo par
   `source_record_key + source_url` já tenha artefato filho idêntico;
3. baixa no máximo cinco PDFs ainda ausentes;
4. respeita um orçamento agregado suave de 64 MiB por execução; depois de ao
   menos um PDF preservado, o próximo arquivo que ultrapassaria o teto e os
   seguintes ficam adiados. Um primeiro PDF maior que 64 MiB ainda avança para
   não bloquear permanentemente a fila;
5. mantém catálogo, PDF, URL, data de coleta, hash e versão do coletor no
   armazenamento bruto privado;
6. não cria linha pública de folha, pessoa ou componente salarial.

O limite de cinco documentos não avança para sempre sobre os demais: como o
catálogo inteiro cabe em uma página de 500 registros, a partição documental
retorna ao início e drena os próximos ausentes de forma idempotente.
O teto agregado controla a velocidade de crescimento do Storage, mas não é uma
política de descarte: a execução fica `partial`, registra bytes processados e
retoma os documentos adiados em outro lote.

## Gate para a próxima etapa

Antes de publicar qualquer número, uma amostra por tipo e ano deverá confirmar:

- competência, unidade monetária e significado de cada coluna;
- regra determinística para tipo de vínculo, órgão e remuneração bruta;
- distinção entre servidor, estagiário e terceirizado;
- retificações, duplicidades e totalizadores do próprio documento;
- exclusão de CPF, matrícula desnecessária, conta bancária, descontos pessoais
  e demais campos sem finalidade pública proporcional.

A primeira projeção será agregada por competência, órgão e tipo de vínculo.
Valores individuais ou componentes só poderão avançar por ADR posterior e
testes específicos de minimização.

## Consequências

- o acervo deixa de depender da permanência dos links do fornecedor;
- uma sequência de PDFs grandes não consome espaço sem limite numa única
  execução;
- a automação progride sem publicar dados pessoais por acidente;
- os números populares de pessoal permanecem indisponíveis até a classificação
  determinística dos leiautes;
- falha em um PDF deixa a partição parcial e retomável, sem transformar ausência
  de coleta em ausência de servidores.
