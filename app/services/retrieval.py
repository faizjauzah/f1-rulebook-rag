import logging
from typing import List, Dict, Any
import chromadb

from app.config import config
from app.services.ingestion import get_embeddings

logger = logging.getLogger(__name__)


def retrieve_chunks(question: str) -> List[Dict[str, Any]]:
    """Retrieve relevant chunks from ChromaDB."""
    logger.info(f"Retrieving chunks for question: {question}")
    
    # Connect to ChromaDB
    client = chromadb.HttpClient(host=config.chroma_host, port=config.chroma_port)
    
    try:
        collection = client.get_collection(name=config.collection_name)
    except Exception as e:
        logger.error(f"Collection {config.collection_name} not found: {e}")
        raise ValueError(f"Collection {config.collection_name} not found. Please run /ingest first.")
    
    # Generate query embedding
    query_embedding = get_embeddings([question])[0]
    
    # Query ChromaDB
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=config.top_k
    )
    
    # Format results
    chunks = []
    if results['ids'] and results['ids'][0]:
        for i, doc_id in enumerate(results['ids'][0]):
            distance = results['distances'][0][i] if results['distances'] else 0
            # Convert distance to similarity score (cosine similarity = 1 - distance for normalized vectors)
            similarity = 1 - distance
            
            chunks.append({
                "id": doc_id,
                "text": results['documents'][0][i],
                "metadata": results['metadatas'][0][i],
                "similarity": similarity
            })
    
    logger.info(f"Retrieved {len(chunks)} chunks")
    return chunks


def filter_by_threshold(chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Filter chunks by similarity threshold."""
    filtered = [c for c in chunks if c["similarity"] >= config.similarity_threshold]
    logger.info(f"Filtered to {len(filtered)} chunks above threshold {config.similarity_threshold}")
    return filtered
