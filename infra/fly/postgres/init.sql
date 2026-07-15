-- Runs once, on first container start, against POSTGRES_DB (verdantis).
-- Production-only counterpart to docker/postgres-init/01-init.sql: creates
-- the vector extension, but deliberately skips that script's verdantis_test
-- database -- that's a dev/CI-only concern, not something prod needs.

CREATE EXTENSION IF NOT EXISTS vector;
