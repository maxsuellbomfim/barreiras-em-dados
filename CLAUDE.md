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
- LLMs não calculam totais. Publicação exige conferência por código contra o
  documento oficial; a IA confere caso a caso e pode vetar ou retirar, mas
  nunca publica o que o código não validou (ADR 0012, ADR 0099).
- Fato, inferência, anomalia e hipótese devem ser campos/estados distintos.
- A plataforma é autônoma: não depende de revisão humana. Indícios e
  conteúdo reputacional são publicados após revisão automatizada registrada
  (código + agente de IA), com rótulo "Conferido automaticamente — sem
  revisão humana", regra, parâmetro e documento oficial visíveis (ADR 0099).
- Indício, nunca acusação: é proibido afirmar ou insinuar que pessoa ou
  empresa identificada cometeu crime, fraude, corrupção, desvio ou
  superfaturamento. Use "indício", "alerta", "merece apuração".
- Contestação é anônima e dispara reconferência automática; item que não se
  sustenta é retirado por nova versão, sem apagar histórico.
- A amostra de qualidade da extração de atos pode ser conferida por IA
  (ADR 0091): anotação validada por código, métricas calculadas por código
  e rótulo "estimativa automática por IA, não revisão humana".
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
