# ADR 0008 — PostgreSQL e armazenamento de objetos portáveis

- Estado: Aceita
- Data: 2026-07-30

## Contexto

O plano inicial usava Supabase para PostgreSQL, Auth e Storage. A conta de
desenvolvimento atingiu o limite de dois projetos gratuitos ativos e o projeto
municipal não deve reutilizar, pausar ou apagar aplicações sem relação com ele.
O coletor também não pode depender de um único fornecedor para preservar
evidências públicas.

## Decisão

Manter o modelo SQL compatível com PostgreSQL e acessar bytes por uma porta de
armazenamento de objetos. Supabase é um adaptador possível, não uma dependência
do domínio.

Em `development` e `test`, o modo `filesystem`:

- grava objetos em chaves endereçadas por SHA-256;
- cria arquivos com exclusividade e nunca faz overwrite;
- restaura e verifica os bytes após a escrita;
- grava um manifesto canônico e imutável por execução e versão de parser;
- detecta alteração, corrupção, conflito de idempotência e tentativa de escapar
  do diretório permitido.

Esse manifesto é um pacote local de evidência e replay. Ele não substitui o
PostgreSQL como banco operacional nem é permitido em staging ou produção.

O futuro provedor deverá oferecer PostgreSQL padrão e armazenamento privado
compatível com S3 ou uma nova implementação da mesma porta. Auth poderá ser
escolhido separadamente.

## Consequências

- coletores e contratos continuam funcionando durante a escolha de hospedagem;
- dados locais ficam fora do Git e não carregam segredos;
- o teste remoto de migrations, grants, backup e object lock continua sendo um
  gate obrigatório antes de staging;
- adaptadores de nuvem exigem revisão própria de identidade, TLS, retenção e
  custo;
- o modo local preserva a primeira observação idempotente e permite manifestos
  adicionais para novas versões do parser.

## Alternativas

- Reutilizar um projeto Supabase existente: rejeitada por isolamento e risco.
- Pausar ou apagar outro projeto: rejeitada sem autorização específica.
- Adotar SQLite como banco do produto: rejeitada por divergência semântica com
  PostgreSQL, filas, grants e migrations.
- Paralisar todo o fluxo até contratar nuvem: rejeitada porque aquisição,
  hashing e replay podem ser validados com segurança localmente.
