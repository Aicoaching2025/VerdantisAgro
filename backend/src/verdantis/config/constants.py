"""Project-wide constants that must stay identical across models and migrations.

EMBEDDING_DIM is the pgvector column width for Company.embedding. It MUST match
the output dimension of the embedding model you standardize on, and it MUST be
set correctly BEFORE running migration 0001 — changing it later requires a new
migration and a re-embed of every stored vector.

Common dimensions:
    Google  text-embedding-004        -> 768
    OpenAI  text-embedding-3-small    -> 1536
    OpenAI  text-embedding-3-large    -> 3072
    Cohere  embed-v4 (default)        -> 1024

Default below is 1024; override to your model before the first migration.
"""

EMBEDDING_DIM: int = 1024
