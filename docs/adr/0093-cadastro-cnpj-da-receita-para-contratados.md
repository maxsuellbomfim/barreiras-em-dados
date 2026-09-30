# ADR 0093 — Cadastro CNPJ da Receita para contratados

## Status

Aceita em 30/09/2026 pelo titular ("se atente nos contratos ... nome fantasia
ou razão social ... ou consórcio; encontre a melhor forma de verificar").

## Contexto

O mesmo fornecedor aparece com nomes diferentes: o empenho da Prefeitura traz
a razão social ("GSV MAIS ALIMENTOS LTDA"), o portal de contratos às vezes o
nome fantasia ("COMERCIAL VALOIS"), e empresário individual tem como razão
social o nome do titular. A regra de ligação empenho → contrato deixava essas
citações pendentes como "favorecido divergente" (4.202 em 30/09). A fonte que
resolve a identidade é o cadastro oficial do CNPJ.

## Decisão

1. Fonte: dados abertos do CNPJ publicados pela Receita Federal no
   compartilhamento público do próprio domínio
   (`arquivos.receitafederal.gov.br`, WebDAV), pasta mensal mais recente
   completa. Nenhum espelho de terceiros é usado como fonte.
2. Escopo: só os CNPJs de contratos do portal municipal e de contratos e
   resultados do PNCP (`finance.get_cnpj_registry_targets`).
3. Custódia: a base inteira (~7 GB) não é guardada. Cada ZIP é baixado, tem o
   SHA-256 calculado no download e o tamanho conferido com o anunciado, é lido
   em fluxo e apagado. Fica preservado um extrato JSON com os hashes, URLs e
   datas de todos os ZIPs de origem, as linhas dos CNPJs pedidos e a lista dos
   não encontrados. Qualquer pessoa pode baixar o mesmo mês e conferir.
4. Minimização: só razão social, nome fantasia, natureza jurídica, porte,
   situação cadastral, matriz/filial, UF e município. Telefone, e-mail,
   endereço e sócios não são coletados.
5. O cadastro alimenta regras de identidade (ADR seguinte) e não é publicado
   por si só nesta etapa.

## Consequências

- Nome fantasia, razão social, empresário individual (natureza 2135) e
  consórcio (2151, 2283) passam a ser distinguíveis por dado oficial.
- Coleta mensal e pesada (~1 h de download); falha de listagem ou de download
  é falha explícita da execução, nunca "CNPJ inexistente".
- O token do compartilhamento é público; se a Receita trocar o link, a coleta
  falha de forma visível e o endereço é atualizado no conector.
