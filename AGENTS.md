# Agent Instructions

## Commands

**Must use `./run.sh` for all operations:**
```bash
./run.sh start      # Start services (Docker)
./run.sh ingest     # Ingest PDFs (~5-10 min, run once per collection)
./run.sh query "Q"  # Query via curl
./run.sh health     # Health check
./run.sh eval       # Run eval inside container
./run.sh clean      # Delete data/ and containers
```

**Do not** run `uvicorn` directly or `python` commands outside Docker. The app only runs in containers.

**Testing**: Use `./smoke_test.sh` for quick validation, not manual curl chains.

**Eval**: Must run inside container: `docker-compose exec api python eval/run_eval.py` (also available as `./run.sh eval`). `eval/` is copied into the image at build time, so rebuild after editing eval files.

## Local-only, by design

There is no cloud provider and no profile switch. Embeddings and generation both go to an OpenAI-compatible server on the host (LM Studio by default), configured in `config.yaml`.

- `app/config.py` validates both `base_url`s at import: they must be loopback, `host.docker.internal`, or a private address, otherwise startup raises. This exists because the OpenAI SDK silently defaults to `api.openai.com` when `base_url` is missing — never remove this guard.
- Do not add a cloud provider back without an ADR superseding `docs/adr/0001-local-only-inference.md`.
- The UI vendors marked + DOMPurify in `app/static/vendor/`; keep it that way (no CDN).

## Ingestion timing

- Local: ~5–10 minutes for all six PDFs (~8.5 min measured for 6,080 chunks; embedding model must be loaded; batch size `LOCAL_EMBED_BATCH`, default 16).

Embeddings are generated **before** the existing collection is deleted, so a failed run does not wipe prior data. Chunks are added in batches sized to ChromaDB's max batch size.

## ChromaDB connection

- From host: `localhost:8001`
- From API container: `chroma:8000` (docker-compose networking)
- Persistence: `./data/chroma` (host) ↔ `/data` (chroma container) and `/data/chroma` (api container)
- Version: ChromaDB `1.5.9` (image `chromadb/chroma:1.5.9`); collection space is **cosine** (`hnsw:space: cosine`), so similarity = `1 - distance`.
- Collection name: `f1-regs` (`config.yaml` → `collection`). One collection only; changing the embedding model invalidates it and requires re-ingestion.

API connects to ChromaDB using `CHROMA_HOST` and `CHROMA_PORT` env vars set in `docker-compose.yml`.

## PDF chunking

Chunking is **clause-based**, not article-based and not fixed-size. Regexes in `app/services/ingestion.py`:

- `ARTICLE_RE = ^ARTICLE\s+([A-F]\d+):\s+(.+)$`  (e.g. `ARTICLE C1: GENERAL PRINCIPLES`)
- `CLAUSE_RE = ^([A-F]\d+(?:\.\d+)+)\s+(\S.*)$`  (e.g. `C3.5.2 Floor Foot`)

Pipeline: parse PDF → drop TOC/noise pages → walk articles/clauses → merge sections shorter than `MIN_CHARS` into the next → split oversized clauses into ~`MAX_CHARS`-char parts with `OVERLAP`-char overlap. Chunk size is controlled by env vars (see Tunables), not by config.

Table-of-contents and running headers/footers/noise lines are filtered during parsing. Ligature-damaged words (`specifc`, `efect`, …) are repaired in `clean_line()`.

Filename pattern for metadata extraction: `Section ([A-F]) \[([^\]]+)\].*Iss (\d+).*(\d{4}-\d{2}-\d{2})` → `section`, `section_name`, `issue`, `date`, `doc_title`.

Metadata stored per chunk: `section`, `section_name`, `issue`, `date`, `doc_title`, `article` (clause code), `article_title`, `parent_article`, `parent_title`, `page`, `part`.

## Environment setup

`.env` is mounted into the container (line 24 in `docker-compose.yml`). Changes to `.env` require container restart, not rebuild. Nothing in `.env` is required: no API keys exist.

### Tunables (env vars, all optional)

| Var | Default | Effect |
|---|---|---|
| `LOCAL_API_KEY` | `lm-studio` | Key sent to the local server |
| `TOP_K` | `5` | Sources returned per query |
| `SIMILARITY_THRESHOLD` | `0.6` | Min similarity to keep a source |
| `PDF_DIRECTORY` | `PDFs` | PDF input dir |
| `MAX_CHUNK_CHARS` | `500` | Max chars per chunk part |
| `CHUNK_OVERLAP_CHARS` | `120` | Overlap between split parts |
| `MIN_CHUNK_CHARS` | `200` | Merge smaller sections into next |
| `LOCAL_EMBED_BATCH` | `16` | Embedding batch size |
| `EMBED_QUERY_PREFIX` | `` | Prefix for query embeddings (model-card dependent) |
| `EMBED_DOC_PREFIX` | `` | Prefix for document embeddings |
| `EVAL_TIMEOUT` | `180` | Per-question deadline for `eval/run_eval.py` (seconds) |

