# ADR 0061 — Preservar emendas estaduais antes do recorte territorial

- Estado: aceito
- Data: 13/08/2026

## Contexto

O Portal de Dados Abertos da Bahia publica diariamente o conjunto Emendas
Parlamentares Estaduais em um ZIP com cinco CSVs. A inspeção do recurso oficial
confirmou informações financeiras e administrativas, mas nenhum dos cabeçalhos
publica município de destino ou código IBGE. Atribuir uma emenda a Barreiras por
busca de palavras no objeto ou no beneficiário produziria falsos positivos e
totais sem sustentação determinística.

## Decisão

Preservar separadamente o JSON do catálogo CKAN e o ZIP bruto em armazenamento
privado e imutável. O coletor valida nomes exatos dos cinco membros, cabeçalhos,
codificação UTF-8, tamanhos, quantidade de linhas e SHA-256 antes de considerar
a partição completa. Somente manifestos técnicos são gravados como registros
brutos; valores e autores não são normalizados nem publicados nesta etapa.

O checkpoint registra `territorial_scope=not_available_in_archive`. A fonte e
o prefixo de armazenamento estaduais permanecem separados da trilha federal.
Não existe concessão de leitura anônima sobre os artefatos.

## Consequências

- o Barreiras 360 mantém histórico verificável do conjunto estadual desde a
  primeira coleta;
- mudanças silenciosas no schema interrompem a coleta e ficam observáveis;
- CSV preservado com sintaxe defeituosa permanece auditável, mas recebe
  cobertura parcial e contagem indisponível em vez de um número inventado;
- ausência de chave territorial não é convertida em zero nem em ausência de
  atuação parlamentar;
- nenhuma emenda entra em ranking ou total de Barreiras nesta fase;
- a etapa seguinte deve localizar no Transparência Bahia/FIPLAN uma chave ou
  relação oficial entre emenda, execução e município beneficiado.
