# Modelo de segurança

## Objetivos

1. impedir alteração ou perda silenciosa de evidências;
2. impedir publicação sem autorização editorial;
3. proteger credenciais, painel administrativo e dados pessoais;
4. tratar documentos e respostas externas como conteúdo hostil;
5. manter disponibilidade sem sobrecarregar fontes oficiais.

## Ativos críticos

- artefatos brutos, hashes e proveniência;
- banco normalizado e histórico de versões;
- decisões editoriais e trilha de auditoria;
- credenciais de banco, Storage, deploy e fontes;
- contas administrativas;
- código de coletores/parsers e regras metodológicas.

## Atores e ameaças

- atacante externo explorando web/API;
- conta administrativa comprometida;
- dependência ou GitHub Action maliciosa;
- fonte externa retornando PDF/HTML/JSON hostil;
- erro de parser que corrompe semântica;
- colaborador alterando histórico ou aprovando indevidamente;
- indisponibilidade/rate limit causando lacuna interpretada como ausência.

## Fronteiras de confiança

- internet → collector;
- objeto bruto → parser/OCR;
- worker → banco interno;
- banco interno → revisão;
- revisão → projeção pública;
- cliente público → web/API;
- administrador → painel e ações privilegiadas.

## Controles

### Aquisição

- allowlist de hosts por endpoint;
- bloquear redirects para IP privado/loopback e prevenir SSRF;
- timeouts de conexão/leitura e limite de bytes;
- rate limit por fonte, retries com jitter e respeito a `Retry-After`;
- circuit breaker por endpoint;
- TLS validado; nunca desabilitar verificação de certificado;
- respostas salvas antes do parsing.

### Conteúdo não confiável

- MIME detectado por conteúdo e comparado com o declarado;
- PDFs/OCR processados fora do frontend e sem execução de JavaScript;
- limites de páginas, tamanho, CPU e memória;
- nomes de arquivo nunca usados como caminho local;
- HTML renderizado somente após sanitização estrita;
- nenhum comando construído com texto da fonte.

### Banco e provedor

- schemas internos não expostos pela Data API;
- RLS em toda tabela de schema exposto;
- grants explícitos e mínimos;
- views públicas com `security_invoker = true`;
- nenhuma secret/service role em `NEXT_PUBLIC_*`;
- workers com credenciais próprias e permissões por schema;
- roles de aplicação sem DELETE em bruto/auditoria;
- login do coletor como membro de `collector_worker`, nunca como `postgres`;
- conexão PostgreSQL remota com TLS obrigatório e timeouts por role/transação;
- funções privilegiadas em schema privado, `search_path` fixo e EXECUTE revogado
  de `PUBLIC`.

### Storage

- bucket bruto privado;
- upload apenas por worker confiável;
- download público via proxy/signed URL depois de decisão editorial;
- verificação de SHA-256 após upload;
- object key derivada do hash, sem dados pessoais;
- operações pelo Storage API, sem editar tabelas `storage` diretamente.
- coletor autenticado por usuário Auth técnico e chave publicável;
- allowlist interna por UUID, bucket, prefixo, operação, estado e validade;
- somente `SELECT` e `INSERT`; ausência explícita de `UPDATE` e `DELETE`;
- secret/service role recusada pelo coletor porque ignora RLS;
- desativação exige primeiro suspender a allowlist e a role PostgreSQL, depois
  revogar as sessões Auth.
- modo local permitido somente em `development`/`test`;
- diretório local relativo, fora do Git e sem links simbólicos;
- criação exclusiva de objetos/manifestos e verificação pelo hash do nome;
- o acervo local não é backup de produção nem mecanismo de controle de acesso.

### Administração

- MFA obrigatório;
- sessões curtas para ações sensíveis;
- autorização em `app_metadata`, nunca `user_metadata`;
- aprovação/publicação com reautenticação e proteção CSRF;
- separação entre extrator, revisor e publicador para conteúdo sensível;
- auditoria append-only de login, revisão, publicação, correção e exportação.

