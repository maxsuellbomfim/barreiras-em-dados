# Barreiras em Dados

Fundação de uma plataforma cívica municipal, apartidária e orientada a
evidências para tornar dados públicos da Prefeitura e da Câmara Municipal de
Barreiras (BA) mais verificáveis e compreensíveis.

Portal de pré-lançamento:
[barreiras-em-dados.vercel.app](https://barreiras-em-dados.vercel.app)

## Documentação essencial

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

Este repositório está na etapa 1A. O escopo ativo é:

- documentação de produto, arquitetura, governança, segurança e política
  editorial;
- contratos de dados independentes de linguagem;
- migrations fundamentais do PostgreSQL;
- conector e persistência idempotente do Querido Diário;
- coleta diária automatizada fora da Vercel, com credenciais de privilégio
  mínimo e replay manual;
- acervo local append-only por SHA-256, sem dependência de nuvem;
- portal público Next.js de pré-lançamento, sem dados cívicos não revisados;
- status público agregado da coleta, sem expor tabelas brutas;
- fixtures e testes do conector.

Não existe ainda conteúdo público de caráter reputacional, detecção de
irregularidade ou integração PNCP. O portal publicado apresenta apenas fontes,
metodologia e o estado técnico real da construção.

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
2. Leia `docs/ARCHITECTURE.md` e os ADRs em `docs/adr/`.
3. Siga `docs/DEVELOPMENT_PLAN.md` para a ordem de implementação.
4. No Claude Code, leia `CLAUDE.md` antes de delegar módulos.

Os três arquivos ZIP na raiz são referências externas e não fazem parte do
produto. Nenhum deles deve ser extraído ou incorporado sem revisão de licença,
segurança e adequação editorial.
