# Revisão da persistência integral do Diário Oficial

Data da revisão: 8 de agosto de 2026.

## Resultado desta etapa

Esta etapa cria a base de dados e o comando de processamento necessários para
preservar e publicar o texto literal de cada edição do Diário Oficial. Ela não
substitui o texto oficial por resumos e não usa IA para decidir onde um
documento começa ou termina.

O conteúdo extraído é persistido em blocos imutáveis, ligados ao artefato bruto
e ao seu hash SHA-256. Cada versão editorial mantém a sequência exata dos
blocos usados. O banco rejeita versões com texto alterado, bloco de outra
edição, lacuna, inversão de ordem ou intervalo incompatível.

## Decisão conservadora de publicação

Na granularidade disponível hoje, cada página é um bloco. Isso ainda não prova
com segurança as fronteiras internas entre portarias, decretos, editais e
outros documentos que possam começar ou terminar na mesma página.

Por isso, a primeira versão publicável é sempre uma `edition_fallback`: a edição
inteira, em ordem, sem cortes. O segmentador pode registrar quantas divisões
propôs para diagnóstico, mas essas propostas não são publicadas até que uma
etapa futura consiga comprovar as fronteiras pelo layout e pelo texto oficial.

Essa limitação é intencional. É preferível apresentar o texto integral de uma
edição a atribuir a um documento um trecho truncado ou pertencente ao ato
seguinte.

## Fontes, datas e precedência

- Edições coletadas diretamente da Prefeitura têm precedência sobre cópias do
  Querido Diário na projeção pública.
- Quando o PDF direto não contém a data nos metadados do artefato, o repositório
  pode completá-la com o registro do catálogo oficial da mesma edição e ano.
- Ano e número da edição fazem parte da ordenação; edições de anos diferentes
  não são misturadas.
- Toda versão mantém relação com o artefato bruto, as páginas e os hashes do
  conteúdo usado.

## Segurança e governança

- As novas tabelas internas não são legíveis por `anon` ou `authenticated`.
- A API pública acessa somente uma função de projeção com privilégios mínimos.
- Blocos e versões são append-only: não podem ser alterados ou apagados
  silenciosamente.
- Uma versão retirada não faz uma versão pública antiga reaparecer.
- O RPC público prefere a fonte direta e retorna apenas lotes validados ou o
  fallback integral conservador.
- Falhas de processamento são registradas com mensagem sanitizada.

## Verificações executadas

- 416 testes Python: aprovados, com uma exclusão prevista.
- 68 testes Node: aprovados.
- Testes PGlite da migration e das restrições de integridade: aprovados.
- Catálogos de fontes e contratos JSON Schema: aprovados.
- Ruff e verificação de formatação Python: aprovados.
- Typecheck e build de `apps/web` e `apps/admin`: aprovados.
- Verificação de whitespace do Git e busca de segredos nos arquivos alterados:
  aprovadas.

O aviso local de Node 24 não impediu os testes; o repositório e o CI declaram
Node 22 como versão suportada.

## Limitações e próxima menor etapa vertical

Este PR ainda não altera a interface pública nem agenda o novo comando no
workflow. Após aplicar a migration, a próxima etapa deve:

1. expor o contrato tipado da projeção pública no portal;
2. mostrar a edição integral com navegação por página e busca no texto;
3. incluir o comando no workflow do Diário com checkpoint e backfill;
4. só depois implementar segmentação interna baseada em blocos de layout,
   sempre submetida à validação literal antes da publicação.
