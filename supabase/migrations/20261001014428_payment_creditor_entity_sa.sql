begin;

set local statement_timeout = '300s';

-- Correção antes da publicação: sem acento, o sobrenome "SÁ" virava o marcador
-- "SA" e expunha pessoa física ("... DE SÁ TELES"). S/A segue reconhecida por
-- "S/A" e "S.A."; nome que só termina em "SA" vai para o agregado sem nome.

-- Nome publicável: forma jurídica, ente público ou MEI (CNPJ-base no nome),
-- e nenhum CPF. Pessoa física sem marca fica no agregado.
create or replace function finance.payment_creditor_is_entity_v1(p_name text)
returns boolean
language sql
immutable
parallel safe
set search_path = ''
as $$
  select coalesce(
    n !~ '(^|[^0-9])[0-9]{3}\.?[0-9]{3}\.?[0-9]{3}-?[0-9]{2}([^0-9]|$)'
    and (
      n ~ '^[0-9]{2}\.[0-9]{3}\.[0-9]{3} '
      or n ~ ('\m(LTDA|LIMITADA|EIRELL?I|EPP|ME|MEI|CIA|SPE|S\s*/\s*[AS]|S\.\s*A'
        || '|COMPANHIA|EMPRESA|SOCIEDADE|ASSOCIACAO|FUNDACAO|INSTITUTO|CONSORCIO'
        || '|COOPERATIVA|SINDICATO|LIGA|MOVIMENTO|LAR|LOJA|IGREJA|PAROQUIA|DIOCESANA'
        || '|CARITAS|APAE|ORGANIZACAO|GRUPO|ESCRITORIO|ADVOCACIA|ADVOGADOS|ASSOCIADOS'
        || '|PREFEITURA|MUNICIPIO|MUNICIPAL|FUNDO|FOPAG|FOLHA DE PAGAMENTO'
        || '|MINISTERIO|SECRETARIA|GOVERNO|ESTADO|UNIAO|FEDERAL|AUTARQUIA|AGENCIA'
        || '|TRIBUNAL|CONSELHO|INSS|RECEITA|DETRAN|BANCO|CAIXA|CORREIOS'
        || '|HOSPITAL|CLINICA|LABORATORIO|FARMACIA|DROGARIA|POSTO|COMERCIO|COMERCIAL'
        || '|SERVICOS|SOLUTIONS|INDUSTRIA|DISTRIBUIDORA|CONSTRUTORA|ENGENHARIA'
        || '|ACADEMIA|ESCOLA|COLEGIO|UNIVERSIDADE|FACULDADE|EDITORA|PRODUCOES'
        || '|EVENTOS|TRANSPORTES?|LOCADORA|TELECOM|ENERGIA|SANEAMENTO)\M')
    ),
    false)
  from (
    select translate(upper(coalesce(p_name, '')),
      'ÁÀÂÃÄÉÈÊËÍÌÎÏÓÒÔÕÖÚÙÛÜÇ', 'AAAAAEEEEIIIIOOOOOUUUUC') as n
  ) as creditor
$$;

select finance.refresh_payment_recipients();

commit;
