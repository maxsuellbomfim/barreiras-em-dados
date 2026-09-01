# Barreiras 360

Fundação do Barreiras 360, uma plataforma cívica municipal, apartidária e orientada a
evidências para tornar dados públicos da Prefeitura e da Câmara Municipal de
Barreiras (BA) mais verificáveis e compreensíveis.

Portal de pré-lançamento:
[barreiras-em-dados.vercel.app](https://barreiras-em-dados.vercel.app)

## Documentação essencial

- [Estado atual e gates](docs/CURRENT_STATUS.md)
- [Visão do produto](docs/PRODUCT_VISION.md)
- [Arquitetura](docs/ARCHITECTURE.md)
- [Fontes de dados](docs/DATA_SOURCES.md)
- [Perfis públicos documentados](docs/POLITICAL_PROFILES.md)
- [Matriz de ETLs e fontes](docs/ETL_SOURCE_MATRIX.md)
- [Inventários técnicos das fontes](docs/sources/README.md)
- [Estratégia de funcionalidades](docs/FEATURE_STRATEGY.md)
- [Sistema de design](docs/DESIGN_SYSTEM.md)
- [Portal público de pré-lançamento](docs/PUBLIC_PORTAL.md)
- [Operação do coletor diário](docs/COLLECTOR_OPERATIONS.md)
- [Guia de configuração](docs/SETUP_GUIDE.md)
- [Estratégia de ferramentas](docs/TOOLING_STRATEGY.md)
- [Portões de conformidade](docs/COMPLIANCE_GATES.md)
- [Revisão das referências](docs/REFERENCE_REPOSITORIES_REVIEW.md)
- [Revisão da etapa 0](docs/reviews/STAGE_0_REVIEW.md)
- [Revisão da persistência 1A](docs/reviews/STAGE_1A_PERSISTENCE_REVIEW.md)
- [Plano de desenvolvimento](docs/DEVELOPMENT_PLAN.md)

## Estado atual

O portal está em **pré-lançamento, estabilização e construção do rastro do
dinheiro**. Já existem projeções públicas do Diário, atos, finanças, compras,
Legislativo, representação e emendas. Cobertura histórica, qualidade da fonte
e limitações continuam explícitas: dado não localizado nunca é convertido em
zero, nem anomalia em acusação.

Consulte [`docs/CURRENT_STATUS.md`](docs/CURRENT_STATUS.md) antes de iniciar uma
mudança. Esse documento concentra o estágio vigente, as limitações e o próximo
fluxo vertical; `docs/ROADMAP.md` preserva o histórico detalhado.

### Portal web local

```powershell
pnpm.cmd install
pnpm.cmd --filter @barreiras-em-dados/web dev
```

O build de produção é validado com:

```powershell
pnpm.cmd --filter @barreiras-em-dados/web typecheck
pnpm.cmd --filter @barreiras-em-dados/web build
pnpm.cmd audit --prod
```

## Comece por aqui

1. Leia `docs/PRODUCT_VISION.md`.
2. Leia `docs/CURRENT_STATUS.md`.
3. Leia apenas a parte de `docs/ARCHITECTURE.md` e o ADR aplicável ao domínio.
4. Agentes de código seguem `AGENTS.md`; o Claude Code também lê `CLAUDE.md`.

Os três arquivos ZIP na raiz são referências externas e não fazem parte do
produto. Nenhum deles deve ser extraído ou incorporado sem revisão de licença,
segurança e adequação editorial.
