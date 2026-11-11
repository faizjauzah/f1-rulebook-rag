# Troubleshooting Guide

Everything runs locally, so most failures are one of three things: Docker, ChromaDB, or the model server on the host.

### 1. Docker services won't start

- Check ports 8000 (API) and 8001 (ChromaDB) are free:
  ```bash
  lsof -i :8000
  lsof -i :8001
  ```
- Docker needs ~4GB RAM for the containers (the models themselves run outside Docker).
- View logs: `docker-compose logs`

### 2. API refuses to start: `...base_url must point at a local server`

`app/config.py` rejects any `base_url` that isn't loopback, `host.docker.internal`, or a private network address. This is deliberate: the OpenAI SDK would otherwise silently fall back to `api.openai.com`.

Use one of:
- `http://host.docker.internal:1234/v1` (server on this machine)
- `http://192.168.x.x:1234/v1` (server on your LAN)

### 3. Can't reach the model server

- **LM Studio server not started**: Developer tab → Start Server, port 1234.
- **Wrong address from Docker**: use `host.docker.internal`, not `localhost` — inside the container, `localhost` is the container.
- **Linux**: `docker-compose.yml` maps `host.docker.internal` via `extra_hosts`; if you removed that, the name won't resolve.
- **Server bound to 127.0.0.1 only**: enable "Serve on Local Network" (or bind `0.0.0.0`) so the container can reach it.
- Quick check from the host: `curl http://localhost:1234/v1/models`

### 4. `model_not_found` / 404 from the model server

The names in `config.yaml` must match what the server actually has:

```bash
curl http://localhost:1234/v1/models
```

Load the embedding model **and** the chat model in LM Studio. Either enable just-in-time loading in the server settings or load both before starting a query/ingest.

### 5. ChromaDB connection errors

- Wait for the healthcheck to pass: `docker-compose logs chroma`
- Verify from the host: `curl http://localhost:8001/api/v1/heartbeat`
- Restart: `docker-compose restart`

### 6. Ingestion fails

- **Model server unreachable or embedding model missing** — see issues 3 and 4; the embed step fails first.
- **Timeout**: a cold model can take a while on the first batch; the client allows 120s per request. Ingestion overall takes ~5–10 minutes.
- **Check logs**: `docker-compose logs api`
- **PDFs**: ensure all six files are in `PDFs/` and match the `Section X [Name] ... Iss NN ... date` filename pattern.

If embedding fails, the existing collection is left untouched — embeddings are generated before the collection is recreated.

### 7. "Collection not found"

Ingestion hasn't run (or was run against a different collection name):

```bash
./run.sh ingest
```

Changing the embedding model also invalidates the collection: re-ingest.

### 8. No results / low-quality answers

- **Lower the threshold**: `similarity_threshold` from `0.6` to `0.4` in `config.yaml`.
- **Raise `top_k`** from `5` to `10`.
- **Use regulation wording**: "minimum mass", "power unit", "parc fermé", not "car weight".
- **Small models paraphrase**: a larger chat model usually improves citation accuracy.

### 9. Slow responses

- The first request after loading a model is slow (weights into RAM); later ones are faster.
- Check the model fits in RAM/VRAM; a swapping 27B model is slower than a resident 8B model.
- Reduce `top_k` to send fewer chunks.
- Check container CPU/RAM in Docker Desktop.

### 10. Web UI won't load

- `curl http://localhost:8000/health`
- Browser console errors: the UI loads `marked` and `DOMPurify` from `/static/vendor/` (vendored, no CDN). If those 404, the UI falls back to plain text.
- Try incognito or another browser.

### 11. Eval fails

- Run inside Docker: `./run.sh eval`
- Ingestion must be complete, and the chat model loaded.
- Per-question deadline is `EVAL_TIMEOUT` (default 180s). Local answers take 60–130s; if you see read timeouts, raise it. A timed-out request keeps running server-side and the next one queues behind it, so timeouts cascade.
- Check `eval/results.json` inside the container for the raw answers.

### 12. PDF parsing issues

- PDFs must follow the FIA layout (Section header, `ARTICLE C4: ...`, `C4.1 ...` clause headings).
- Check per-file logs: "Extracted N chunks from ...".
- Long clauses are split into numbered parts (`part` metadata) on purpose.
- Filenames must match `Section ([A-F]) [Name] ... Iss NN ... YYYY-MM-DD`.

## Getting help

1. `docker-compose logs api` / `docker-compose logs chroma`
2. `curl http://localhost:8000/health`
3. `curl http://localhost:1234/v1/models` (host)
4. `config.yaml` model names vs what the server lists

## Debug mode

In `app/main.py`, change `logging.basicConfig(level=logging.INFO)` to `DEBUG`, then `docker-compose up --build` and `docker-compose logs -f api`.

## Reset everything

```bash
./run.sh clean
./run.sh start
./run.sh ingest
```

`clean` removes `data/`, so the collection is rebuilt from scratch.

## Expected performance

On a machine with enough RAM for the model:

- **Ingestion**: ~5–10 minutes (six PDFs)
- **Query**: a few seconds to ~2 minutes depending on model size and `top_k`
- **Eval suite**: 10 questions, ~15 minutes at 60–130s each
- **Startup**: 30–60s (ChromaDB healthcheck)

Much slower than this usually means the model is swapping or the server is still loading weights.
