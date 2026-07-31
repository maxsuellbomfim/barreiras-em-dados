# Portal público de pré-lançamento

Produção: [https://barreiras-em-dados.vercel.app](https://barreiras-em-dados.vercel.app)

Estado verificado em 31/07/2026:

- projeto Vercel isolado `barreiras-em-dados`;
- ambiente `production`;
- deployment estável `dpl_AGkA5AY7AEqYRqn6RQAKVSUwYxS7`;
- página inicial e `/api/health` respondendo HTTP 200;
- coleta diária do Querido Diário ativa no GitHub Actions;
- projeção pública agregada criada no Supabase;
- novo painel de coleta pronto para publicação após configurar duas variáveis
  públicas na Vercel.

## Objetivo desta versão

O portal torna a construção observável sem antecipar a publicação de registros
municipais ainda não revisados. Ele apresenta:

- propósito e limites editoriais;
- cadeia de evidências em linguagem comum;
- links diretos para fontes oficiais;
- ordem das primeiras áreas de dados;
- estado técnico verificável da coleta do Querido Diário.

Esta versão **não é o lançamento da base cívica** definido no roadmap. Nenhuma
nomeação, exoneração, despesa, contratação, pessoa ou fornecedor aparece antes
do fluxo de coleta, extração, validação, revisão humana e aprovação.

## Indicadores exibidos

A seção **A coleta já começou** consulta uma projeção pública somente leitura e
mostra:

- quantidade distinta de edições preservadas;
- intervalo de datas efetivamente coberto;
- quantidade distinta de respostas brutas preservadas;
- horário da última coleta bem-sucedida;
- link para a fonte oficial agregadora.

Os números descrevem somente o acervo técnico. Eles não medem desempenho,
regularidade ou qualidade da gestão municipal. Replays idempotentes não aumentam
as contagens. Falha de consulta é apresentada como indisponibilidade, nunca como
zero dados.

## Fluxo da consulta pública

1. o servidor Next.js chama
   `api.get_querido_diario_collection_status()` pela Data API;
2. o PostgREST expõe o schema dedicado `api`;
3. a função retorna apenas agregados não reputacionais;
4. a resposta é validada por tipo, formato e versão metodológica;
5. a página usa cache revalidado a cada cinco minutos;
6. erro, timeout ou resposta inesperada produzem um estado seguro de
   indisponibilidade.

O navegador não recebe acesso direto às tabelas internas. As variáveis
`PUBLIC_DATA_SUPABASE_URL` e `PUBLIC_DATA_SUPABASE_PUBLISHABLE_KEY` são lidas
somente no servidor web. A chave publicável não concede acesso por si só; os
grants do banco continuam sendo o controle efetivo.

## Segurança e privacidade

- `anon` pode executar apenas a função agregada;
- `anon` não pode consultar `raw.raw_records` nem `raw.raw_artifacts`;
- nenhuma service role, secret key ou senha é usada pelo portal;
- a função é `SECURITY DEFINER`, tem `search_path` vazio e referências
  qualificadas;
- nenhuma informação pessoal ou conteúdo reputacional é retornado;
- HSTS, `nosniff`, proteção contra iframe, política de referência e bloqueio de
  câmera, microfone e geolocalização permanecem ativos;
- não há cookies, login, analytics ou formulários.

Uma CSP com nonce continua pendente e será obrigatória antes de scripts
externos, autenticação ou conteúdo gerado pelo usuário.

## Qualidade dos dados

Uma revisão visual encontrou texto UTF-8 corrompido no catálogo de três fontes.
A correção foi aplicada por migration append-only e gerou eventos de auditoria
com estado anterior, estado novo e motivo. Nenhum histórico foi apagado.

O painel diferencia explicitamente:

- coleta preservada;
- cobertura da amostra-piloto;
- atos ainda não extraídos;
- registros ainda não revisados ou publicados.

## Verificação

Foram verificados:

- build de produção e TypeScript estrito;
- resposta real da função pela chave publicável;
- negação de leitura anônima das tabelas brutas;
- migration fundamental e teste de autorização negativo;
- renderização desktop em 1440 px;
- renderização móvel em 390 px, sem overflow horizontal;
- comportamento de indisponibilidade sem mostrar contagens falsas;
- `prefers-reduced-motion`, `prefers-reduced-transparency` e
  `prefers-contrast`;
- ausência de segredos e vulnerabilidades conhecidas nas dependências de
  produção.

## Limitações e próxima menor evolução

- a cobertura atual é uma amostra pequena, não o histórico completo;
- PDFs e textos das edições ainda precisam ser preservados como artefatos
  filhos;
- nomeações e exonerações ainda não foram extraídas nem revisadas;
- o plano gratuito do Supabase não oferece proteção contra senhas vazadas;
- backup e exercício integrado de DLQ/circuit breaker continuam pendentes.

Depois da publicação do painel, a próxima menor etapa vertical será baixar e
preservar PDF/texto de uma edição, produzir candidatos determinísticos de
nomeação/exoneração e encaminhá-los à revisão humana sem publicação automática.
