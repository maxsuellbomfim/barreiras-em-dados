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

A etapa ativa é **1A — coleta preservada do Diário**. Páginas JSON podem ser
preservadas em modo local append-only e o replay de uma janela real já foi
validado. Um projeto Supabase isolado chamado `Barreiras em Dados` está ativo em
São Paulo. Cinco migrations, o seed e o bucket privado `raw-artifacts` já foram
aplicados; o advisor não aponta falha de RLS ou exposição de dados, mas registra
proteção contra senhas vazadas desativada no Auth. Todas as chaves estrangeiras
estão indexadas. A role `collector_querido_diario` possui LOGIN, limite de duas
conexões e continua sem privilégios administrativos. O UUID Auth
`d3e7a733-6101-4c9e-8d7a-d0f88a243eee` está ativo exclusivamente no bucket
`raw-artifacts`, prefixo `querido-diario/gazettes/`, para `SELECT` e `INSERT`.
O cliente `psql 17.10` está instalado sem servidor ou serviço local. A senha
PostgreSQL foi criada por prompt interativo, sem exposição. O login real da role
foi aprovado com TLS `verify-full`: uma inserção autorizada foi exercitada dentro
de transação, `DELETE`/`UPDATE` no bruto foram negados e o rollback deixou zero
registros temporários. A identidade Auth real também foi aprovada com chave
publicável: criou e restaurou uma página legítima do Querido Diário, confirmou
seu SHA-256 e foi impedida de sobrescrever, apagar ou sair do prefixo autorizado.
Há exatamente um objeto de 861 bytes no bucket e nenhum fora do prefixo. O
próximo gate é executar uma coleta remota de um dia, vincular esse objeto ao
PostgreSQL e repetir o replay sem duplicação, sem compartilhar senhas.

Somente depois desse gate, baixe PDF/TXT como artefatos filhos. Parser de atos e
PNCP continuam fora de escopo. O projeto `Site Kelvin Vinicius` foi pausado, não
apagado, para liberar a cota; não o reutilize nem altere os demais projetos.

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
