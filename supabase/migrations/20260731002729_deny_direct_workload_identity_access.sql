begin;

-- A allowlist só pode ser lida pela função de autorização. Mesmo que uma role
-- receba acesso à tabela no futuro, esta política restritiva mantém o acesso
-- direto negado.
create policy storage_workload_identities_deny_direct_access
on audit.storage_workload_identities
as restrictive
for all
to public
using (false)
with check (false);

commit;
