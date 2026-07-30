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

A etapa ativa é **1A — coleta preservada do Diário**. A persistência de páginas
JSON está implementada localmente, mas o gate remoto continua aberto. Antes de
PDF, parser de atos ou PNCP, aplique migrations em Supabase descartável, use
login membro de `collector_worker`, restrinja Storage, execute uma janela de um
dia, repita-a e restaure o objeto pelo SHA-256.

## Regras inegociáveis

- Todo registro normalizado deve apontar para ao menos um `raw_record` ou
  `raw_artifact` por meio de `evidence_items`.
- Artefatos brutos são append-only e endereçados por SHA-256.
- Falha de fonte não é “zero resultados”; use estados explícitos de execução.
- Valores monetários usam decimal exato (`numeric` no PostgreSQL), nunca float.
- Cálculos financeiros e regras de anomalia são determinísticos e versionados.
- LLMs não calculam totais e não publicam conteúdo automaticamente.
- Fato, inferência, anomalia e hipótese devem ser campos/estados distintos.
- Nenhum achado reputacional é publicado sem revisão humana registrada.
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
