# Portal público de pré-lançamento

Produção: [https://barreiras-em-dados.vercel.app](https://barreiras-em-dados.vercel.app)

Estado em 30/07/2026:

- projeto Vercel `barreiras-em-dados`;
- ambiente `production`;
- framework detectado: Next.js;
- deployment aprovado: `dpl_6U24rq87y9Kp48K7iSPt1qP4L41U`;
- estado `READY`, sem erro de alias;
- página inicial e `/api/health` respondendo HTTP 200;
- nenhum erro de runtime encontrado após a publicação.

Uma primeira tentativa de pacote foi reprovada pelo teste pós-deploy porque a
raiz respondia 404, apesar do health check saudável. Ela não permaneceu no alias
de produção: um segundo pacote, limitado aos dez arquivos-fonte do aplicativo,
foi compilado, verificado e promovido automaticamente pelo novo deploy.

Um preview automático posterior foi bloqueado antes do build porque a identidade
global do Git apontava para outra conta GitHub. A produção não foi afetada. A
identidade foi alinhada, apenas neste repositório, com `maxsuellbomfim`, o Node
foi fixado em `22.x` e o `vercel.json` da raiz passou a declarar explicitamente
o build e a saída do `apps/web`. As mesmas versões de Next e React também estão
nas `devDependencies` da raiz exclusivamente para a detecção inicial da Vercel;
o aplicativo e seu código permanecem em `apps/web`.

## Objetivo desta versão

O primeiro site público existe para tornar a construção observável sem antecipar
a publicação dos registros municipais. Ele apresenta:

- propósito e limites editoriais;
- cadeia de evidências em linguagem comum;
- links diretos para fontes oficiais;
- ordem das primeiras áreas de dados;
- estado técnico verificável da infraestrutura.

Esta versão **não é o lançamento da base cívica** definido no roadmap. Nenhuma
nomeação, exoneração, despesa, contratação, pessoa ou fornecedor aparece antes
do fluxo de coleta, extração, revisão humana e publicação estar completo.

## Indicadores exibidos

Os números da página inicial descrevem somente a infraestrutura:

- 79 recursos oficiais catalogados nas APIs da Prefeitura e da Câmara;
- 40 tabelas internas da fundação de dados;
- um artefato remoto legítimo com SHA-256 verificado.

A interface declara expressamente que esses números não são indicadores da
gestão municipal. Eles devem ser atualizados por código ou por mudança revisada
enquanto não houver uma projeção pública automatizada.

## Implementação

- Next.js App Router e TypeScript estrito;
- renderização estática da página inicial;
- CSS responsivo com fontes do sistema, sem rastreamento ou fontes externas;
- metadata social, ícone e `robots.txt`;
- health check estático em `/api/health`;
- Vercel somente para o aplicativo web;
- sem conexão do navegador ao PostgreSQL ou ao Storage nesta etapa;
- sem variáveis de ambiente, cookies, login, analytics ou formulários.

O desenho segue os princípios Apple já escolhidos para o projeto: hierarquia
tipográfica, materiais translúcidos com alternativa sólida, feedback imediato e
movimento reduzido. A linguagem e o contraste permanecem orientados a um portal
cívico, não a uma peça promocional.

## Segurança

Controles ativos:

- HSTS;
- `X-Content-Type-Options: nosniff`;
- `X-Frame-Options: DENY`;
- `Referrer-Policy: strict-origin-when-cross-origin`;
- `Permissions-Policy` bloqueando câmera, microfone e geolocalização;
- `poweredByHeader` desativado;
- versões de produção fixadas no lockfile;
- auditoria de dependências sem vulnerabilidade conhecida no momento do deploy;
- overrides temporários para `sharp 0.35.0` e `postcss 8.5.18`, porque as
  versões transitivas do Next apresentavam advisories conhecidos.

Uma CSP com nonce continua pendente. A página atual não aceita entrada, não
executa conteúdo de terceiros e não possui scripts de analytics; a CSP deve ser
implementada antes de adicionar scripts externos, autenticação ou conteúdo
gerado pelo usuário.

## Verificação

Antes da primeira publicação foram verificados:

- build de produção e tipagem;
- carregamento HTTP 200;
- ausência de erro no console e de overlay do Next;
- renderização desktop em 1440 px;
- renderização móvel em 390 px, sem overflow horizontal;
- health check HTTP 200;
- presença dos cabeçalhos de segurança;
- links externos com `rel="noreferrer"`;
- comportamento para `prefers-reduced-motion`,
  `prefers-reduced-transparency` e `prefers-contrast`.

O navegador automatizado local confirmou o layout completo sem erros em desktop
e mobile. A verificação remota usou a própria integração autenticada da Vercel,
pois o Chrome automatizado do ambiente local bloqueia navegação externa; ela
confirmou HTML completo, metadata, cabeçalhos, health e ausência de erro de
runtime.

## Próxima menor evolução

1. ligar o status de fontes a uma projeção pública somente leitura;
2. adicionar página pública de metodologia e changelog;
3. criar canal de correção/contato com minimização de dados;
4. publicar a linha do tempo apenas depois do gate editorial da etapa 1C;
5. adicionar domínio próprio, monitoramento e CSP com nonce.
