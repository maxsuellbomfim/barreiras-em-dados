# Ativação segura do coletor municipal

Este roteiro ativa somente o corredor `municipal-transparency/` do projeto
Barreiras em Dados. Ele não compartilha credenciais com Querido Diário, PNCP,
Câmara ou TSE.

## Estado atual

- migration do corredor aplicada no Supabase;
- bucket `raw-artifacts` continua privado;
- nenhum usuário Auth municipal está na allowlist;
- nenhuma página real da Prefeitura ou Câmara foi persistida remotamente;
- nenhum valor financeiro foi normalizado ou publicado.

## Ação do responsável no painel Supabase

1. Abra **Authentication → Users** no projeto Barreiras em Dados.
2. Crie um usuário técnico novo, exclusivo para transparência municipal.
3. Use uma caixa técnica controlada, nunca a conta pessoal de administração.
4. Gere uma senha aleatória longa e guarde-a no gerenciador de senhas.
5. Marque **Auto Confirm User**.
6. Copie apenas o **User UID** do usuário criado.

Não envie e-mail, senha, token, chave `service_role`, publishable key ou
captura de tela com segredos. O agente precisa somente do UUID.

## Ativação posterior

Com o UUID, uma migration separada registrará uma linha em
`audit.storage_workload_identities` com:

- `slug`: `municipal-transparency-collector`;
- `bucket_id`: `raw-artifacts`;
- `object_prefix`: `municipal-transparency/`;
- `can_select`: `true`;
- `can_insert`: `true`;
- `status`: `active`;
- `UPDATE`, `DELETE` e `upsert`: nunca autorizados.

A migration não conterá senha. Depois da ativação serão executados, em janela
controlada, um upload de teste, restauração com SHA-256, tentativa negativa de
outro prefixo e uma única página oficial. O mesmo recorte será repetido para
confirmar idempotência antes de qualquer normalização financeira.

## Critério de publicação

O coletor só poderá escrever evidência bruta. A API municipal será inspecionada
primeiro para distinguir registros numéricos de catálogos ou links de documentos.
Somente depois dessa validação será criado um parser financeiro determinístico;
nenhum modelo de linguagem calculará totais.
