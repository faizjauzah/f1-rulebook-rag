# ⚡ Quick Start Guide

Get the F1 Rulebook RAG running in under 10 minutes (plus ingestion time).

## Step 1: Get Your API Key (2 minutes)

1. Go to https://ai.google.dev/
2. Click "Get API key in Google AI Studio"
3. Click "Create API key"
4. Copy the key

## Step 2: Configure (1 minute)

```bash
# Copy environment template
cp .env.example .env

# Edit .env and paste your API key
# Replace 'your_google_api_key_here' with your actual key
nano .env  # or use any text editor
```

## Step 3: Start Services (2 minutes)

```bash
# Make helper script executable
chmod +x run.sh

# Start Docker containers
./run.sh start
```

Wait for logs to show:
- ✅ "Application startup complete"
- ✅ ChromaDB healthcheck passing

## Step 4: Ingest PDFs (5-20 minutes)

```bash
# In a new terminal
./run.sh ingest
```

**Wait time**: 
- Cloud mode (Gemini): ~20 minutes (rate limited)
- Local mode: ~5 minutes (if you have LM Studio)

You'll see logs like:
```
Processing Section A...
Extracted 52 chunks from Section A
Processing Section B...
...
Ingestion complete: 342 chunks added
```

## Step 5: Test It! (1 minute)

### Web UI
Open http://localhost:8000 in your browser and ask:
- "What is DRS?"
- "What happens if it rains during qualifying?"

### Command Line
```bash
./run.sh query "What is DRS?"
```

### Smoke Tests
```bash
chmod +x smoke_test.sh
./smoke_test.sh
```

## That's It! 🎉

You now have a working RAG system.

## What Next?

### Run Full Evaluation
```bash
./run.sh eval
```

### Try the API Docs
Open http://localhost:8000/docs

### Deploy to Cloud
See `CHECKLIST.md` for Fly.io deployment steps

### Customize
Edit `config.yaml` to:
- Switch between cloud/local profiles
- Adjust `top_k` (chunks retrieved)
- Tune `similarity_threshold`

## Troubleshooting

### "Collection not found" error
You forgot step 4. Run `./run.sh ingest`

### "ChromaDB connection failed"
Wait longer for services to start. Check with `./run.sh health`

### Slow/no response
Check your internet connection (for Gemini API)

### Still stuck?
See `TROUBLESHOOTING.md` for detailed help

## Quick Commands Reference

```bash
./run.sh start      # Start services
./run.sh stop       # Stop services
./run.sh ingest     # Ingest PDFs
./run.sh health     # Check status
./run.sh query "Q"  # Ask a question
./run.sh eval       # Run full evaluation
./run.sh logs       # View API logs
./run.sh clean      # Reset everything
```

## Local Mode (Optional)

To use local LLM instead of Gemini:

1. Install LM Studio from https://lmstudio.ai/
2. Load a model (Mistral 7B or Llama 3)
3. Start server on port 1234
4. Edit `config.yaml`: change `profile: "cloud"` to `profile: "local"`
5. Restart: `./run.sh stop && ./run.sh start`
6. Ingest again: `./run.sh ingest`

---

**Time to first query**: ~10 minutes (setup) + 5-20 minutes (ingestion)

Need help? Check `README.md` or `TROUBLESHOOTING.md`