### Aplicações públicas

- CSP restritiva, HSTS, headers seguros e cookies `Secure`/`HttpOnly`;
- validação de entrada e limites de consulta/exportação;
- rate limit compartilhado, não somente memória da instância;
- paginação por cursor;
- mensagens de erro sem stack trace, SQL ou segredo;
- cache apenas de projeções públicas.

### Integrações de IA

- chaves somente no secret manager do runtime que executa a chamada;
- allowlist de provedores, modelos e finalidades;
- orçamento, timeout, rate limit e circuit breaker por provedor;
- minimização/redação antes do envio e bloqueio de dados sensíveis;
- revisão de retenção, treinamento, localização e suboperadores do provedor;
- prompt, versão, hash da entrada e saída registrados sem duplicar segredo;
- conteúdo retornado tratado como não confiável e validado por schema;
- nenhuma ferramenta de escrita, publicação ou consulta livre ao banco
  concedida ao modelo.

### Grafos e exportações

- API do grafo entrega somente relações aprovadas;
- limite de profundidade, quantidade de nós e custo da consulta;
- nenhuma busca pública por CPF ou identificador pessoal oculto;
- exportações assíncronas, com autorização, rate limit e expiração de link;
- hash, filtros, dataset e ator registrados na auditoria;
- conteúdo reputacional não pode contornar revisão por meio de CSV/PDF/DOCX;
- em células textuais de planilha, conteúdo externo iniciado por `=`, `+`, `-`
  ou `@` é neutralizado para prevenir formula injection; células numéricas
  tipadas não são convertidas em texto.

O portal de pré-lançamento é estático, não usa cookies, autenticação,
analytics, segredos ou acesso direto ao Supabase. HSTS, proteção contra
iframes, `nosniff`, política de referência e bloqueio de câmera/microfone/
geolocalização já estão ativos. A CSP com nonce permanece um gate antes de
qualquer script externo, login ou conteúdo gerado por usuário.

O lockfile fixa as versões de produção. A primeira publicação usa overrides
para `sharp 0.35.0` e `postcss 8.5.18`, versões corrigidas para advisories
encontrados na auditoria das dependências transitivas do Next. Build e auditoria
devem ser repetidos quando o Next incorporar versões compatíveis sem override.

### Supply chain e CI

- versões fixadas e lockfiles commitidos;
- Actions de terceiros pinadas por SHA;
- workflows com `permissions: contents: read` por padrão;
- scans de secrets, dependências e código;
- builds de PR sem acesso a secrets de produção;
- SBOM e procedimento de atualização documentado antes do lançamento.

## Auditoria

Todo evento privilegiado inclui ator, ação, alvo, versão anterior/nova, horário,
request/correlation ID e motivo. Logs operacionais não substituem a trilha
editorial.

## Backups e recuperação

- backup separado do Storage;
- restauração testada trimestralmente;
- runbook para fonte comprometida, hash divergente, publicação indevida,
  segredo exposto e conta admin comprometida;
- capacidade de retirar projeção pública sem apagar evidência.

## Segurança de dados pessoais

Inventário e classificação precedem a publicação. Dados sensíveis,
identificadores completos, contatos e descontos individuais são bloqueados por
padrão. Acesso interno é justificado, limitado e auditado.

## Checklist por etapa

- modelagem de ameaça atualizada;
- grants/RLS revisados;
- secrets fora do repositório;
- testes de autorização negativos;
- fixture hostil e limites de parsing;
- dependências e Actions verificadas;
- restauração e retração testadas;
- limitações documentadas.

Referências:

- [Segurança do Storage Supabase](https://supabase.com/docs/guides/storage/security/access-control)
- [RLS no Supabase](https://supabase.com/docs/guides/database/postgres/row-level-security)
- [OWASP ASVS](https://owasp.org/www-project-application-security-verification-standard/)
