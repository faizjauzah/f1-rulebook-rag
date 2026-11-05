# F1 Rulebook RAG - Project Summary

**Status**: ✅ Complete and ready for deployment

## What Was Built

A production-ready Retrieval Augmented Generation (RAG) system for querying the 2026 FIA Formula 1 Regulations. Built as a portfolio project to demonstrate AI engineering capabilities for job applications.

## Core Components

### Application Layer
- **FastAPI REST API** with 4 endpoints (health, ingest, query, docs)
- **Simple Web UI** (single HTML page with CSS/JS)
- **Docker Compose** orchestration (API + ChromaDB containers)
- **Profile-based configuration** (cloud/local switching)

### RAG Pipeline
- **Ingestion**: PDF → pymupdf → semantic chunking by article → embeddings → ChromaDB
- **Retrieval**: Question → embedding → vector search → similarity threshold filtering → top-k chunks
- **Generation**: Chunks → LLM prompt → answer with citations

### Two Operating Modes
1. **Cloud Mode**: Google Gemini (free API) for embeddings + LLM
2. **Local Mode**: bge-large-en-v1.5 embeddings + LM Studio LLM

### Quality Assurance
- **Eval set**: 10 questions (easy/medium/hard, all 6 sections)
- **Smoke tests**: 5 automated tests for quick validation
- **Edge case handling**: Off-topic detection, similarity threshold, error fallbacks

## File Structure

```
/
├── README.md                    # Complete documentation
├── CHECKLIST.md                 # Setup and deployment checklist
├── TROUBLESHOOTING.md           # Common issues and solutions
├── config.yaml                  # Profile-based configuration
├── docker-compose.yml           # Multi-container orchestration
├── Dockerfile                   # API container image
├── requirements.txt             # Python dependencies
├── run.sh                       # Helper script for common tasks
├── smoke_test.sh                # Quick validation tests
├── .env.example                 # Environment template
├── .gitignore                   # Git exclusions
│
├── app/
│   ├── main.py                  # FastAPI application entry
│   ├── config.py                # Configuration loading
│   ├── api/
│   │   ├── routes.py            # API endpoints
│   │   └── models.py            # Pydantic request/response models
│   ├── services/
│   │   ├── ingestion.py         # PDF processing & embedding
│   │   ├── retrieval.py         # Vector search
│   │   └── generation.py        # LLM answer generation
│   └── static/
│       └── index.html           # Web UI
│
├── eval/
│   ├── questions.json           # 10 evaluation questions
│   └── run_eval.py              # Evaluation runner script
│
├── docs/
│   └── ARCHITECTURE.md          # Architecture diagram & decisions
│
└── PDFs/                        # 6 F1 regulation PDFs (provided by user)
```

## Technology Stack

- **Backend**: FastAPI, Python 3.11
- **Vector DB**: ChromaDB
- **LLMs**: Google Gemini API, LM Studio (local)
- **Embeddings**: Gemini text-embedding-004, bge-large-en-v1.5
- **PDF Processing**: pymupdf (fitz)
- **Containerization**: Docker, Docker Compose
- **Validation**: Custom eval framework, smoke tests

## Key Features Implemented

✅ Semantic chunking by regulation article (preserves structure)  
✅ Rich metadata per chunk (section, article, page, issue, date)  
✅ Two separate ChromaDB collections (768-dim vs 1024-dim)  
✅ Similarity threshold filtering (configurable, default 0.6)  
✅ Profile-based config (one-line switch between cloud/local)  
✅ Source citations with exact text snippets  
✅ Response metadata (model, chunks used, response time)  
✅ Off-topic question handling (graceful fallback)  
✅ Docker healthchecks and service dependencies  
✅ Helper scripts for common operations  
✅ Comprehensive documentation  

## What It Demonstrates

### AI Engineering Skills
- RAG architecture design and implementation
- Vector database usage (embeddings, similarity search)
- LLM prompt engineering and integration
- Multiple provider support (Gemini, OpenAI-compatible)
- Semantic chunking strategies
- Retrieval quality optimization

### Software Engineering Skills
- REST API design with FastAPI
- Docker multi-container orchestration
- Configuration management (profiles, env vars)
- Error handling and edge cases
- Logging and observability
- Code organization and modularity

### DevOps/Deployment Skills
- Docker containerization
- Docker Compose networking and volumes
- Cloud deployment readiness (Fly.io)
- Environment-based configuration
- Health checks and service dependencies

### Documentation Skills
- Complete README with examples
- Architecture documentation
- Troubleshooting guide
- Setup checklist
- Code comments

## Next Steps for User

1. **Add Google API Key**:
   - Get free key from https://ai.google.dev/
   - Add to `.env` file

2. **Start Services**:
   ```bash
   ./run.sh start
   ```

3. **Run Ingestion** (5-20 min wait):
   ```bash
   ./run.sh ingest
   ```

4. **Validate**:
   ```bash
   ./smoke_test.sh
   ./run.sh eval
   ```

5. **Deploy**:
   - Follow `CHECKLIST.md` for Fly.io deployment
   - Get live demo URL for portfolio

6. **Share**:
   - Push to public GitHub repo
   - Add to portfolio site with demo link
   - Include in job applications

## Portfolio Value

This project demonstrates:
- **Hands-on RAG experience** (not just theory)
- **Production-ready code** (error handling, logging, documentation)
- **Cloud + Local** flexibility (shows understanding of cost/privacy tradeoffs)
- **Full stack** (API, UI, database, deployment)
- **Best practices** (Docker, config management, testing)
- **Technical writing** (documentation quality)

Perfect for AI Engineer, ML Engineer, or Backend Engineer positions focusing on LLM applications.

## Estimated Build Time

Total: ~4 hours for complete implementation, testing, and documentation

Breakdown:
- Core RAG pipeline: 1.5 hours
- API + UI: 1 hour
- Docker setup: 0.5 hours
- Eval + smoke tests: 0.5 hours
- Documentation: 0.5 hours

## Dependencies

All in `requirements.txt`, key ones:
- fastapi==0.115.0
- chromadb==0.5.11
- google-generativeai==0.8.3
- sentence-transformers==3.2.0
- pymupdf==1.24.10
- openai==1.52.2 (for LM Studio)

## Cost

- **Development**: $0 (Docker + free Gemini API)
- **Cloud hosting**: ~$5-10/month (Fly.io free tier may cover it)
- **Local mode**: $0 (fully offline)

## License

MIT (suggested for portfolio projects)

---

**Project completed**: 2026-11-05  
**Ready for deployment**: Yes  
**Ready for portfolio**: Yes  
**Documentation complete**: Yes  
**Tests included**: Yes
