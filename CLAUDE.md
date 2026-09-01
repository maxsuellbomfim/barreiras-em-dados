# Instruções do projeto — Barreiras em Dados

## Missão

Construir uma plataforma municipal apartidária, verificável e compreensível.
O código deve preservar a cadeia de custódia dos dados e nunca converter sinais
estatísticos em acusações.

## Ordem obrigatória de trabalho

1. Leia os documentos em `docs/` e os ADRs aplicáveis.
2. Confirme o menor fluxo vertical em andamento.
3. Faça mudanças somente no módulo delegado.
4. Execute testes proporcionais ao risco.
5. Revise segurança, qualidade de dados e documentação.
6. Informe limitações e não inicie uma nova fase grande automaticamente.

## Etapa ativa

Leia primeiro `docs/CURRENT_STATUS.md`. A fase vigente é estabilização do
pré-lançamento e construção incremental do rastro do dinheiro. Diário, atos,
finanças, compras, Legislativo, representação e emendas já possuem projeções
públicas; não trate o projeto como etapa inicial de PNCP.

O próximo trabalho deve fechar um fluxo vertical pequeno: corrigir regressão
observada, tornar cobertura/falha explícita ou ligar dois estágios financeiros
por chave oficial. Não abra uma fase ampla com base apenas no histórico de
`docs/ROADMAP.md`.

## Regras inegociáveis

- Todo registro normalizado deve apontar para ao menos um `raw_record` ou
  `raw_artifact` por meio de `evidence_items`.
- Artefatos brutos são append-only e endereçados por SHA-256.
- Falha de fonte não é “zero resultados”; use estados explícitos de execução.
- Valores monetários usam decimal exato (`numeric` no PostgreSQL), nunca float.
- Cálculos financeiros e regras de anomalia são determinísticos e versionados.
- LLMs não calculam totais e não decidem publicação; publicação automática
  só existe para conteúdo verificado literalmente por código contra o
  documento oficial, com rótulo explícito e reversão auditada (ADR 0012).
- Fato, inferência, anomalia e hipótese devem ser campos/estados distintos.
- Achados de anomalia e conteúdo interpretativo além do registro oficial
  não são publicados sem revisão humana registrada; registros fiéis de
  atos oficiais seguem o ADR 0012 com revisão humana por exceção.
- Não publicar CPF completo, descontos pessoais ou dados sensíveis
  desnecessários.
- Correções criam novas versões; histórico não é alterado ou apagado em
  silêncio.
- Não colocar chaves administrativas em código cliente ou variáveis
  `NEXT_PUBLIC_*`.
- Coletores não vivem em rotas Next.js nem dependem do ciclo de deploy web.

## Limites modulares

- `workers/collectors`: aquisição externa e emissão de registros brutos.
- `workers/document-processing`: OCR, páginas e trechos.
- `workers/normalization`: transformação tipada, sem publicação.
- `workers/reconciliation`: identidades e conflitos entre fontes.
- `workers/anomaly-detection`: regras determinísticas e achados não editoriais.
- `packages/database`: migrations, acesso e transações.
- `packages/data-contracts`: schemas canônicos.
- `packages/evidence`: cadeia de evidências e hashes.
- `apps/admin`: revisão humana; nunca é fonte de fatos.
- `apps/web` e `apps/public-api`: somente dados aprovados.

Agentes com permissão de escrita devem receber um único limite modular por
tarefa. Revisores não devem corrigir silenciosamente o que encontrarem.

## Referências externas na raiz

Os ZIPs são apenas inspiração:

- `honestidade-politicos-brasil-main.zip`;
- `Poligrafo-main.zip`;
- `transparencia-politica-2026-main.zip`.

Não extraia os ZIPs na raiz e não copie código sem registrar licença e
atribuição em `THIRD_PARTY_NOTICES.md`. Prefira reimplementação adequada ao
escopo municipal.
