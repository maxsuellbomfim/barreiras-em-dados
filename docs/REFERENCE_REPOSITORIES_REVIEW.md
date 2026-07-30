# Revisão dos repositórios de referência

Os três ZIPs da raiz foram examinados sem incorporação de código. Ideias podem
ser reimplementadas; reutilização literal exige licença compatível, atribuição
e revisão de segurança.

## honestidade-politicos-brasil

### Aproveitar e adaptar

- metodologia e fontes públicas em destaque;
- validação automática de dados no CI;
- processo público de contestação/correção;
- workflows com permissões mínimas e Actions fixadas por SHA;
- documentação de segurança.

### Não adotar

- ranking, nota de honestidade ou adjetivos sobre pessoas;
- perfis manuais sem proveniência por campo;
- inferir integridade pela simples ausência de registros;
- nome de produto que prometa julgamento moral.

O município oferece uma vantagem: é possível cobrir melhor as fontes e o
histórico, em vez de produzir uma comparação nacional superficial.

## Poligrafo

### Aproveitar e adaptar

- cliente isolado por fonte;
- testes unitários e de integração separados;
- documentação de ambiente e segurança;
- fixtures e tratamento explícito de integrações;
- licença MIT, caso algum trecho venha a ser considerado futuramente.

### Não adotar

- enquadramento de “letalidade”, julgamento ou dossiê reputacional;
- ETL pesado em rotas Next.js;
- converter falha de fonte em lista vazia;
- paginação PNCP limitada à primeira página;
- rate limiter em memória como controle global de múltiplas instâncias;
- parâmetros antigos do Querido Diário (`since`/`until`).

O conector novo usa `published_since`/`published_until`, preserva os bytes e
falha de forma distinguível de resultado vazio.

## transparencia-politica-2026

### Aproveitar e adaptar

- foco municipal pelo código IBGE;
- integração conceitual com SICONFI;
- normalização simples como etapa anterior à análise;
- busca e navegação acessíveis ao cidadão.

### Não adotar

- JavaScript sem contratos fortes nas fronteiras;
- escrita direta no Supabase sem camada de proveniência;
- rankings e outliers tratados como conclusões;
- cálculos monetários no frontend;
- logs, dumps, ZIPs aninhados e scripts locais versionados;
- workflows que ocultam falhas com `continue-on-error`.

O ZIP declara ISC no `package.json`, mas não contém arquivo de licença separado.
Não foi copiado código.

## Síntese para Barreiras

A adaptação municipal deve priorizar profundidade:

- cobertura e lacunas por dia/fonte;
- documentos preservados por hash;
- linha do tempo de atos e contratos;
- reconciliação entre Diário, portais, PNCP, SICONFI e TCM-BA;
- correções versionadas;
- páginas de evidência e downloads reproduzíveis.

A pressão pública vem da permanência, legibilidade e verificabilidade dos
fatos — não de uma nota produzida pelo portal.
