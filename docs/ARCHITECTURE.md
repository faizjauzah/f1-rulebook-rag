# F1 Rulebook RAG — Architecture

Everything below runs on one machine. The only network hop is container → host, to the local model server.

```
┌─────────────────────────────────────────────────────────────────────┐
│                            USER LAYER                                │
│                                                                       │
│  ┌─────────────────┐              ┌──────────────────────┐          │
│  │   Web Browser   │              │   API Clients        │          │
│  │  (localhost:    │              │   (curl, Postman)    │          │
│  │    8000)        │              │                      │          │
│  └────────┬────────┘              └──────────┬───────────┘          │
│           │                                   │                      │
└───────────┼───────────────────────────────────┼──────────────────────┘
            │                                   │
            └───────────────┬───────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────────┐
│                       FASTAPI APPLICATION                            │
│                        (Docker Container)                            │
│                                                                       │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  GET  /            → Web UI (static, vendored assets)        │   │
│  │  GET  /health      → models + Chroma status                  │   │
│  │  POST /ingest      → PDF ingestion                           │   │
│  │  POST /query       → RAG query                               │   │
│  │  GET  /docs        → OpenAPI docs                            │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                            │                                          │
│  ┌─────────────────────────┴──────────────────────────────────┐     │
│  │                    Service Layer                            │     │
│  │                                                             │     │
│  │  ┌──────────────┐  ┌──────────────┐  ┌─────────────────┐ │     │
│  │  │  Ingestion   │  │  Retrieval   │  │   Generation    │ │     │
│  │  │              │  │              │  │                 │ │     │
│  │  │ • PDF parse  │  │ • direct     │  │ • prompt        │ │     │
│  │  │ • clause     │  │   clause     │  │ • answer        │ │     │
│  │  │   chunking   │  │   lookup     │  │ • source fmt    │ │     │
│  │  │ • embeddings │  │ • vector     │  │ • highlight     │ │     │
│  │  │ • Chroma     │  │   search     │  │                 │ │     │
│  │  │   writes     │  │ • grouping   │  │                 │ │     │
│  │  └──────┬───────┘  └──────┬───────┘  └────────┬────────┘ │     │
│  │         │                 │                   │          │     │
│  │         └────────┬────────┴───────────────────┘          │     │
│  │                  ▼                                       │     │
│  │        app/services/embeddings.py                        │     │
│  │        app/services/local_client.py (key + timeouts)     │     │
│  └──────────────────┼───────────────────────────────────────┘     │
│                     │                                               │
│  ┌──────────────────▼───────────────────────────────────────┐     │
│  │  app/config.py — loads config.yaml, rejects non-local     │     │
│  │  base_url (no silent api.openai.com fallback)             │     │
│  └──────────────────┬───────────────────────────────────────┘     │
└─────────────────────┼───────────────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────┐
│                CHROMADB CONTAINER                   │
│                 (localhost:8001)                    │
│                                                     │
│  Collection: f1-regs  (cosine)                      │
│  • one vector per clause part                       │
│  • metadata: section, article, page, issue, ...     │
│                                                     │
│  Persistent storage: ./data/chroma (bind mount)     │
└─────────────────────────────────────────────────────┘

                      ▲
                      │  OpenAI-compatible HTTP
                      │  (embeddings + chat)
                      │
┌─────────────────────┴───────────────────────────────┐
│              LOCAL MODEL SERVER                     │
│        host.docker.internal:1234/v1                 │
│                                                     │
│  LM Studio (default), or Ollama / llama.cpp / vLLM  │
│  • text-embedding-bge-large-en-v1.5  (embeddings)   │
│  • google/gemma-4-e4b               (chat)          │
│                                                     │
│  No internet. No API keys. No cloud calls.          │
└─────────────────────────────────────────────────────┘


DATA SOURCES:

  PDFs/ (6 files)
  ├── Section A - General Provisions
  ├── Section B - Sporting
  ├── Section C - Technical
  ├── Section D - Financial (F1 Teams)
  ├── Section E - Financial (PU Manufacturers)
  └── Section F - Operational


DATA FLOW:

Ingestion (one-time, ~5–10 min):
  PDFs → pymupdf parser → clause chunks (ARTICLE / C4.1 headings)
       → local embeddings → ChromaDB collection "f1-regs"

Query (real-time):
  Question → local embedding → ChromaDB similarity search
           (+ direct clause lookup when the question names a code)
  → group chunks into clauses → threshold filter
  → prompt local chat model → answer + cited sources


CONFIGURATION:

config.yaml (single, flat — no profiles):
  • embedding.base_url / embedding.model
  • llm.base_url / llm.model / llm.temperature
  • collection: "f1-regs"
  • top_k, similarity_threshold, pdf_directory

Environment variables (.env, all optional):
  • LOCAL_API_KEY (default "lm-studio")
  • TOP_K, SIMILARITY_THRESHOLD, PDF_DIRECTORY
  • MAX_CHUNK_CHARS, CHUNK_OVERLAP_CHARS, MIN_CHUNK_CHARS
  • LOCAL_EMBED_BATCH, EMBED_QUERY_PREFIX, EMBED_DOC_PREFIX
```

## Key design decisions

1. **Single collection** (`f1-regs`, cosine) — one embedding model, so one vector space. Switching the embedding model invalidates the collection and requires re-ingestion.

2. **Local-only guard**: `app/config.py` rejects a `base_url` that isn't loopback, `host.docker.internal`, or a private address. Without it, the OpenAI SDK silently defaults to `api.openai.com` when `base_url` is missing. See [`adr/0001-local-only-inference.md`](adr/0001-local-only-inference.md).

3. **Clause-based chunking**: chunk on `ARTICLE C4:` and `C4.1` boundaries so citations are exact and thresholds behave predictably.

4. **Similarity threshold**: filter low-relevance chunks before generation (default 0.6), renumbering `ref` so citations have no gaps.

5. **Metadata-rich chunks**: section, article, clause title, page, issue and date travel with every vector.

6. **One client factory**: `app/services/local_client.py` owns the fake key and the timeouts (connect 10s, embeddings 120s, LLM 300s), so an unresponsive server fails visibly.

7. **Vendored UI assets**: marked and DOMPurify live in `app/static/vendor/`; the UI has no CDN dependency.

8. **Stateless API**: no session storage, each query independent.