## Local inference quirks

- Requires an OpenAI-compatible server; the defaults assume LM Studio on port 1234.
- From Docker the server is `host.docker.internal:1234/v1`; `docker-compose.yml` maps that name on Linux via `extra_hosts`.
- The same server must expose **both** the embedding model and the chat model (two model names, one base URL).
- Model names in `config.yaml` must exist in the server; LM Studio can auto-load on first request if enabled, otherwise load them by hand.
- Embeddings go through the **OpenAI-compatible client** (`app/services/embeddings.py`), not `sentence-transformers`. Set `EMBED_QUERY_PREFIX`/`EMBED_DOC_PREFIX` per your embedding model's card (nomic, EmbeddingGemma, bge, …).
- Client timeouts live in `app/services/local_client.py` (connect 10s, embeddings 120s, LLM 300s). A hung server should fail, not hang the request.

## Architecture

FastAPI app in one container, ChromaDB in another. No direct Python execution—everything through Docker.

Entry point: `app/main.py` → includes `app/api/routes.py` → calls services in `app/services/`

Static UI served from `app/static/index.html` at root `/`. The UI consumes the source schema (`paragraphs`, `highlight`, `cited`, `truncated`, `match`, `ref`).

`/health` reports `embedding_model`, `llm_model`, `collection`, `chroma_connected` (no profile).

### Retrieval pipeline (`app/services/retrieval.py`)

1. **Direct clause lookup**: if the question contains an article/clause code (e.g. `C3.5.2`, or `Article C3`), fetch those clauses directly (`match: "article_number"`, similarity `1.0`). Capped at `MAX_DIRECT_SOURCES = 2`.
2. **Semantic search**: embed the question (with `is_query=True`) and query `top_k * 3` chunks (candidate multiplier).
3. **TOC filtering**: drop chunks that look like table-of-contents text before ranking.
4. **Grouping**: chunks collapse into one source per clause (keyed by `doc_title` + `article` + `page`; page is part of the key so TOC entries never merge with bodies).
5. **Expansion**: fetch all parts of each clause so a source is never truncated mid-clause (capped at `MAX_PARTS_PER_SOURCE = 4`).
6. **Threshold filter**: `filter_by_threshold()` drops sources below `similarity_threshold` and renumbers `ref` with no gaps.

### Generation (`app/services/generation.py`)

- Prompt instructs the LLM to cite sources as `[1]`, `[2]`, … matching the `ref` numbers.
- `format_sources(chunks, answer, question)` builds the API source list, including a heuristic highlight: paragraphs are scored by overlap with question/answer tokens (numeric codes weighted 3×, normalized by `sqrt(paragraph size)`); the best paragraph(s) get `highlight: true`. A source with no strong match gets no highlight.
- Each source is marked `cited: true` if its `ref` appears in the answer's citations.

### Source schema (API `Source` model)

`ref`, `label`, `section`, `section_name`, `doc_title`, `article`, `article_title`, `page`, `issue`, `date`, `similarity`, `match`, `cited`, `truncated`, `paragraphs: [{text, highlight}]`. (No top-level `text`; full text lives in `paragraphs`.)

## Eval

10 questions in `eval/questions.json` with difficulty levels (easy/medium/hard). Results write to `eval/results.json`.

Must query after ingestion completes, else "collection not found" error. The chat model must be loaded in the local server, or every question fails.

Local generation is slow: ~60–130 s per question on `google/gemma-4-e4b` (~15 min for the suite). `eval/run_eval.py` waits `EVAL_TIMEOUT` seconds per question (default 180). If a client deadline expires while the server is still generating, the request keeps running and the next one queues behind it — timeouts cascade, so keep the deadline above real latency.

## Agent skills

### Issue tracker

Issues and specs live as GitHub issues in `faizjauzah/f1-rulebook-rag`, managed via the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

Default canonical triage labels (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`) plus `bug`/`enhancement` categories. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: [`GLOSSARY.md`](GLOSSARY.md) at the repo root and ADRs in [`docs/adr/`](docs/adr/). See `docs/agents/domain.md`.
