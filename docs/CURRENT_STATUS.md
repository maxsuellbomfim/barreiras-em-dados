# Estado atual do Barreiras 360

Atualizado em **23/09/2026**. Este é o ponto de entrada operacional: um resumo
curto do que está no ar, do que está frágil e do próximo fluxo. O registro
detalhado de cada entrega de agosto e setembro, com evidências e hashes, está em
[`reviews/STATUS_LOG_2026_08_09.md`](reviews/STATUS_LOG_2026_08_09.md);
decisões ficam em `docs/adr/` e o histórico amplo em `docs/ROADMAP.md`.

## Fase atual

**Estabilização do pré-lançamento e construção incremental do rastro do
dinheiro.** O portal está marcado como pré-lançamento até os gates abaixo serem
comprovados. O trabalho deve fechar fluxos verticais pequenos, não abrir fases
amplas.

## Estado em 23/09/2026

- **Dados em dia:** Diário até a edição 4741 (22/09), PNCP e portal municipal
  coletados em 22 e 23/09, segmentador do Diário 2.0.0 em 648 edições.
- **Finanças voltou a responder.** A função de linhagem exata, usada por todas as
  RPCs públicas de Finanças, varria o acervo inteiro a cada chamada e passou do
  timeout de 3 s do papel `anon` conforme o dreno do TCM-BA cresceu (`/api/health`
  estava `degraded` desde 21/09). Índices parciais levaram a cobertura de ~3,5 s
  para ~0,3 s; um índice por `record_type` levou contratos, processos e sanções
  de 1,2–2 s para 0,2–0,4 s (PR #788).
- **`/licitacoes` deixou de pesar 2,7 MB:** lista compacta com página própria
  por contratação (`/licitacoes/contratacao/<número>`, PR #789) e paginação dos
  painéis municipais (PR #793).
- **Fila de aliases:** o sugestor não reenvia nomes já aprovados ou decididos;
  a fila visível caiu de 100 para 48 (PR #790).
- **Falhas de coleta:** HTTP permanente não é mais registrado como "nova
  tentativa agendada" (PR #791).
- **Sitemap:** de 16 para ~1.050 URLs, com edições, contratações, fornecedores
  pessoa jurídica e meses financeiros completos (PR #792).
- **Diário 4310/2024:** índice de 15 documentos (páginas 1–137) conferido
  visualmente, exibido só para o PDF de hash `424488a81d36041e...`. Os links
  abrem o original na página inicial; não publica OCR nem PDFs derivados e não
  comprova pagamentos (PR #787).

## Pendências abertas, por prioridade

0. **Privacidade: CPF no texto público do Diário. Corrigido em 25/09, falta
   só vigiar.** A auditoria mediu 3.093 CPFs completos em 712 documentos
   públicos (260 edições), e a busca encontrava documento por CPF. A
   migration `20260925121627_diario_public_cpf_mask` (PR #829) passou a
   mascarar CPF em edição, lista, busca, atos e resumos, com a coluna gerada
   `public_full_text` e a função `editorial.mask_cpf_v1` (cpf-mask/1.0.0).
   O texto literal e o hash não mudam. Conferido pela API anônima: nenhum CPF
   completo nas saídas e busca por CPF vazia. Limite: CPF muito deformado pelo
   OCR e sem o rótulo "CPF" perto pode escapar
   ([`reviews/DIARIO_OCR_QUALITY_AUDIT_2026_09_25.md`](reviews/DIARIO_OCR_QUALITY_AUDIT_2026_09_25.md)).
1. **Texto do Diário: fila de OCR zerada em 24/09.** A auditoria de 22/09
   achou ~15 mil páginas publicadas cuja extração era só o número da página.
   Em 24/09 o dreno `ocr-gazette-backlog` passou a reconhecer 4 páginas em
   paralelo (PR #815) e rodou em lotes manuais; 16.607 páginas têm OCR e 321
   edições foram reorganizadas no dia (5.395 documentos). Três gargalos
   apareceram e foram corrigidos: busca de atos pendentes (#817) e fila de
   reorganização (#819) passavam do `statement_timeout` de 15 s do coletor, e
   as cópias erradas servidas pelo catálogo travavam a reorganização (#818).
   4263 e 4309 de 2024 eram erro do catálogo da diariomtransparente (redireciona
   para `diario4264.pdf` e `diario4310.pdf`); o coletor usa o PDF canônico da
   prefeitura (#816) e as duas já estão no ar com o conteúdo certo. As cópias
   seguem no bruto, fora das filas. Atos de edições com OCR exibem aviso de
   transcrição. Pendências: o agendador do GitHub dispara o dreno só ~5 vezes
   por dia (suficiente para as ~700 páginas novas diárias do backfill).
   Auditoria por amostragem (25/09, 29 páginas): texto corrido e valores
   monetários conferidos fiéis, mas `§` vira `8` de forma sistemática (2.163
   páginas), tabelas perdem colunas e há erros de dígito isolados
   ([`reviews/DIARIO_OCR_QUALITY_AUDIT_2026_09_25.md`](reviews/DIARIO_OCR_QUALITY_AUDIT_2026_09_25.md)).
2. **Rastro do dinheiro ponta a ponta (gate 4), contrato → empenho →
   liquidação → pagamento no ar:** empenhos e liquidações individuais do sistema
   Sudoeste/WebRun preservados mês a mês de janeiro de 2024 a agosto de 2026
   (64 partições `complete`; 82.660 empenhos e 53.070 liquidações; ADR 0086).
   A ligação empenho → contrato é decidida por regra determinística: 21.121
   empenhos ligados a 642 contratos e publicados com rótulo (ADR 0087);
   13.516 citações aguardam revisão humana (6.974 sem contrato no portal,
   6.385 com favorecido divergente — de grafias diferentes da mesma empresa a
   números de contrato atribuídos a outra empresa —, 133 duplicatas do
   portal, 22 ilegíveis, 2 com várias citações). A fila de revisão humana
   (aba "Empenhos × contratos" do admin) agrupa 6.518 dessas citações em 304
   grupos com contrato candidato; confirmações publicam com rótulo de revisão
   humana. Cada empenho mostra suas liquidações e seus pagamentos pela chave
   oficial da fonte, sem somar estágios; pagamentos coletados de 2024-01 a
   2026-08 (32 meses, 53.731 pagamentos). Faltam os meses anteriores a
   2024, que a série histórica da fonte não entrega
   ([`sources/PREFEITURA_DESPESAS_WEBRUN.md`](sources/PREFEITURA_DESPESAS_WEBRUN.md)).
3. **Dados abertos:** `apps/public-api` está vazio e a única exportação CSV é a
   da Farmácia Popular. A visão prevê downloads e API com os mesmos estados da
   interface.
4. **Executor de novas tentativas:** `next_retry_at` é exibido, mas nenhum
   componente repete as coletas vencidas. As 111 falhas de indisponibilidade da
   API complementar do Querido Diário (TLS, desde agosto) precisam de executor ou
   de estado próprio de fonte opcional.
5. **Autoria legislativa:** coautorias chegam num campo só ("A e B", "A / B") e
   geram a maior parte das novas sugestões de alias; suplentes em exercício e
   autoria do Executivo ainda não têm perfil próprio.
6. **Qualidade medida:** a amostra anotada para precisão e revocação da extração
   de atos segue pendente.

## O que já está disponível no portal

- Diário Oficial com busca global, paginação, edição permanente, texto extraído
  por documento, páginas, fonte e hashes;
- atos oficiais aprovados com evidência e canal público de correção;
- receitas, despesas, fechamentos, obrigações e folha em agregados validados,
  com matriz pública mensal de cobertura desde 2021 e mapa de fontes que
  preserva as cadências mensal, bimestral, quadrimestral e anual; a série mensal
  do TCM-BA fechou 60 de 60 competências de 2021 a 2025 (auditoria de
  01/09/2026);
- licitações, processos, contratos, itens, fornecedores, sanções CEIS/CNEP e
  recortes do PNCP, com página própria por contratação e por fornecedor;
- leis e proposições da Câmara com autoria publicada e aliases revisados;
- Executivo, vereadores, representantes estaduais e federais, candidaturas e
  votos em Barreiras separados por eleição, cargo e turno;
- emendas e transferências federais e estaduais, mantendo autorização,
  empenho, transferência e pagamento como estágios distintos;
- Farmácia Popular em `/recursos/saude`, com publicação conferida por
  estabelecimento;
- painel administrativo de revisão, cobertura e falhas das fontes, com MFA.

## Limitações que permanecem explícitas

- o gate de sete dias exige vinte sondagens **agendadas** por dia encerrado;
  disparos manuais não preenchem essa cobertura e atrasos do GitHub Actions
  aparecem como cobertura insuficiente, não como disponibilidade comprovada;
- cobertura histórica varia por fonte; período não classificado não pode ser
  apresentado como vazio;
- parte da execução estadual antiga não possui chave oficial suficiente para
  ligação única com as autorizações territoriais;
- o catálogo mensal do TCM-BA é fonte privada em validação e não autoriza,
  sozinho, publicar valores financeiros; o formulário do e-TCM só funciona pelo
  executor Windows validado;
- o CDN do TSE responde HTTP 403 a runners hospedados; os recortes de 2022 e
  2024 foram importados em 18/08/2026 e o de 2024 marca os 20 CPFs como não
  divulgáveis;
- a API complementar do Querido Diário segue sujeita a timeout TLS; catálogo e
  PDFs oficiais continuam obrigatórios;
- fatos literais aprovados podem ser automáticos, mas identidade ambígua,
  conflito entre fontes e interpretação reputacional exigem revisão.

## Gates prioritários

1. Saúde real: endpoints públicos, falhas e cobertura não podem depender de
   respostas estáticas nem selos verdes isolados.
2. Cobertura desde 2021: cada partição deve terminar como completa, vazia,
   parcial, falha ou bloqueada — nunca desconhecida por omissão.
3. Experiência pública: nenhuma página deve transbordar no celular; listas
   grandes usam paginação e carregam o inteiro teor somente no detalhe.
4. Rastro do dinheiro: relacionar origem, órgão, empenho, liquidação, pagamento,
   contrato, fornecedor, objeto e parlamentar somente por chaves oficiais.
5. Evidência: todo total, ranking e aviso de ausência precisa permitir conferir
   fonte, período, metodologia e documento.
6. Prontidão: sete execuções agendadas consecutivas sem falha não tratada,
   sete dias sem HTTP 500 público e CI completo verde antes do lançamento.

## Próximo fluxo vertical

Recuperar o texto do Diário nas páginas com extração vazia: reprocessar o OCR
das 14.832 páginas pela fila já preparada, comparar com a extração anterior sem
sobrescrever versões publicadas e republicar apenas por nova versão auditada.
Em seguida, o primeiro elo individual do rastro do dinheiro: um contrato do PNCP
ligado aos seus empenhos e pagamentos por chave oficial, com a mesma disciplina
de estágios separados.
