# Portal público — contrato atual

Atualizado em 04/09/2026. Substitui a descrição do piloto de 31/07; aquele
documento não descrevia mais as funcionalidades disponíveis. O histórico
permanece no Git. Para cobertura operacional, leia [CURRENT_STATUS.md](CURRENT_STATUS.md).

Produção: <https://barreiras-em-dados.vercel.app>.

## O que o cidadão encontra

| Área | Contrato de leitura |
| --- | --- |
| `/diario` | Busca e paginação de edições; texto literal organizado por documento no detalhe, com páginas, fonte e hashes. Não é tradução nem resumo por IA. |
| `/atos` | Atos aprovados e sua evidência; nomeação não prova exercício nem remuneração. |
| `/financas` | Receitas, despesas, fechamentos e cobertura por período. Empenho, liquidação e pagamento não são somados entre si. |
| `/licitacoes` | Compras, contratos, itens e fornecedores com documentos e filtros. |
| `/camara` | Leis e proposições, autoria publicada e aliases revisados; autoria ausente não é inventada. |
| `/representantes` | Executivo, vereadores e representação territorial; eleição, turno, cargo e legislatura permanecem separados. |
| `/recursos` | Emendas e transferências com fonte, autoria e estágio; ranking financeiro não é nota geral de trabalho parlamentar. |
| `/estado` | Consulta atual às projeções de Diário, finanças e representação, sem afirmar cobertura histórica integral. |

## Dados e evidência

As páginas usam RPCs públicas autorizadas no schema `api` e validam seus
contratos. O browser não recebe credenciais privadas nem acesso às tabelas
internas. As variáveis `PUBLIC_DATA_SUPABASE_URL` e
`PUBLIC_DATA_SUPABASE_PUBLISHABLE_KEY` são configuração do servidor web;
autorização continua sendo responsabilidade dos grants e contratos do banco.

Cada estado tem significado próprio: consulta falha, dado não encontrado na
fonte, período não coletado e zero oficial não são equivalentes. A evidência
mostra quando e onde a consulta foi feita; ausência em uma fonte não prova
inexistência em todas as fontes.

Listas devem receber somente metadados paginados. O texto grande pertence ao
detalhe; fechar um `<details>` não reduz o que é enviado ao navegador. A auditoria
atual identificou payloads maiores que merecem revisão, mas não presumiu que
toda página grande transporta PDFs ou textos integrais.

## Disponibilidade não é completude

`/api/health` testa três projeções e retorna `ok`, `degraded` ou `unavailable`,
com HTTP 503 quando todas estão indisponíveis. Suas contagens descrevem o
recorte consultado — o Diário consulta uma edição para testar a disponibilidade.

A sonda agendada verifica oito rotas e registra execução e falhas. O painel
interno exige sete dias encerrados consecutivos, com pelo menos vinte sondagens
agendadas por dia. Testes manuais não completam esse histórico. Trata-se de
amostragem sintética, não de prova sobre todas as requisições dos visitantes.

## Verificação e próximos limites

O [relatório da auditoria de 04/09](reviews/AUDIT_2026_09_04.md) registra bugs
reproduzidos, correções, falhas ainda abertas e medições pontuais de produção.
Novos PRs devem manter testes Node/Python, contratos, migrations, typecheck,
build e testes de uso móvel/desktop quando houver mudança visual.

O portal continua em pré-lançamento: nem cobertura integral desde 2021, nem sete
dias sem erro, nem ausência de bugs foram comprovados por uma checagem pontual.
