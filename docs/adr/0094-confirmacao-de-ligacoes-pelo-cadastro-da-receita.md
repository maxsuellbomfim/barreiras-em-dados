# ADR 0094 — Confirmação de ligações pelo cadastro da Receita

## Status

Aceita em 30/09/2026 pelo titular ("alguns podem ter nome fantasia ou razão
social mesmo, ou consórcio ... encontre a melhor forma de verificar, confirmar
e mostrar").

## Contexto

Das citações empenho → contrato pendentes por "favorecido divergente", boa
parte é o mesmo fornecedor escrito de outro jeito: nome fantasia no portal e
razão social no empenho (GSV Mais Alimentos / Comercial Valois), sufixo
LTDA-ME/EPP, "EIRELI" junto do nome fantasia (Comercial Mapel Eireli Atacadão
Vitória). O cadastro oficial do CNPJ (ADR 0093) diz qual razão social e qual
nome fantasia pertencem ao CNPJ do contrato citado.

## Decisão

1. `finance.normalize_company_name` (fixa e testada): maiúsculas, sem acento,
   sem pontuação e sem as formas jurídicas LTDA, LIMITADA, ME, EPP, EIRELI,
   MEI, S.A. e S/S. Nenhuma similaridade aproximada.
2. `finance.confirm_commitment_links_by_registry_name`
   (`commitment-registry-name/1.0.0`) confirma a citação pendente quando o nome
   do credor no empenho, normalizado, é **igual** à razão social, ao nome
   fantasia ou à razão social seguida do nome fantasia do CNPJ de exatamente
   um contrato candidato, no cadastro vigente da Receita.
3. Só confirma. Nome diferente não é prova de outra empresa (grafia, plural,
   abreviação), então nada é rejeitado por esta regra; o que não bate continua
   pendente e não é publicado.
4. A decisão vai para `editorial.editorial_reviews` com o autor
   `automated:commitment-registry-name` e a evidência (campo que bateu, CNPJ,
   mês do cadastro, registro bruto da Receita, contrato). A projeção pública
   rotula essas ligações como `registry_name` ("confirmada pelo cadastro da
   Receita").
5. Roda depois da regra por chave do credor, no mesmo passo do workflow de
   empenhos.

## Consequências

- Na amostra de 30/09, só a igualdade exata resolve fornecedores que somam
  ~1.300 das 4.202 citações pendentes; erros de grafia seguem pendentes.
- Consórcio (natureza 2151/2283) fica identificável pelo cadastro; ligação de
  empenho de consorciado a contrato do consórcio não é feita por esta regra.
