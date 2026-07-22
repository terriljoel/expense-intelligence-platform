# SQL migration copies

Alembic revisions under `apps/api/alembic/versions/` are the executable source
of truth for schema changes.

The SQL files in this directory are retained as readable PostgreSQL references.
Only `001_initial_schema.sql` is used directly when creating a new database,
after which the database is stamped at the Alembic baseline. Do not execute the
later SQL files in addition to Alembic, because that would apply the same change
twice.
