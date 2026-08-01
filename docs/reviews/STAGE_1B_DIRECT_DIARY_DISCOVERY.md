# Descoberta — coleta direta do Diário Oficial de Barreiras

Data: 01/08/2026. Pesquisa somente leitura; nenhuma coleta realizada.

## Por que o Querido Diário parou em 10/06/2026

- a página oficial `https://barreiras.ba.gov.br/diario-oficial/` virou apenas
  um iframe para a plataforma terceirizada
  `https://pmbarreiras.diariomtransparente.com.br/`;
- o raspador do Querido Diário para Barreiras (`ba_barreiras.py`) depende da
  estrutura antiga (`div.content .style16`) e quebrou com a migração — a
  edição mais recente no QD é 10/06/2026, com 4.030 edições históricas
  preservadas desde 2008;
- consequência: o QD segue excelente para **backfill e verificação cruzada**,
  mas o **presente** exige coleta direta.

## Como a fonte direta funciona (verificado ao vivo)

- listagem: `https://pmbarreiras.diariomtransparente.com.br/publicacoes`,
  com links `/publicacao?referencia=<id sequencial>` (conteúdo renderizado
  por JavaScript; metadados não são estáveis no HTML);
- **cada publicação redireciona (HTTP 302) para o PDF oficial em URL
  previsível**:
  `https://barreiras.ba.gov.br/diario/pdf/<ano>/diario<edição>.pdf`
  (ex.: edição 4703, 7,7 MB, verificada em 01/08/2026);
- o host `barreiras.ba.gov.br` já pertence a `ALLOWED_ARTIFACT_HOSTS` do
  coletor atual;
- os números de edição são sequenciais (as edições de 10/06 no QD são
  ~nº 4669–4670; a atual é 4703).

## Desenho proposto para o coletor direto (próxima fatia)

1. cursor por número de edição derivado do banco: a partir da maior edição
   conhecida, sondar `diario<n+1>.pdf` adiante até um limite curto por
   execução; 404 encerra a janela (estado explícito, não falha);
2. cada PDF vira `raw_artifact` (`document`, papel `pdf`) com SHA-256,
   idempotência por conteúdo e os mesmos limites/retries do
   `GazetteDocumentClient`;
3. a data e o número da edição saem do cabeçalho do próprio PDF na etapa de
   processamento (o texto canônico exigirá extração de texto do PDF — hoje
   só tratamos `.txt` do QD; avaliar `pypdf` fixado ou o texto do QD quando
   a edição aparecer lá, mantendo OCR fora de escopo);
4. nova fonte no seed (`barreiras-diario-oficial`, endpoint `pdf-directo`) e
   novo prefixo de Storage `barreiras-diario/gazettes/`, o que exige
   generalizar `audit.storage_workload_identities` (hoje o check restringe a
   um único prefixo e há `unique (auth_user_id)`);
5. QD permanece ativo como fonte de verificação cruzada e backfill; conflitos
   entre fontes vão para `evidence.source_conflicts`, sem fonte vencedora.

## Riscos anotados

- URLs previsíveis podem mudar de novo (a prefeitura acabou de trocar de
  plataforma); o cursor derivado do banco e estados explícitos limitam o
  dano a "zero novas edições", nunca silêncio;
- PDFs diretos não têm o `.txt` que o QD fornecia — a extração de candidatos
  para edições novas depende da fatia de texto de PDF;
- o QD usa proxy comercial no raspador; monitorar se a coleta direta a partir
  do GitHub Actions sofre bloqueio de IP (mitigação: retries/backoff já
  padrão; último recurso: janela menor por execução).
