# API do Portal da Transparência da Prefeitura

- Observada em: 30/07/2026
- Publicador: Prefeitura Municipal de Barreiras
- Catálogo: <https://portaldatransparencia.barreiras.ba.gov.br/dados-abertos/>
- API: `https://portaldatransparencia.barreiras.ba.gov.br/api`

## Situação

Fonte oficial e pública, sem autenticação observada. O catálogo documenta 51
recursos. Não foram localizadas declaração de licença, política de
versionamento, limite de requisições ou garantia de disponibilidade.

O `robots.txt` não bloqueia `/api`, mas isso não representa autorização para
consumo ilimitado. Um futuro coletor deve começar em no máximo 10 requisições
por minuto, com identificação, cache, backoff e contato com o publicador.

## Contrato observado

Exemplo:

```text
GET /api?resource=contratos&limit=50&offset=0
```

Resposta bem-sucedida:

```json
{
  "resource": "contratos",
  "count": 50,
  "data": []
}
```

Regras verificadas:

- `limit` e `offset` paginam;
- `count` é a quantidade retornada na página, não o total disponível;
- encerrar somente quando `count < limit` ou `data` estiver vazio;
- ausência ou nome inválido de `resource` retorna HTTP 200 com raiz `error`;
- sucesso exige validar raiz `resource,count,data`, não apenas o status HTTP;
- resposta usa `application/json; charset=utf-8`;
- `Cache-Control: no-store, no-cache, must-revalidate`;
- não foram observados `ETag`, `Last-Modified`, CORS ou cabeçalhos de rate limit.

## Recursos prioritários

| Recurso | Conteúdo | Filtros documentados | Uso |
|---|---|---|---|
| `contratos` | contratos e aditivos | `numero`, `limit`, `offset` | reconciliar PNCP |
| `processos` | processos licitatórios | `numero`, `limit`, `offset` | reconciliar contratação |
| `licitacoes` | documentos/atos | `titulo`, `limit`, `offset` | preservar PDFs |
| `servidores` | catálogo de folhas em PDF | `ano`, `mes`, `tipo` | descoberta de RH |
| `atos-oficiais` | decretos, portarias e atos | `ano`, `mes`, `tipo` | complementar Diário |
| `rgf` | documentos RGF | `ano` | reconciliar SICONFI |
| `rreo` | documentos RREO | `ano` | reconciliar SICONFI |
| `pdc-obras-em-andamento` | documentos de obras | não confirmado | futuro painel de obras |

`servidores` não é uma API de linhas de folha: é um catálogo de PDFs. Nenhuma
linha individual deve ser inferida antes de baixar, preservar, classificar e
revisar o documento.

## Tipos e divergências

Nos recursos `contratos` e `processos`, identificadores, datas e valores
monetários foram observados como strings JSON, com campos opcionais `null`.
Conversão deve ser explícita, com valor original preservado.

A documentação de exemplo usa alguns nomes prefixados, como
`contratos_contratoNumero`, enquanto a resposta real observada usa
`contratoNumero`. Portanto:

- fixture real sanitizada é o contrato operacional;
- mudança de campo deve falhar de modo explícito;
- campos novos devem ser preservados;
- não renomear ou preencher silenciosamente valores ausentes.

## Documentos

Em amostra pequena, URLs de `contratos`, `licitacoes`, `servidores`,
`atos-oficiais` e obras apontaram para PDFs HTTPS em
`barreiras.mtransparente.com.br`.

O host do fornecedor deve ter allowlist separada. Redirect, tipo MIME, tamanho,
hash e conteúdo real devem ser verificados; extensão `.pdf` não basta.

## Recursos catalogados

O snapshot sanitizado completo está em
`fixtures/sources/prefeitura-transparencia/catalog-observation.json`.

## Pendências antes do conector

O cliente paginado inicial foi implementado em
`workers/collectors/src/barreiras_collectors/connectors/municipal_transparency.py`
para preservar o recurso `pdc-resumo-execucao-da-receita`. Ele valida a raiz
`resource,count,data`, trata erro HTTP 200 com `error`, usa limite conservador,
retries e circuit breaker e ainda não normaliza valores monetários.

Esse cliente não publica totais nem grava `finance.revenues` sozinho: a próxima
etapa precisa observar uma resposta real, confirmar nomes/unidades de campos e
criar a persistência raw-first antes de qualquer cálculo.

1. confirmar contato técnico, termos e limite aceitável;
2. medir cobertura temporal e duplicação por recurso;
3. definir chave estável por recurso;
4. congelar fixtures reais sem dados pessoais desnecessários;
5. testar alterações durante paginação;
6. mapear CPF/CNPJ em `documento` e mascarar pessoa natural;
7. testar PDFs hostis antes de qualquer parsing;
8. reconciliar, sem eleger fonte vencedora global, com PNCP/SICONFI/Diário.
