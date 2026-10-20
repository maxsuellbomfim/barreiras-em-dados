begin;

-- O PostgreSQL limita repetição em expressão regular a 255; caminho vira
-- "/ sem espaços" com limite de tamanho à parte.
alter table editorial.public_contestations
  drop constraint public_contestations_target_path_check;
alter table editorial.public_contestations
  add constraint public_contestations_target_path_check
  check (target_path ~ '^/\S*$' and length(target_path) <= 300);

do $patch$
declare
  definition text := pg_get_functiondef('api.submit_public_contestation(text,text,text,text)'::regprocedure);
  patched text;
begin
  patched := replace(
    definition,
    $x$if clean_path !~ '^/[^\s]{0,299}$' then$x$,
    $x$if clean_path !~ '^/\S*$' or length(clean_path) > 300 then$x$
  );
  if patched = definition then
    raise exception 'validação do caminho não encontrada';
  end if;
  execute patched;
end;
$patch$;

notify pgrst, 'reload schema';

commit;
