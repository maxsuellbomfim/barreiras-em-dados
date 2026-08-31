# MFA do painel de revisão

## Estado de implantação

O painel oferece cadastro TOTP e desafia sessões de contas que já possuem um
fator verificado. A política do banco nasce em `observe`: um revisor ativo sem
MFA ainda consegue trabalhar durante a adesão. O modo `required` só deve ser
ativado depois que ao menos uma conta administrativa tiver alcançado AAL2 e o
procedimento de recuperação abaixo tiver sido testado.

## Ativação controlada

1. Entre no painel com uma conta de revisão ativa.
2. Cadastre o TOTP e confirme que a sessão alcançou AAL2.
3. Saia, entre novamente e confirme que o painel exige o código.
4. Em uma sessão AAL2, chame a RPC
   `api.set_reviewer_mfa_enforcement(true, <justificativa>)`.
5. Confirme que uma sessão AAL1 de teste recebe `42501` nas RPCs de revisão e
   que a mesma conta volta a funcionar depois do desafio TOTP.
6. Confira a nova versão em `audit.reviewer_mfa_policy_versions` e o evento
   `reviewer_mfa_policy_changed` em `audit.audit_events`.

A justificativa deve explicar data, responsáveis e validações realizadas. A
RPC recusa contas não revisoras, sessões AAL1, justificativas curtas e mudanças
duplicadas. O histórico é append-only; não se altera nem apaga uma versão.

## Recuperação normal

Se um revisor perder o autenticador, outro administrador com sessão AAL2 deve
remover o fator perdido pelo fluxo administrativo oficial do Supabase e
orientar um novo cadastro. Não se solicita nem se armazena o segredo TOTP, QR
code ou código temporário em tickets, logs, chat ou banco da aplicação.

## Recuperação de emergência

Se não restar nenhuma sessão AAL2 funcional:

1. acesse o projeto pelo proprietário da organização no Supabase Dashboard;
2. confirme que o incidente se limita ao segundo fator, sem indício de tomada
   da conta principal;
3. pelo SQL Editor com papel administrativo, **insira uma nova versão** com
   modo `observe`, ator e justificativa de emergência; nunca atualize ou apague
   versões anteriores;
4. registre o mesmo motivo em `audit.audit_events`;
5. recupere ou recrie o fator TOTP de uma conta administrativa;
6. valide AAL2 e reative `required` pela RPC normal;
7. documente horário, operador, motivo e testes pós-recuperação.

Se houver suspeita de comprometimento, encerre as sessões da conta antes de
remover o fator e revise os eventos administrativos do período. Desativar MFA
não substitui revogação de sessão, rotação de senha ou investigação.

## Gate para tornar obrigatório

- pelo menos uma conta administrativa com TOTP verificado;
- login AAL2 testado em janela anônima;
- proprietário do projeto Supabase acessível;
- recuperação de fator testada sem registrar segredos;
- teste negativo AAL1 e positivo AAL2 nas RPCs;
- evento de ativação presente na trilha append-only;
- CI, migrations e Advisor de segurança verdes.
