# ADR 0056: diagnóstico mensal de integridade financeira

- Status: aceito
- Data: 2026-08-11

## Contexto

O painel administrativo já mostrava documentos preservados e fechamentos
mensais. Ainda faltava responder, antes de interpretar qualquer total, se a
competência tinha receita e despesa comparáveis, se existiam versões
duplicadas e se cada registro possuía vínculo verificável com a resposta bruta
e o PDF oficial.

## Decisão

A RPC interna `api.get_admin_finance_integrity` produz um diagnóstico por órgão
e mês desde 2021. Os estados são determinísticos:

- `ready`: existe exatamente um documento de receita e um de despesa, sem
  vínculo documental pendente;
- `needs_data`: falta ao menos uma das duas famílias documentais;
- `needs_review`: existe mais de um documento da mesma família e competência;
- `blocked`: ao menos um registro não aponta para origem bruta e PDF exatos.

O diagnóstico também separa vínculos diretos, reconciliados por versão
append-only e pendentes. A consulta classifica pares distintos de registro e
PDF antes de agregá-los, evitando repetir a validação para cada linha
financeira. A RPC exige revisor ativo, não expõe identificadores internos e
revoga acesso anônimo.

## Consequências

- um mês ausente continua sendo exibido como falta de cobertura, nunca como
  valor zero;
- um vínculo reconciliado informa uma correção de proveniência, não uma
  alteração do valor contábil;
- competências duplicadas ou sem origem exata permanecem explícitas no admin;
- IA não participa dos estados, contagens ou decisões de publicação;
- a próxima entrega pública pode usar o mesmo estado para explicar por que um
  total aparece, está incompleto ou foi temporariamente ocultado.
