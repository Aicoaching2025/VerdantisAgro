FROM pgvector/pgvector:pg16

# Postgres's entrypoint runs every *.sql/*.sh in here, once, only when the
# data directory is empty (i.e. on the very first boot against a fresh
# volume) -- exactly the "create the extension" step this app needs and
# nothing more.
COPY init.sql /docker-entrypoint-initdb.d/01-init.sql
