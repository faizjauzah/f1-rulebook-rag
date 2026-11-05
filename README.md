# 🏎️ F1 Rulebook RAG

A Retrieval Augmented Generation (RAG) system for querying the 2026 FIA Formula 1 Regulations. Built to demonstrate modern AI engineering practices including vector search, LLM integration, REST API design, and containerization.

## 🎯 Features

- **Dual Operating Modes**: Cloud (Google Gemini) or Local (LM Studio + local embeddings)
- **Semantic Search**: Retrieves relevant regulation articles using vector similarity
- **Source Citations**: Every answer includes exact article references with page numbers
- **REST API**: FastAPI with automatic OpenAPI documentation
- **Simple Web UI**: Ask questions and view answers with sources
- **Docker Compose**: Multi-container setup (API + ChromaDB)
- **Configurable**: Profile-based config switching between cloud/local

## 📋 Table of Contents

- [Architecture](#architecture)
- [Setup](#setup)
- [Usage](#usage)
- [Configuration](#configuration)
- [Evaluation](#evaluation)
- [API Documentation](#api-documentation)
- [Deployment](#deployment)

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
│  │ Ingestion│  │    Query        │ │
│  │ Service  │  │    Service      │ │
│  └────┬─────┘  └────┬────────────┘ │
│       │             │               │
│       ▼             ▼               │
│  ┌──────────────────────────────┐  │
│  │     ChromaDB Vector Store     │  │
│  └──────────────────────────────┘  │
└─────────────────────────────────────┘
          │                │
          ▼                ▼
    ┌─────────┐      ┌──────────┐
    │ Gemini  │      │ LM Studio│
    │   API   │      │  (Local) │
    └─────────┘      └──────────┘
```

**Components:**

- **FastAPI**: REST API + static file serving
- **ChromaDB**: Vector database for embeddings
- **Gemini API**: Cloud embeddings + LLM (free tier)
- **LM Studio**: Local LLM inference (optional)
- **sentence-transformers**: Local embeddings (bge-large-en-v1.5)
- **pymupdf**: PDF text extraction with semantic chunking

**Data Flow:**

1. **Ingestion**: PDFs → pymupdf → semantic chunks (by article) → embeddings → ChromaDB
2. **Query**: Question → embedding → similarity search → top-k chunks → LLM prompt → answer + sources

## 🚀 Setup

### Prerequisites

- Docker and Docker Compose
- Google AI Studio API key (free at https://ai.google.dev/)
- (Optional) LM Studio for local mode

### Quick Start

1. **Clone and navigate:**
   ```bash
   cd f1-rulebook-rag
   ```

2. **Create `.env` file:**
   ```bash
   cp .env.example .env
   ```
   
   Edit `.env` and add your Google API key:
   ```
   GOOGLE_API_KEY=your_actual_key_here
   ```

3. **Start services:**
   ```bash
   docker-compose up --build
   ```

4. **Wait for services** to be healthy (check logs for "Application startup complete")

5. **Ingest PDFs** (one-time setup):
   ```bash
   curl -X POST http://localhost:8000/ingest
   ```
   
   This takes ~5-20 minutes depending on your profile (local is faster).

6. **Open UI**: http://localhost:8000

### Local Mode Setup (Optional)

To use local LLM instead of Gemini:

1. **Install LM Studio**: https://lmstudio.ai/

2. **Load a model** (recommended: Mistral 7B or Llama 3.1 8B)

3. **Start LM Studio server** on port 1234

4. **Change profile** in `config.yaml`:
   ```yaml
   profile: "local"
   ```

5. **Restart containers**:
   ```bash
   docker-compose down
   docker-compose up
   ```

6. **Ingest with local embeddings**:
   ```bash
   curl -X POST http://localhost:8000/ingest
   ```

## 💡 Usage

### Web UI

1. Open http://localhost:8000
2. Select profile (Cloud/Local)
3. Type your question
4. Get answer with source citations

**Example questions:**
- "What is DRS and when can it be used?"
- "What happens if it rains during qualifying?"
- "What are the technical specifications for the power unit?"

### API (curl)

**Query:**
```bash
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"question": "What is DRS?"}'
```

**Health check:**
```bash
curl http://localhost:8000/health
```

**Re-ingest:**
```bash
curl -X POST http://localhost:8000/ingest
```

### API Documentation

Interactive docs at http://localhost:8000/docs

## ⚙️ Configuration

### config.yaml

Profile-based configuration:

```yaml
profile: "cloud"  # or "local"

profiles:
  cloud:
    embedding:
      provider: "gemini"
      model: "text-embedding-004"
    llm:
      provider: "gemini"
      model: "gemini-1.5-flash"
      temperature: 0.1
    collection: "f1-regs-gemini"
  
  local:
    embedding:
      provider: "local"
      model: "BAAI/bge-large-en-v1.5"
    llm:
      provider: "local"
      base_url: "http://host.docker.internal:1234/v1"
      model: "local-model"
      temperature: 0.1
    collection: "f1-regs-local"

shared:
  top_k: 5                      # Number of chunks to retrieve
  chunk_size: 512               # Target chunk size (not strict)
  similarity_threshold: 0.6     # Minimum similarity score
  pdf_directory: "PDFs"
  chroma_persist_directory: "/data/chroma"
```

### Environment Variables

Override config via `.env`:

```bash
PROFILE=local
TOP_K=10
SIMILARITY_THRESHOLD=0.7
GOOGLE_API_KEY=your_key
```

## 📊 Evaluation

Run the evaluation suite:

```bash
# Inside the container or with Python 3.11+
python eval/run_eval.py
```

**Eval set:** 10 questions spanning:
- **Difficulty**: 3 easy, 4 medium, 3 hard
- **Coverage**: All 6 regulation sections (A-F)

Results are saved to `eval/results.json` and printed as a summary table.

**Example output:**
```
EVALUATION SUMMARY
================================================================================

Total questions: 10
Successful: 10
Failed: 0
Average response time: 3.45s

By category:
  Easy: 3/3
  Medium: 4/4
  Hard: 3/3
```

## 📚 API Documentation

### POST /query

Query the RAG system.

**Request:**
```json
{
  "question": "What is DRS?"
}
```

**Response:**
```json
{
  "answer": "DRS (Drag Reduction System) is...",
  "sources": [
    {
      "section": "B",
      "section_name": "Sporting",
      "doc_title": "FIA 2026 F1 Regulations - Section B [Sporting]",
      "article": "12.3",
      "article_title": "DRS Activation",
      "page": 47,
      "text": "The DRS may only be activated..."
    }
  ],
  "metadata": {
    "model": "gemini-1.5-flash",
    "chunks_retrieved": 5,
    "chunks_used": 3,
    "response_time_ms": 1247
  }
}
```

### POST /ingest

Ingest PDFs into the vector store (one-time setup per collection).

**Response:**
```json
{
  "status": "success",
  "message": "Successfully ingested 6 PDFs",
  "chunks_created": 342,
  "collection": "f1-regs-gemini"
}
```

### GET /health

Health check.

**Response:**
```json
{
  "status": "healthy",
  "profile": "cloud",
  "chroma_connected": true
}
```

## 🌐 Deployment

### Fly.io (Recommended)

1. **Install flyctl**: https://fly.io/docs/flyctl/install/

2. **Login**:
   ```bash
   fly auth login
   ```

3. **Create app**:
   ```bash
   fly launch
   ```

4. **Set secrets**:
   ```bash
   fly secrets set GOOGLE_API_KEY=your_key
   ```

5. **Create volume** for ChromaDB:
   ```bash
   fly volumes create chroma_data --size 1
   ```

6. **Update fly.toml** to mount volume (adjust as needed)

7. **Deploy**:
   ```bash
   fly deploy
   ```

8. **Ingest** (one-time):
   ```bash
   curl -X POST https://your-app.fly.dev/ingest
   ```

### Other Platforms

- **Railway**: Similar process, use Railway CLI
- **Render**: Deploy from GitHub, add environment variables
- **Google Cloud Run**: Use Cloud SQL for ChromaDB persistence

## 🧪 Testing

**Smoke test** (5 varied queries):
```bash
# Easy
curl -X POST http://localhost:8000/query -H "Content-Type: application/json" -d '{"question": "What is DRS?"}'

# Medium
curl -X POST http://localhost:8000/query -H "Content-Type: application/json" -d '{"question": "What happens if a driver causes a collision?"}'

# Hard
curl -X POST http://localhost:8000/query -H "Content-Type: application/json" -d '{"question": "How do cost cap regulations interact with power unit manufacturer regulations?"}'

# Off-topic (should gracefully fail)
curl -X POST http://localhost:8000/query -H "Content-Type: application/json" -d '{"question": "What is the weather tomorrow?"}'

# Edge case
curl -X POST http://localhost:8000/query -H "Content-Type: application/json" -d '{"question": "Tell me about basketball rules"}'
```

## 📁 Project Structure

```
/
├── README.md
├── app/
│   ├── main.py                 # FastAPI application
│   ├── config.py               # Configuration loading
│   ├── api/
│   │   ├── routes.py           # API endpoints
│   │   └── models.py           # Pydantic models
│   ├── services/
│   │   ├── ingestion.py        # PDF processing & embedding
│   │   ├── retrieval.py        # Vector search
│   │   └── generation.py       # LLM answer generation
│   └── static/
│       └── index.html          # Web UI
├── eval/
│   ├── questions.json          # Evaluation questions
│   └── run_eval.py             # Evaluation script
├── PDFs/                       # F1 regulation PDFs (6 files)
├── data/chroma/                # ChromaDB persistence (gitignored)
├── config.yaml                 # Profile-based config
├── .env                        # API keys (gitignored)
├── .env.example
├── requirements.txt
├── Dockerfile
└── docker-compose.yml
```

## 🛠 Technology Stack

- **FastAPI**: Modern Python web framework
- **ChromaDB**: Vector database
- **Google Gemini**: Cloud LLM + embeddings
- **sentence-transformers**: Local embeddings (bge-large-en-v1.5)
- **LM Studio**: Local LLM server
- **pymupdf**: PDF parsing
- **Docker**: Containerization
- **Pydantic**: Data validation

## 🎓 Learning Outcomes

This project demonstrates:

✅ **RAG Architecture**: Document chunking, embeddings, vector search, prompt engineering  
✅ **REST API Design**: FastAPI, Pydantic models, error handling, response formatting  
✅ **Docker**: Multi-container orchestration, networking, volumes, healthchecks  
✅ **Configuration Management**: Profile-based config, environment variables, secrets  
✅ **LLM Integration**: Multiple providers (Gemini, OpenAI-compatible), prompt engineering  
✅ **Vector Databases**: ChromaDB setup, collection management, similarity search  
✅ **PDF Processing**: Semantic chunking, metadata extraction  
✅ **Edge Case Handling**: Off-topic detection, similarity thresholds, graceful errors  

## 📝 Future Enhancements

- [ ] Conversation history (multi-turn queries)
- [ ] Hybrid search (keyword + semantic)
- [ ] Query rewriting for better retrieval
- [ ] Streaming responses
- [ ] Advanced eval metrics (RAGAS, faithfulness)
- [ ] CI/CD pipeline
- [ ] Rate limiting
- [ ] Caching frequent queries

## 📄 License

MIT

## 🤝 Contributing

This is a portfolio project, but feedback and suggestions are welcome via issues.

---

**Built with ❤️ for AI engineering portfolio**
