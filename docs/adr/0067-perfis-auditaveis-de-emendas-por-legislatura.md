# ADR 0067 — Perfis auditáveis de emendas por legislatura

## Status

Aceito em 14 de agosto de 2026.

## Contexto

O ranking por legislatura responde quem aparece com maior valor destinado ou
autorizado para Barreiras, mas um número agregado não permite que cidadãos e
jornalistas confiram quais emendas formam o total. A API federal reconciliada
e o snapshot estadual já possuem registros, estágios e evidências, mas têm
contratos diferentes.

## Decisão

Publicar uma RPC limitada por autoria exata, esfera e legislatura:
`api.get_public_parliamentary_legislature_contributions`.

A RPC:

- aceita no máximo 100 linhas por requisição; a interface usa 25;
- restringe os anos aos exercícios civis completos da legislatura;
- exclui conflitos federais e conserva o status de reconciliação;
- publica execução estadual somente quando a reconciliação autoriza;
- calcula totais com `numeric(20,2)` antes da paginação;
- exige URL HTTPS e hash SHA-256 da evidência principal;
- roda como `security definer` com `search_path` vazio, `PUBLIC` revogado e
  `EXECUTE` concedido somente a `anon` e `authenticated`;
- não expõe CPF nem consulta o domínio privado de identidade.

A página pública mostra cada estágio separadamente. Nulo é explicado como
informação não localizada ou não atribuída com segurança; nunca é formatado
como zero.

## Consequências

O ranking se torna verificável em um clique e passa a sustentar estudos por
legislatura sem transformar o indicador em nota geral de desempenho. A
consulta federal ainda depende da view reconciliada atual; caso o volume cresça
materialmente, deverá receber snapshot indexado sem alterar o contrato público.
