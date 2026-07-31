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

## Pendências para as próximas fatias

- ações de aprovar/rejeitar gravando em `editorial.editorial_reviews` com
  auditoria e dupla revisão;
- exigência de MFA (enrolamento TOTP e verificação `aal2` na RPC);
- cadastro do primeiro revisor real (exige conta criada pelo titular e
  ativação registrada);
- deploy do admin como projeto separado na Vercel;
- paginação/filtros e testes negativos de autorização em produção.
