# Matriz de ETLs e fontes

## Conclusão do inventário

Os comandos citados pelo repositório **Polígrafo** são referências de produto,
não componentes prontos para produção no **Barreiras em Dados**. O código está
sob licença MIT, mas precisa ser reescrito para nossa arquitetura de evidências,
escopo municipal, minimização e credenciais restritas.

Nenhum script foi copiado nesta análise.

## Avaliação comando a comando

| Referência | Decisão | Uso em Barreiras | Problema observado na referência | Implementação exigida |
|---|---|---|---|---|
| `ceap-sync.ts` | reescrever/adaptar | despesas de deputados federais monitorados | usa HTTP, chave `service_role`, apaga o ano, grava direto no cache, mantém CPF/CNPJ bruto e não preserva ZIP/CSV | download HTTPS oficial, hash e bruto imutável; parsing por versão; documento fiscal minimizado; normalização e publicação separadas |
| `frequencia-sync.ts` | reescrever | Câmara Federal e, com contratos próprios, ALBA/Câmara local | presume que todo deputado não listado em evento é “ausência não justificada” e limita silenciosamente a coleta | preservar eventos e participantes; modelar universo elegível, presença regimental, justificativa e cobertura sem inferência |
| `votacoes-sync.ts` | reescrever/adaptar | votos nominais nas três casas | agrega voto e abstenção como “ausência”, corta paginação por limite arbitrário e apaga o ano | preservar votação, orientação, objeto, voto nominal e tipo; não inventar voto em deliberação simbólica |
| `emendas-pix-sync.ts` | rejeitar mapeamento atual e reescrever | recursos destinados a Barreiras | apaga o ano e usa valor empenhado/pago como proxy de categorias econômicas diferentes | usar APIs atuais CGU/Transferegov; modelar autorizado, empenhado, transferido, pago e executado como eventos distintos |
| `tse-sync-real.ts` | rejeitar implementação; manter ideia | candidaturas e bens por eleição | o script rotulado como bens ignora bens e grava `valor_total=0`; usa CPF como resolução principal e não preserva bruto | usar datasets oficiais TSE/CKAN, candidaturas e bens separados, status diário, identificador TSE, hash e versões |
| `tse-doadores-sync.ts` | adiar e redesenhar | prestação de contas de candidatos vinculados a Barreiras | agrupa por nome+UF, armazena CPF/CNPJ de doadores em arrays e não resolve homônimos | consumir download oficial sem contornar WAF; vincular por candidatura; minimizar pessoa natural; publicar valores e doações com contexto |
| `fotos-sync.ts` | adaptar | fotos oficiais de ocupantes/candidatos | deriva URL e armazena sem metadados de licença, hash ou histórico | usar recurso oficial, registrar autoria/termo/URL/data/hash e gerar derivados sem apagar o original |
| `ibama-sync.ts` | rejeitar implementação | possível registro administrativo futuro | insere dados fictícios e documentos pessoais; não coleta o IBAMA | fonte oficial de autos, bruto preservado, identificador exato, situação e revisão reputacional; nenhum dado fictício fora de fixture |
| `anac-sync.ts` | rejeitar implementação e adiar módulo pessoal | estudo futuro, se houver finalidade proporcional | insere aeronaves e proprietários fictícios e usa documento pessoal | se aprovado juridicamente, usar dataset oficial RAB e publicar só vínculo exato, necessário e revisado; nunca pesquisar por nome |
| `sync:spu` | redirecionar | imóveis **da União** situados em Barreiras | a finalidade pode ser confundida com patrimônio privado de político; exige CSV manual | integrar como camada territorial de patrimônio público federal, nunca como bem pessoal |
| `sync-cmrj-servidores.ts` | não reutilizar | nenhum; CMRJ é Rio de Janeiro | endpoint de outro Município, apaga tabela e substitui o retrato inteiro | criar conector próprio para os PDFs/recursos da Câmara de Barreiras, com histórico e minimização |
| `cmrj_cotas_etl.ts` | não reutilizar | nenhum; CMRJ é Rio de Janeiro | Playwright e IA extraem PDFs de outra casa e gravam diretamente sem gate editorial | descobrir primeiro fonte oficial local; API/download antes de browser; IA somente como extração candidata validada |

## O que pode ser aproveitado conceitualmente

### Polígrafo

- mapa de integrações federais;
- React Flow como camada de visualização;
- testes de rate limit e clientes de APIs como lista de cenários;
- downloads em lote para CEAP e TSE;
- ideia de exportar recortes.

Não aproveitar:

- linguagem de “letalidade”, “empresa suspeita” ou “rede de corrupção”;
- julgamento automático por IA;
- busca DataJud por pessoa;
- credencial `service_role` compartilhada entre ETLs;
- exclusão e recarga de tabelas;
- caches sem origem bruta;
- dados fictícios apresentados como sincronização.

### Honestidade Políticos Brasil

Pode inspirar:

- canal de contestação;
- documentação de fonte;
- validação automática de arquivos;
- contribuição pública e atualização periódica.

Não será adotado score de honestidade, ranking moral, “ficha limpa” calculada ou
classificação excelente/ruim. Misturar presença, patrimônio, produtividade e
processos em uma nota produz uma conclusão reputacional que os dados não
sustentam.

O conteúdo está sob CC BY 4.0; eventual adaptação exige atribuição e indicação de
mudanças.

### Transparência Política 2026

Pode inspirar:

- navegação por ente, pessoa e votação;
- separação de coletores de Câmara, Senado e SICONFI;
- componentes de perfil.

O ZIP analisado não contém arquivo de licença separado. Conceitos gerais podem
ser estudados, mas nenhum código, texto ou asset será incorporado até licença e
proveniência serem confirmadas.

## Arquitetura padrão para cada ETL

Cada integração nova precisa dos mesmos componentes:

1. cadastro de fonte e endpoint;
2. contrato tipado e fixture sanitizada;
3. cliente HTTP com identificação, rate limit, retry, backoff e circuit breaker;
4. preservação do arquivo/resposta original por SHA-256;
5. registro de execução, cursor, versão e cobertura;
6. parsing determinístico e versionado;
7. DLQ para linha inválida;
8. normalização temporal;
9. resolução de identidade separada;
10. reconciliação e conflitos;
11. revisão editorial quando necessária;
12. projeção pública somente de aprovados.

O acesso ao banco será por role específica por fonte. ETLs não receberão
`postgres` nem `service_role`. A role coleta e registra bruto; não publica.

## Agendamento no GitHub Actions

Automação só entra depois de duas execuções manuais idempotentes e restauração de
artefato comprovada. O workflow deve:

- usar `permissions: contents: read`;
- fixar actions por SHA após revisão;
- não executar segredos de produção em pull requests;
- usar `concurrency` por fonte;
- declarar timeout;
- produzir resumo sem dados pessoais;
- falhar quando houver schema desconhecido;
- preservar artefatos brutos no Storage, não no log;
- alertar DLQ, lacuna e circuito aberto;
- permitir replay de uma janela sem apagar a anterior.

## Ordem recomendada

1. concluir e repetir o Querido Diário remoto;
2. atos de nomeação/exoneração e perfil mínimo;
3. PNCP e contratações locais;
4. roster oficial municipal e remuneração;
5. TSE candidaturas/bens de 2024 e 2026;
6. sessões, votos e despesas da Câmara de Barreiras;
7. emendas e representantes estaduais/federais;
8. CEAP;
9. CGU e QSA com revisão;
10. doadores, IBAMA e ANAC somente após avaliação específica.
