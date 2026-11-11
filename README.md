# 🏎️ F1 Rulebook RAG

A Retrieval Augmented Generation (RAG) system for querying the 2026 FIA Formula 1 Regulations — running **entirely on your machine**. Embeddings and answers come from a local OpenAI-compatible server (LM Studio by default); there are no API keys and no cloud calls anywhere in the stack.

## 🎯 Features

- **Fully local inference**: local embeddings + local LLM, UI assets vendored, no network egress at runtime
- **Semantic search**: retrieves relevant regulation clauses using vector similarity
- **Source citations**: every answer cites the clause it came from, with page and issue
- **Direct clause lookup**: asking about `C3.5.2` fetches that clause even if similarity ranking wouldn't
- **REST API**: FastAPI with automatic OpenAPI documentation
- **Simple web UI**: ask questions, read answers with highlighted supporting paragraphs
- **Docker Compose**: API + ChromaDB, nothing else
- **Refuses to phone home**: a non-local `base_url` is a startup error, not a silent fallback

## 🏗 Architecture

```
┌─────────────┐
│   User UI   │
└──────┬──────┘
       │
       ▼
┌─────────────────────────────────────┐
│         FastAPI Service             │
│  ┌──────────┐  ┌─────────────────┐ │
│  │ Ingestion│  │    Retrieval    │ │
│  │ Service  │  │  + Generation   │ │
│  └────┬─────┘  └────────┬────────┘ │
│       │                 │           │
│       ▼                 ▼           │
│  ┌──────────────────────────────┐  │
│  │     ChromaDB Vector Store     │  │
│  └──────────────────────────────┘  │
└───────────────────────┬─────────────┘
                        │  OpenAI-compatible HTTP
                        ▼
              ┌────────────────────┐
              │  LM Studio         │
              │  host.docker.      │
              │  internal:1234     │
              │  • embedding model │
              │  • chat model      │
              └────────────────────┘
```

**Components:**

- **FastAPI**: REST API + static file serving (`app/services/`)
- **ChromaDB**: vector store, cosine space, persisted to `./data/chroma`
- **LM Studio** (or Ollama / llama.cpp / vLLM): serves both the embedding model and the chat model
- **pymupdf**: PDF text extraction, clause-aware chunking

**Data flow:**

1. **Ingestion**: PDFs → pymupdf → clause chunks → embeddings → ChromaDB
2. **Query**: question → embedding → similarity search (+ direct clause lookup) → grouped sources → LLM → answer with citations

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the detailed diagram and [`docs/adr/0001-local-only-inference.md`](docs/adr/0001-local-only-inference.md) for why this is local-only.

## 🚀 Quick Start

### Prerequisites

