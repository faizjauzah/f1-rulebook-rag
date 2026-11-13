import time
import logging
from fastapi import APIRouter, HTTPException
import chromadb

from app.api.models import QueryRequest, QueryResponse, IngestResponse, HealthResponse, Source, QueryMetadata
from app.services.ingestion import ingest_pdfs
from app.services.retrieval import retrieve_chunks, filter_by_threshold
from app.services.generation import generate_answer, format_sources
from app.config import config

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    # Check ChromaDB connection
    chroma_connected = False
    try:
        client = chromadb.HttpClient(host=config.chroma_host, port=config.chroma_port)
        client.heartbeat()
        chroma_connected = True
    except Exception as e:
        logger.warning(f"ChromaDB connection failed: {e}")
    
    return HealthResponse(
        status="healthy" if chroma_connected else "degraded",
        embedding_model=config.embedding_model,
        llm_model=config.llm_model,
        collection=config.collection_name,
        chroma_connected=chroma_connected
    )


@router.post("/ingest", response_model=IngestResponse)
async def ingest():
    """Ingest PDFs into vector store."""
    try:
        logger.info("Starting ingestion...")
        result = ingest_pdfs()
        return IngestResponse(**result)
    except Exception as e:
        logger.error(f"Ingestion failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {str(e)}")


@router.post("/query", response_model=QueryResponse)
async def query(request: QueryRequest):
    """Query the RAG system."""
    start_time = time.time()
    
    try:
        # Retrieve relevant chunks
        chunks = retrieve_chunks(request.question)
        chunks_retrieved = len(chunks)
        
        # Refuse when nothing clears the refusal threshold, even if some chunks
        # cleared the lower similarity threshold (keeps out-of-scope questions
        # from being answered from weak matches). Direct clause lookups always
        # have similarity 1.0 and are never refused here.
        max_similarity = max((c.get("similarity", 0.0) for c in chunks), default=0.0)
        if not chunks or max_similarity < config.refusal_threshold:
            return QueryResponse(
                answer="I couldn't find any relevant F1 regulations to answer your question. Please try rephrasing or ask about a different topic covered in the 2026 F1 regulations.",
                sources=[],
                metadata=QueryMetadata(
                    model=config.llm_model,
                    chunks_retrieved=chunks_retrieved,
                    chunks_used=0,
                    response_time_ms=int((time.time() - start_time) * 1000)
                )
            )

        # Filter by similarity threshold
        filtered_chunks = filter_by_threshold(chunks)
        
        # Check if we have relevant results
        if not filtered_chunks:
            # No relevant regulations found
            return QueryResponse(
                answer="I couldn't find any relevant F1 regulations to answer your question. Please try rephrasing or ask about a different topic covered in the 2026 F1 regulations.",
                sources=[],
                metadata=QueryMetadata(
                    model=config.llm_model,
                    chunks_retrieved=chunks_retrieved,
                    chunks_used=0,
                    response_time_ms=int((time.time() - start_time) * 1000)
                )
            )
        
        # Generate answer
        answer = generate_answer(request.question, filtered_chunks)
        
        # Format sources
        sources = format_sources(filtered_chunks, answer, request.question)
        
        # Calculate response time
        response_time_ms = int((time.time() - start_time) * 1000)
        
        return QueryResponse(
            answer=answer,
            sources=[Source(**s) for s in sources],
            metadata=QueryMetadata(
                model=config.llm_model,
                chunks_retrieved=chunks_retrieved,
                chunks_used=len(filtered_chunks),
                response_time_ms=response_time_ms
            )
        )
    
    except ValueError as e:
        # Collection not found or other validation error
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Query failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Query failed: {str(e)}")
