begin;

alter role authenticator
  set pgrst.db_schemas = 'public, graphql_public, api';

notify pgrst, 'reload config';

commit;
