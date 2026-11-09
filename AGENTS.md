# Agent Instructions

## Commands

**Must use `./run.sh` for all operations:**
```bash
./run.sh start      # Start services (Docker)
./run.sh ingest     # Ingest PDFs (5-20 min, run once per collection)
./run.sh query "Q"  # Query via curl
./run.sh health     # Health check
./run.sh eval       # Run eval inside container
./run.sh clean      # Delete data/ and containers
```

**Do not** run `uvicorn` directly or `python` commands outside Docker. The app only runs in containers.

**Testing**: Use `./smoke_test.sh` for quick validation, not manual curl chains.

**Eval**: Must run inside container: `docker-compose exec api python eval/run_eval.py` (also available as `./run.sh eval`). `eval/` is copied into the image at build time, so rebuild after editing eval files.

## Profile switching

Change `config.yaml` line 1: `profile: "cloud"` or `profile: "local"` (or override with the `PROFILE` env var).

**After profile change**: Must `./run.sh clean` then restart and re-ingest. Collections are profile-specific (`f1-regs-gemini` vs `f1-regs-local`). Switching profiles without re-ingesting will query the wrong collection.

## Ingestion timing

- Cloud (Gemini): ~20 minutes due to 0.7s sleep between embeddings (`app/services/ingestion.py`, ~line 250)
- Local: ~5 minutes (requires LM Studio running on port 1234)

Rate limit handling in `app/services/ingestion.py` (~lines 255-270): retries 5 times with exponential backoff (45s × attempt) on 429 errors.

Embeddings are generated **before** the existing collection is deleted, so a failed run does not wipe prior data. Chunks are added in batches sized to ChromaDB's max batch size.

## ChromaDB connection

- From host: `localhost:8001`
- From API container: `chroma:8000` (docker-compose networking)
- Persistence: `./data/chroma` (host) ↔ `/data` (chroma container) and `/data/chroma` (api container)
- Version: ChromaDB `1.5.9` (image `chromadb/chroma:1.5.9`); collection space is **cosine** (`hnsw:space: cosine`), so similarity = `1 - distance`.

API connects to ChromaDB using `CHROMA_HOST` and `CHROMA_PORT` env vars set in `docker-compose.yml`.

## PDF chunking

Chunking is **clause-based**, not article-based and not fixed-size. Regexes in `app/services/ingestion.py`:

- `ARTICLE_RE = ^ARTICLE\s+([A-F]\d+):\s+(.+)$`  (e.g. `ARTICLE C1: GENERAL PRINCIPLES`)
- `CLAUSE_RE = ^([A-F]\d+(?:\.\d+)+)\s+(\S.*)$`  (e.g. `C3.5.2 Floor Foot`)

Pipeline: parse PDF → drop TOC/noise pages → walk articles/clauses → merge sections shorter than `MIN_CHARS` into the next → split oversized clauses into ~`MAX_CHARS`-char parts with `OVERLAP`-char overlap. The `chunk_size: 512` in config is misleading and **not enforced**; real chunk size is controlled by env vars (see Tunables).

Table-of-contents and running headers/footers/noise lines are filtered during parsing. Ligature-damaged words (`specifc`, `efect`, …) are repaired in `clean_line()`.

Filename pattern for metadata extraction: `Section ([A-F]) \[([^\]]+)\].*Iss (\d+).*(\d{4}-\d{2}-\d{2})` → `section`, `section_name`, `issue`, `date`, `doc_title`.

Metadata stored per chunk: `section`, `section_name`, `issue`, `date`, `doc_title`, `article` (clause code), `article_title`, `parent_article`, `parent_title`, `page`, `part`.

## Environment setup

`.env` is mounted into the container (line 24 in `docker-compose.yml`). Changes to `.env` require container restart, not rebuild.

`GOOGLE_API_KEY` required for cloud profile. No key needed for local profile if using LM Studio.

### Tunables (env vars, all optional)

| Var | Default | Effect |
|---|---|---|
| `PROFILE` | `config.yaml` profile | Override active profile |
| `TOP_K` | `5` | Sources returned per query |
| `SIMILARITY_THRESHOLD` | `0.6` | Min similarity to keep a source |
| `PDF_DIRECTORY` | `PDFs` | PDF input dir |
| `CHROMA_PERSIST_DIR` | `/data/chroma` | (shared config) |
| `MAX_CHUNK_CHARS` | `1000` | Max chars per chunk part |
| `CHUNK_OVERLAP_CHARS` | `120` | Overlap between split parts |
| `MIN_CHUNK_CHARS` | `200` | Merge smaller sections into next |
| `LOCAL_EMBED_BATCH` | `16` | Local embedding batch size |
| `EMBED_QUERY_PREFIX` | `` | Prefix for local query embeddings (model-card dependent) |
| `EMBED_DOC_PREFIX` | `` | Prefix for local document embeddings |

## Local mode quirks

- Requires LM Studio on port 1234 with OpenAI-compatible endpoint
- Uses `host.docker.internal:1234` from within Docker
- LM Studio must have the embedding model loaded (e.g., `text-embedding-bge-large-en-v1.5`)
- LM Studio must also have an LLM loaded for query generation
- No downloads—uses whatever models LM Studio has loaded via its API
- Local embeddings go through the **OpenAI-compatible** client (not `sentence-transformers`, even though the package is installed). Set `EMBED_QUERY_PREFIX`/`EMBED_DOC_PREFIX` per your embedding model's card (nomic, EmbeddingGemma, bge, …).
- Cloud embeddings/LLM use the `google-genai` SDK (`genai.Client`), not `google-generativeai`.

## Architecture

FastAPI app in one container, ChromaDB in another. No direct Python execution—everything through Docker.

Entry point: `app/main.py` → includes `app/api/routes.py` → calls services in `app/services/`

Static UI served from `app/static/index.html` at root `/`. The UI consumes the new source schema (`paragraphs`, `highlight`, `cited`, `truncated`, `match`, `ref`).

### Retrieval pipeline (`app/services/retrieval.py`)

1. **Direct article lookup**: if the question contains an article/clause code (e.g. `C3.5.2`, or `Article C3`), fetch those clauses directly (`match: "article_number"`, similarity `1.0`). Capped at `MAX_DIRECT_SOURCES = 2`.
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

Must query after ingestion completes, else "collection not found" error.

## Agent skills

### Issue tracker

Issues and specs live as GitHub issues in `faizjauzah/f1-rulebook-rag`, managed via the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

Default canonical triage labels (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`) plus `bug`/`enhancement` categories. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: one `GLOSSARY.md` + `docs/adr/` at repo root (created lazily). See `docs/agents/domain.md`.
