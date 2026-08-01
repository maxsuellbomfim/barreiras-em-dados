# Revisão da etapa 1C — fatia 1: fila de revisão autenticada (somente leitura)

Data: 31/07/2026.

## Escopo

Primeira fatia do portal admin (`apps/admin`): uma pessoa autenticada e
cadastrada como revisora ativa vê a fila de candidatos `needs_review` com os
campos extraídos e o trecho do documento oficial lado a lado. Nenhuma ação de
aprovação existe ainda; nada é publicado; o portal público não muda.

## Banco e autorização

- tabela `audit.reviewer_identities` (RLS forçada, sem acesso a
  anon/authenticated): cadastrar revisor é um ato explícito e auditável, nunca
  um efeito colateral de criar conta;
- RPC `api.get_extraction_review_queue(page_size)` com `security definer`,
  `search_path` vazio e objetos qualificados; concedida somente a
  `authenticated`;
- conta autenticada que não é revisora ativa recebe **erro explícito**
  (`42501`), nunca fila vazia — falha de autorização não se disfarça de
  ausência de dados;
- criar conta no Auth continua possível para qualquer pessoa, mas não dá
  acesso a nada: o dado só sai com identidade cadastrada em
  `reviewer_identities` por migração/ato registrado.

## Portal admin

- `apps/admin` é um app Next.js separado (porta própria, `noindex`,
  cabeçalhos de segurança), com login por e-mail/senha do Supabase Auth e
  chave publicável — nenhuma chave administrativa em código cliente;
- a fila mostra tipo do ato, campos (`Pessoa`, `Cargo`, `Símbolo`, `Órgão`)
  com "não encontrado — confira o trecho" quando a regra não casou, o trecho
  oficial em `details`, versão do extrator, hash do artefato e metodologia;
- fila vazia é apresentada como estado legítimo, distinto de erro e de acesso
  negado;
- acessibilidade básica: HTML semântico, labels, `role="alert"`,
  `aria-live`, contraste em claro/escuro e `prefers-reduced-motion`.

## Verificação

- teste de migrations: 41 tabelas; RPC nega não revisor com a mensagem
  esperada e devolve o candidato semeado para revisor ativo;
- typecheck e build de produção do `apps/admin`;
- migration aplicada ao projeto isolado.

## Fatia 2 — decisão humana com auditoria (01/08/2026)

- RPC `api.review_extraction_candidate(result_id, decision, rationale)`:
  exige revisor ativo, decisão `approved`/`rejected` e justificativa com no
  mínimo 5 caracteres; grava a decisão em `editorial.editorial_reviews`
  (`target_type='raw.extraction_results'`) e um evento
  `extraction_candidate_reviewed` em `audit.audit_events`;
- o dado bruto permanece intacto: `raw.extraction_results.validation_status`
  não é alterado — a decisão vive na camada editorial, e a fila
  (`extraction-review-queue/1.1.0`) passa a excluir candidatos com decisão
  final;
- segunda decisão sobre o mesmo candidato é recusada com erro explícito
  (regra de revisor único; dupla revisão substituirá essa checagem);
- **aprovar não publica**: a projeção pública dos aprovados é uma fatia
  futura e separada;
- portal: cada cartão ganhou justificativa obrigatória e botões
  Aprovar/Rejeitar (desabilitados até a justificativa mínima), com aviso
  explícito de que a publicação é etapa separada;
- primeiro revisor real cadastrado e ativado em 01/08/2026 com evento de
  auditoria (`reviewer_identity_activated`); acesso validado por simulação
  da identidade na RPC;
- verificação: teste de migrations cobre justificativa obrigatória, decisão
  inválida, aprovação, fila esvaziada, dupla decisão negada, contagem de
  auditoria, bruto intocado e negação a não revisor; typecheck e build do
  admin.

## Pendências para as próximas fatias

- exigência de MFA (enrolamento TOTP e verificação `aal2` nas RPCs);
- projeção pública somente de aprovados (`editorial.published_insights` e
  páginas no portal);
- paginação/filtros e testes negativos de autorização em produção;
- dupla revisão de amostra antes do gate da etapa.
