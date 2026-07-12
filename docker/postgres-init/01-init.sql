-- Runs once, on first container start, against POSTGRES_DB (verdantis).
-- Creates the pgvector extension there and provisions a second database +
-- extension for the test suite (tests/conftest.py points at verdantis_test).

CREATE EXTENSION IF NOT EXISTS vector;

CREATE DATABASE verdantis_test;

\connect verdantis_test
CREATE EXTENSION IF NOT EXISTS vector;
