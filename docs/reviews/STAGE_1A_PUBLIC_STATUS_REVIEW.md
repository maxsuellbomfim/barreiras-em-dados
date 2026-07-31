# Revisão da etapa 1A — status público da coleta

Data: 31/07/2026.

## Escopo

Esta entrega publica somente o estado técnico do primeiro acervo do Querido
Diário. Não publica atos, pessoas, cargos, inferências, anomalias ou conclusões
sobre agentes públicos.

## Banco e API

- RPC versionada `api.get_querido_diario_collection_status()`;
- agregação determinística de edições, respostas e cobertura;
- schema `api` incluído explicitamente na Data API;
- execução concedida a `anon` e `authenticated`;
- `SELECT` anônimo negado em `raw.raw_records` e `raw.raw_artifacts`;
- migrations aditivas, auditáveis e aplicadas ao projeto isolado.

## Portal

- consulta somente no servidor Next.js;
- duas variáveis públicas, sem senha ou service role;
- validação estrita do payload e da versão metodológica;
- timeout de cinco segundos e revalidação em cinco minutos;
- fallback que diferencia falha de consulta de ausência de dados;
- interface responsiva baseada no sistema de design Apple do projeto.

## Qualidade dos dados

A inspeção visual encontrou mojibake no nome e na descrição de três fontes. Uma
migration corretiva registrou os estados anterior e posterior em
`audit.audit_events`; nenhuma versão foi apagada.

O resultado remoto verificado contém:

- fonte `Querido Diário`;
- última execução com estado `succeeded`;
- cobertura de 10/06/2026;
- duas edições distintas;
- uma resposta bruta distinta;
- metodologia `querido-diario-collection-status/1.0.0`.

Essas contagens representam uma amostra-piloto, não cobertura histórica.

## Segurança

- nenhuma credencial administrativa no código, chat ou Vercel;
- nenhuma chave secret/service role aceita pelo portal;
- função com `search_path` vazio e objetos totalmente qualificados;
- ausência de dados pessoais ou reputacionais na resposta;
- advisor do Supabase mantém apenas o aviso conhecido de proteção contra senhas
  vazadas, indisponível no plano gratuito;
- dependências de produção sem vulnerabilidade conhecida na auditoria executada.

## Verificação

- teste da migration e autorização negativa;
- validação de contratos e inventário de fontes;
- testes Node e Python;
- TypeScript e build de produção;
- resposta real da RPC com publishable key;
- desktop 1440 px e mobile 390 px sem overflow;
- revisão de contraste, movimento e transparência reduzidos;
- verificação de diff e busca por segredos.

## Limitações e gate de publicação

- a Vercel ainda precisa receber
  `PUBLIC_DATA_SUPABASE_URL` e
  `PUBLIC_DATA_SUPABASE_PUBLISHABLE_KEY` nos ambientes `Production` e
  `Preview`;
- o pull request não deve ser mesclado antes dessa configuração;
- PDFs/textos, lacunas, backup e exercício integrado de DLQ/circuit breaker
  permanecem pendentes;
- registros normalizados só poderão aparecer após revisão humana e aprovação.

## Próxima menor etapa vertical

Preservar PDF e texto de uma edição como artefatos filhos verificados por hash,
identificar candidatos determinísticos de nomeação/exoneração e colocá-los na
fila humana sem qualquer publicação automática.
