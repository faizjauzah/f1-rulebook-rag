# F1 Rulebook RAG - Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                            USER LAYER                                │
│                                                                       │
│  ┌─────────────────┐              ┌──────────────────────┐          │
│  │   Web Browser   │              │   API Clients        │          │
│  │   (localhost:   │              │   (curl, Postman)    │          │
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
│  │                     API Endpoints                             │   │
│  │  • GET  /              → Web UI                              │   │
│  │  • GET  /health        → Service status                      │   │
│  │  • POST /ingest        → PDF ingestion                       │   │
│  │  • POST /query         → RAG query                           │   │
│  │  • GET  /docs          → OpenAPI docs                        │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                            │                                          │
│  ┌─────────────────────────┴──────────────────────────────────┐     │
│  │                    Service Layer                            │     │
│  │                                                             │     │
│  │  ┌──────────────┐  ┌──────────────┐  ┌─────────────────┐ │     │
│  │  │  Ingestion   │  │  Retrieval   │  │   Generation    │ │     │
│  │  │              │  │              │  │                 │ │     │
│  │  │ • PDF parse  │  │ • Vector     │  │ • LLM prompt   │ │     │
│  │  │ • Chunk by   │  │   search     │  │ • Answer gen   │ │     │
│  │  │   article    │  │ • Similarity │  │ • Source fmt   │ │     │
│  │  │ • Embed      │  │   threshold  │  │                 │ │     │
│  │  │ • Store      │  │              │  │                 │ │     │
│  │  └──────┬───────┘  └──────┬───────┘  └────────┬────────┘ │     │
│  └─────────┼─────────────────┼───────────────────┼──────────┘     │
│            │                 │                   │                  │
└────────────┼─────────────────┼───────────────────┼──────────────────┘
             │                 │                   │
             │                 │                   │
             ▼                 ▼                   │
┌─────────────────────────────────────────────┐   │
│         CHROMADB CONTAINER                  │   │
│        (localhost:8001)                     │   │
│                                             │   │
│  ┌────────────────────────────────────┐    │   │
│  │  Collections:                      │    │   │
│  │  • f1-regs-gemini  (768-dim)      │    │   │
│  │  • f1-regs-local   (1024-dim)     │    │   │
│  └────────────────────────────────────┘    │   │
│                                             │   │
│  ┌────────────────────────────────────┐    │   │
│  │  Persistent Storage:               │    │   │
│  │  ./data/chroma/                    │    │   │
│  │  (bind mount)                      │    │   │
│  └────────────────────────────────────┘    │   │
└─────────────────────────────────────────────┘   │
                                                  │
                        ┌─────────────────────────┴────────────────────┐
                        │                                              │
                        ▼                                              ▼
┌──────────────────────────────────────┐    ┌──────────────────────────────────┐
│    CLOUD PROVIDERS (Profile: cloud)  │    │  LOCAL MODELS (Profile: local)   │
│                                      │    │                                  │
│  ┌─────────────────────────────┐    │    │  ┌────────────────────────────┐ │
│  │  Google Gemini API          │    │    │  │  LM Studio                 │ │
│  │  • text-embedding-004       │    │    │  │  (localhost:1234)          │ │
│  │  • gemini-1.5-flash         │    │    │  │  • Local LLM               │ │
│  │  Free tier: 15 RPM          │    │    │  │  • OpenAI-compatible API   │ │
│  └─────────────────────────────┘    │    │  └────────────────────────────┘ │
│                                      │    │                                  │
└──────────────────────────────────────┘    │  ┌────────────────────────────┐ │
                                            │  │  sentence-transformers     │ │
                                            │  │  • bge-large-en-v1.5       │ │
                                            │  │  • Local embeddings        │ │
                                            │  └────────────────────────────┘ │
                                            └──────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│                         DATA SOURCES                                 │
│                                                                       │
│  PDFs/ (6 files)                                                     │
│  ├── Section A - General Provisions                                 │
│  ├── Section B - Sporting                                           │
│  ├── Section C - Technical                                          │
│  ├── Section D - Financial (F1 Teams)                               │
│  ├── Section E - Financial (PU Manufacturers)                       │
│  └── Section F - Operational                                        │
└─────────────────────────────────────────────────────────────────────┘


DATA FLOW:

Ingestion (one-time):
  PDFs → pymupdf parser → Semantic chunks (by article) → 
  Embeddings (Gemini/local) → ChromaDB collection

Query (real-time):
  User question → Embedding → ChromaDB similarity search → 
  Top-K chunks (filtered by threshold) → LLM prompt → 
  Answer + Sources → User


CONFIGURATION:

Profile-based switching (config.yaml):
  • cloud:  Gemini embeddings + Gemini LLM
  • local:  bge-large embeddings + LM Studio LLM

Environment variables (.env):
  • GOOGLE_API_KEY
  • PROFILE (override)
  • TOP_K, SIMILARITY_THRESHOLD (tuning)
```

## Key Design Decisions

1. **Two Collections**: Separate collections for different embedding dimensions (Gemini 768-dim vs bge-large 1024-dim)

2. **Semantic Chunking**: Chunk by article boundaries to preserve regulation structure and enable clean citations

3. **Profile-Based Config**: Single config switch between cloud/local modes, no code changes needed

4. **Similarity Threshold**: Filter out low-relevance chunks before LLM generation (default 0.6)

5. **Metadata-Rich**: Store section, article, page, title with each chunk for detailed citations

6. **Docker Compose**: Multi-container architecture teaching service orchestration and networking

7. **Bind Mount**: ChromaDB data visible in project for inspection and backup

8. **Stateless API**: No session storage, each query is independent (ready for horizontal scaling)
