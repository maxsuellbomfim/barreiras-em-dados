# Etapa 3 — projeção pública de receitas

## Entrega

- migration append-only cria `api.get_public_revenues`;
- a função retorna somente a versão vigente de cada registro por órgão e chave
  externa;
- cada linha pública carrega valor, ano, data, órgão, URL da fonte, hash do
  artefato e horário de coleta;
- a página `/financas` distingue indisponibilidade, ausência de dados e dados
  disponíveis;
- a home passou a apontar para Finanças públicas, sem prometer totais antes da
  reconciliação.

## Controles

- acesso anônimo é somente à função; tabelas internas continuam fora do portal;
- `page_size` é limitado entre 1 e 200;
- ano fiscal inválido falha explicitamente;
- valores são recebidos pelo frontend como texto decimal e formatados sem
  `float` ou soma client-side;
- registros superseded não são projetados como vigentes;
- ausência de receita não é exibida como zero.

## Limitação deliberada

A projeção está preparada, mas não cria registros em `finance.revenues`. A
persistência depende da confirmação dos campos reais do portal, estornos,
retificações, classificações e chaves estáveis. Empenho, liquidação, pagamento
e receita continuam sendo estágios separados.

## Próxima menor fatia

Persistir uma janela pequena da receita bruta com `origin_raw_record_id`,
idempotência e versão, executar reconciliação de amostra e só então preencher o
primeiro total público por período.