- Docker + Docker Compose
- [LM Studio](https://lmstudio.ai/) (or any OpenAI-compatible server) on the host

### 1. Load two models in LM Studio

- **Embedding model**: `text-embedding-bge-large-en-v1.5`
- **Chat model**: `google/gemma-4-e4b`

Start the local server on port **1234** (Developer tab → Start Server). The names must match `config.yaml`; if yours differ, edit that file.

### 2. Start the services

```bash
./run.sh start
```

Wait for `Application startup complete` and a healthy ChromaDB.

### 3. Ingest the PDFs (once, ~5–10 min)

```bash
./run.sh ingest
```

### 4. Ask something

Open http://localhost:8000, or:

```bash
./run.sh query "What is the minimum mass of a car?"
```

There is no API key step. `.env` can stay empty.

## 💡 Usage

### Web UI

Type a question and read the answer; citation links jump to the source cards, and the paragraph(s) the answer relies on are highlighted.

Example questions:
- "What is the minimum mass of a car?"
- "How are cost cap penalties determined?"
- "What are the technical specifications for the power unit?"

(The 2026 regulations replace DRS with active aerodynamics, so "What is DRS?" is correctly answered with "no relevant regulations".)

### API (curl)

```bash
# Query
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"question": "What is DRS?"}'

# Health
curl http://localhost:8000/health

# Re-ingest (recreates the collection)
curl -X POST http://localhost:8000/ingest
```

Interactive docs at http://localhost:8000/docs.

## ⚙️ Configuration

`config.yaml` is a single flat config — there are no profiles to switch:

```yaml
embedding:
  base_url: "http://host.docker.internal:1234/v1"
  model: "text-embedding-bge-large-en-v1.5"

llm:
  base_url: "http://host.docker.internal:1234/v1"
  model: "google/gemma-4-e4b"
  temperature: 0.1

collection: "f1-regs"

top_k: 5
similarity_threshold: 0.6
pdf_directory: "PDFs"
```

`base_url` must resolve to loopback, `host.docker.internal`, or a private network address. Anything else is rejected at startup with a clear error — this is a guard against the OpenAI SDK silently defaulting to `api.openai.com`. Pointing at another machine on your LAN works; pointing at a cloud endpoint does not.

Use LM Studio on a non-default port, or a different server entirely (Ollama, llama.cpp, vLLM) by changing `base_url` and the two model names.

### Environment variables (all optional)

| Var | Default | Effect |
|---|---|---|
| `LOCAL_API_KEY` | `lm-studio` | Key sent to the local server (only needed if it has auth enabled) |
| `TOP_K` | `5` | Sources returned per query |
| `SIMILARITY_THRESHOLD` | `0.6` | Min similarity to keep a source |
| `PDF_DIRECTORY` | `PDFs` | PDF input directory |
| `MAX_CHUNK_CHARS` | `500` | Max chars per chunk part |
| `CHUNK_OVERLAP_CHARS` | `120` | Overlap between split parts |
| `MIN_CHUNK_CHARS` | `200` | Sections shorter than this merge into the next |
| `LOCAL_EMBED_BATCH` | `16` | Embedding batch size |
| `EMBED_QUERY_PREFIX` | *(empty)* | Prefix for query embeddings (model-card dependent) |
| `EMBED_DOC_PREFIX` | *(empty)* | Prefix for document embeddings |
| `CHROMA_HOST` / `CHROMA_PORT` | `localhost` / `8001` | ChromaDB address (set to `chroma:8000` in Compose) |
| `EVAL_TIMEOUT` | `180` | Per-question client deadline for `./run.sh eval` (seconds) |

`.env` is mounted into the container; changes need a restart, not a rebuild.

## 📊 Evaluation

```bash
./run.sh eval
```

10 questions (`eval/questions.json`) across all six regulation sections, with easy/medium/hard difficulty. Results go to `eval/results.json`. Ingestion must have completed first, and the chat model must be loaded in LM Studio.

Local generation is slow: on `google/gemma-4-e4b` expect roughly 60–130 seconds per question (about 15 minutes for the suite). The eval client deadline is `EVAL_TIMEOUT` (default `180` seconds) — raise it if your model is slower.

## 📚 API Reference

### POST /query

```json
{ "question": "What is DRS?" }
```

```json
{
  "answer": "DRS (Drag Reduction System) ... [1]",
  "sources": [
    {
      "ref": 1,
      "label": "Article C3.5.2 – Floor Foot",
      "section": "C",
      "section_name": "Technical",
      "doc_title": "FIA 2026 F1 Regulations - Section C [Technical] - Iss 09 - 2026-10-01",
      "article": "C3.5.2",
      "article_title": "Floor Foot",
      "page": 59,
      "issue": "09",
      "date": "2026-10-01",
      "similarity": 0.83,
      "match": "semantic",
      "cited": true,
      "truncated": false,
      "paragraphs": [
        { "text": "C3.5.2.1 ...", "highlight": true }
      ]
    }
  ],
  "metadata": {
    "model": "google/gemma-4-e4b",
    "chunks_retrieved": 15,
    "chunks_used": 5,
    "response_time_ms": 4210
  }
}
```

`match` is `semantic` or `article_number` (direct clause lookup). `cited` is true when the answer cites that `ref`. Full source text lives in `paragraphs`; `highlight` marks the paragraph(s) backing the answer.

### POST /ingest

Recreates the collection and re-embeds every PDF in `PDF_DIRECTORY`.

```json
{ "status": "success", "message": "Successfully ingested 6 PDFs", "chunks_created": 342, "collection": "f1-regs" }
```

### GET /health

```json
{
  "status": "healthy",
  "embedding_model": "text-embedding-bge-large-en-v1.5",
  "llm_model": "google/gemma-4-e4b",
  "collection": "f1-regs",
  "chroma_connected": true
}
```

## 🧪 Smoke Test

```bash
./smoke_test.sh
```

Five HTTP assertions covering health and a few query shapes, including off-topic questions that should be declined.

## 📁 Project Structure

```
/
├── app/
│   ├── main.py                 # FastAPI application + startup logging
│   ├── config.py               # config.yaml loader + local-endpoint guard
│   ├── api/
│   │   ├── routes.py           # /health, /ingest, /query
│   │   └── models.py           # Pydantic response models
│   ├── services/
│   │   ├── ingestion.py        # PDF parsing, clause chunking, Chroma writes
│   │   ├── embeddings.py       # batched local embeddings
│   │   ├── local_client.py     # OpenAI-compatible client (key + timeouts)
│   │   ├── retrieval.py        # direct lookup + vector search + grouping
│   │   └── generation.py       # prompt, answer, source formatting
│   └── static/
│       ├── index.html          # Web UI
│       └── vendor/             # marked + DOMPurify (no CDN)
├── eval/
│   ├── questions.json
│   └── run_eval.py
├── docs/
│   ├── ARCHITECTURE.md
│   └── adr/0001-local-only-inference.md
├── PDFs/                       # F1 regulation PDFs
├── data/chroma/                # ChromaDB persistence (gitignored)
├── config.yaml
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
└── run.sh
```

## 🛠 Technology Stack

- **FastAPI** + **Pydantic**: API and validation
- **ChromaDB 1.5.9**: vector store (cosine)
- **LM Studio**: local embedding + chat server (OpenAI-compatible)
- **pymupdf**: PDF parsing
- **Docker Compose**: API + ChromaDB

## 📝 Future Enhancements

- [ ] Conversation history (multi-turn queries)
- [ ] Hybrid search (keyword + semantic)
- [ ] Query rewriting for better retrieval
- [ ] Streaming responses
- [ ] Advanced eval metrics (RAGAS, faithfulness)
- [ ] CI pipeline

## 📄 License

MIT
