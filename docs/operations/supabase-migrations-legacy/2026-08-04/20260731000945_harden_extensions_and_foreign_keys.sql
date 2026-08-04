begin;

-- Extensões não devem compartilhar o schema público destinado à API.
create schema if not exists extensions;
alter extension pg_trgm set schema extensions;

-- Toda chave estrangeira recebe um índice cujo prefixo cobre as colunas da
-- restrição. Isso mantém exclusões/validações referenciais e reconciliações
-- previsíveis à medida que o acervo histórico cresce.
do $migration$
declare
  foreign_key record;
begin
  for foreign_key in
    select
      namespace.nspname as schema_name,
      relation.relname as table_name,
      left(
        regexp_replace(constraint_record.conname, '_fkey$', '_idx'),
        63
      ) as index_name,
      string_agg(
        quote_ident(attribute.attname),
        ', '
        order by key_column.ordinality
      ) as indexed_columns
    from pg_catalog.pg_constraint as constraint_record
    join pg_catalog.pg_class as relation
      on relation.oid = constraint_record.conrelid
    join pg_catalog.pg_namespace as namespace
      on namespace.oid = relation.relnamespace
    cross join lateral unnest(constraint_record.conkey)
      with ordinality as key_column(attnum, ordinality)
    join pg_catalog.pg_attribute as attribute
      on attribute.attrelid = relation.oid
      and attribute.attnum = key_column.attnum
    where constraint_record.contype = 'f'
      and namespace.nspname in (
        'source',
        'raw',
        'org',
        'hr',
        'procurement',
        'finance',
        'evidence',
        'analysis',
        'editorial',
        'audit'
      )
      and not exists (
        select 1
        from pg_catalog.pg_index as index_record
        where index_record.indrelid = constraint_record.conrelid
          and index_record.indisvalid
          and index_record.indisready
          and index_record.indpred is null
          and (
            index_record.indkey::smallint[]
          )[0:cardinality(constraint_record.conkey) - 1]
            = constraint_record.conkey
      )
    group by
      namespace.nspname,
      relation.relname,
      constraint_record.conname
    order by
      namespace.nspname,
      relation.relname,
      constraint_record.conname
  loop
    execute format(
      'create index if not exists %I on %I.%I (%s)',
      foreign_key.index_name,
      foreign_key.schema_name,
      foreign_key.table_name,
      foreign_key.indexed_columns
    );
  end loop;
end
$migration$;

commit;
