# ADR 0035 — Paginação do vínculo territorial eleitoral

## Contexto

O coletor preserva o resultado nominal agregado por candidatura, turno e eleição
para o município de Barreiras. O primeiro endpoint público limitava a resposta a
500 linhas. Depois da carga de 2022, esse limite passou a ocultar parte do
histórico: havia 1.818 registros válidos preservados no acervo bruto.

## Decisão

Manter a função pública legada para compatibilidade e adicionar
`api.get_tse_barreiras_votes_page`, com `page_size`, `page_offset`, ano e cargo
opcionais. O portal percorre as páginas determinísticamente até receber uma
resposta menor que o tamanho da página. Um limite de segurança de 20 páginas
retorna indisponibilidade explícita, nunca uma lista silenciosamente incompleta.

## Consequências

- O histórico de 2022 e 2024 pode ser exibido sem truncamento silencioso.
- Filtros por ano e cargo ficam disponíveis para próximas telas e APIs.
- A associação de uma candidatura a um perfil político continua baseada em
  identificadores oficiais; nenhum casamento por nome ou IA é introduzido.
- A página pode ficar pesada se o acervo crescer muito; a próxima evolução deve
  ser paginação visual ou filtros no cliente, sem remover a preservação integral.
