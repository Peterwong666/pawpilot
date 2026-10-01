# ADR 001: pgvector instead of Milvus

## Context

PawPilot needs a vector store for RAG retrieval. The natural options are:

1. Milvus / Zilliz
2. pgvector (PostgreSQL extension)
3. Chroma / Qdrant

## Decision

Use **pgvector**.

## Rationale

- Single container. The dev stack is just one Postgres image. Milvus requires etcd, MinIO, and
  multiple services, increasing local resource use and operational complexity.
- Unified metadata. All chunk metadata and keyword indexes live in one database, simplifying
  hybrid retrieval and backups.
- Sufficient scale. The PawPilot corpus is expected to be in the low tens of thousands of chunks.
  pgvector with ivfflat handles this comfortably.
- Skill alignment. FDE interviews value "right-size architecture" decisions; choosing a lighter
  option over a trendy but overkill vector database demonstrates engineering judgment.

## Consequences

- We lose some advanced vector features (GPU index building, complex partitioning) but gain
  simplicity.
- ivfflat index needs occasional rebuilding as the corpus grows.
