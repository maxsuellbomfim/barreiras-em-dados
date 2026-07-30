# Revisão da etapa 0

Data: 30/07/2026

## Resultado

A fundação arquitetural está implementada. O produto ainda não publica dados e
o conector ainda não persiste artefatos. A próxima etapa permanece limitada à
coleta preservada de uma janela pequena do Diário Oficial.

## Verificações executadas

- 16 testes offline do coletor e ambiente: aprovados;
- 5 contratos JSON Schema com validação estrutural: aprovados;
- 2 catálogos sanitizados das APIs locais: 79 recursos oficiais;
- migration e seed executados duas vezes em PostgreSQL 17 embutido/PGlite:
  aprovados;
- 39 tabelas fundamentais criadas;
- 25 entidades normalizadas com `origin_raw_record_id NOT NULL`;
- smoke test somente leitura do Querido Diário: HTTP 200 e território
  `2903201`;
- auditoria npm: nenhuma vulnerabilidade conhecida;
- busca por chave privada/token típico, CPF formatado e float monetário:
  nenhum achado real.

O lint da CLI Supabase contra uma instância local não foi executado porque não
há Docker ou Podman instalado.

## Revisão de segurança

Controles presentes:

- schemas internos não expostos pelo Data API;
- Data API local configurada somente para o schema vazio `api`;
- bucket `raw-artifacts` privado;
- respostas brutas e auditoria com bloqueio de update/delete;
- HTTPS, allowlist de host e redirects restritos;
- limite de tamanho de resposta;
- headers potencialmente sensíveis não persistidos;
- rate limit, backoff com jitter, `Retry-After` e circuit breaker;
- validação que bloqueia chave secreta com prefixo `NEXT_PUBLIC`;
- cadastro público local desativado e senha administrativa endurecida.

Pendências para a próxima etapa:

- scanner e sandbox para PDF antes do processamento;
- papel de banco dedicado para workers, sem chave ampla;
- políticas de lease/DLQ exercitadas em PostgreSQL Supabase real;
- armazenamento imutável/WORM ou object lock no provedor escolhido;
- política de backup/restauração e rotação de credenciais.

## Revisão de qualidade dos dados

Controles presentes:

- resposta vazia difere de falha/coleção parcial;
- campos aditivos são preservados e geram aviso;
- campos obrigatórios, datas, território e UF são validados;
- bytes, tamanho e SHA-256 de cada página são preserváveis;
- valores monetários usam `numeric`, nunca float;
- correções têm `supersedes_id` e versão;
- homônimos não são fundidos automaticamente;
- estado de revisão antecede publicação de atos.

Pendências:

- validação JSON Schema completa com Ajv 2020-12;
- identidade estável de edição e estratégia de URL com hash alterado;
- detector de duplicata entre páginas;
- corpus anotado de nomeações/exonerações;
- métricas de precisão e cobertura;
- reconciliação com o Diário direto e inventário de lacunas.

## Revisão editorial e conformidade

- fato, inferência, anomalia e hipótese estão separados;
- anomalia é declarada como sinal, nunca prova;
- rankings e rótulos morais foram excluídos;
- publicação reputacional exige revisão humana;
- canal de correção e histórico são requisitos;
- RIPD e revisão jurídica brasileira são gates antes de perfis longitudinais,
  folha individual ou vínculos cruzados;
- regras eleitorais de 2026 exigem política de isonomia e análise específica.

## Limitações conhecidas

- não há repositório Git inicializado;
- apps Next.js/FastAPI ainda são diretórios de arquitetura;
- não há persistência nem download de PDF no conector;
- não existe parser de atos, fila de revisão, admin ou projeção pública;
- não há lockfile Python nem dependências Python instaladas;
- PGlite valida PostgreSQL, mas não substitui teste final no stack Supabase;
- os contratos estão em bootstrap estrutural, ainda sem validação integral.

## Adendo — APIs locais

Em 30/07/2026 foram catalogadas as APIs oficiais da Prefeitura e da Câmara.
Foram adicionadas três fontes/seeds ao total: Querido Diário e os dois portais.

Achados que passam a ser requisitos de teste:

- `count` informa linhas da página, não total;
- paginação usa `limit` e `offset`;
- recurso inválido retorna HTTP 200 com raiz `error`;
- valores, datas e identificadores chegam como strings ou `null`;
- documentação e JSON real divergem em nomes de campos;
- documentos da Prefeitura podem apontar para
  `barreiras.mtransparente.com.br`;
- não há licença, SLA ou rate limit documentado;
- consumo inicial dos portais fica limitado localmente a 10 chamadas/minuto.

Isso não altera a próxima etapa: a persistência do Querido Diário deve ser
estabilizada antes de iniciar um novo conector.

## Próxima menor etapa vertical

1. executar a migration em Supabase local/descartável;
2. criar papel restrito do coletor;
3. persistir uma única página JSON do Querido Diário no bucket privado e nas
   tabelas `collection_runs`, `raw_artifacts` e `raw_records`;
4. reaplicar a mesma coleta e provar ausência de duplicatas;
5. simular 429, 5xx e esgotamento para provar retry e DLQ;
6. restaurar o artefato pelo hash;
7. exibir somente um health/status interno.

Não iniciar parser de nomeações nem PNCP antes desse gate.
