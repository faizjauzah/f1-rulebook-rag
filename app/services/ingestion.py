import os
import re
import logging
from typing import List, Dict, Any
import fitz  # pymupdf
import chromadb
from chromadb.config import Settings

from app.config import config

logger = logging.getLogger(__name__)


def extract_metadata_from_filename(filename: str) -> Dict[str, Any]:
    """Extract section info from PDF filename."""
    # Example: "FIA 2026 F1 Regulations - Section B [Sporting] - Iss 09 - 2026-10-01.pdf"
    pattern = r"Section ([A-F]) \[([^\]]+)\].*Iss (\d+).*(\d{4}-\d{2}-\d{2})"
    match = re.search(pattern, filename)
    
    if match:
        section = match.group(1)
        section_name = match.group(2)
        issue = match.group(3)
        date = match.group(4)
        return {
            "section": section,
            "section_name": section_name,
            "issue": issue,
            "date": date,
            "doc_title": filename.replace(".pdf", "")
        }
    return {}


def extract_chunks_from_pdf(pdf_path: str) -> List[Dict[str, Any]]:
    """Extract semantic chunks from PDF by article structure."""
    chunks = []
    doc = fitz.open(pdf_path)
    
    # Extract metadata from filename
    base_metadata = extract_metadata_from_filename(os.path.basename(pdf_path))
    
    current_article = None
    current_text = []
    current_page = None
    
    for page_num, page in enumerate(doc, start=1):
        text = page.get_text()
        lines = text.split('\n')
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # Detect article headers (e.g., "12.3", "ARTICLE 12.3", "12.3 DRS Activation")
            article_match = re.match(r'^(?:ARTICLE\s+)?(\d+(?:\.\d+)?)\s*(.*?)$', line, re.IGNORECASE)
            
            if article_match and len(line) < 100:  # Article headers are typically short
                # Save previous chunk
                if current_article and current_text:
                    chunk_text = '\n'.join(current_text).strip()
                    if chunk_text:
                        chunks.append({
                            "text": chunk_text,
                            "metadata": {
                                **base_metadata,
                                "article": current_article,
                                "article_title": current_article_title,
                                "page": current_page
                            }
                        })
                
                # Start new chunk
                current_article = article_match.group(1)
                current_article_title = article_match.group(2).strip() or None
                current_text = [line]
                current_page = page_num
            else:
                # Continue current chunk
                if current_article:
                    current_text.append(line)
                    if current_page is None:
                        current_page = page_num
    
    # Save last chunk
    if current_article and current_text:
        chunk_text = '\n'.join(current_text).strip()
        if chunk_text:
            chunks.append({
                "text": chunk_text,
                "metadata": {
                    **base_metadata,
                    "article": current_article,
                    "article_title": current_article_title,
                    "page": current_page
                }
            })
    
    doc.close()
    return chunks


def get_embeddings(texts: List[str]) -> List[List[float]]:
    """Generate embeddings based on configured provider."""
    if config.embedding_provider == "gemini":
        import google.generativeai as genai
        genai.configure(api_key=config.google_api_key)
        
        embeddings = []
        for text in texts:
            result = genai.embed_content(
                model=f"models/{config.embedding_model}",
                content=text,
                task_type="retrieval_document"
            )
            embeddings.append(result['embedding'])
        return embeddings
    
    elif config.embedding_provider == "local":
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer(config.embedding_model)
        embeddings = model.encode(texts, convert_to_numpy=True)
        return embeddings.tolist()
    
    else:
        raise ValueError(f"Unknown embedding provider: {config.embedding_provider}")


def ingest_pdfs() -> Dict[str, Any]:
    """Ingest all PDFs into ChromaDB."""
    logger.info(f"Starting ingestion for collection: {config.collection_name}")
    
    # Connect to ChromaDB
    client = chromadb.HttpClient(host=config.chroma_host, port=config.chroma_port)
    
    # Get or create collection
    try:
        collection = client.get_collection(name=config.collection_name)
        logger.info(f"Collection {config.collection_name} already exists, deleting...")
        client.delete_collection(name=config.collection_name)
    except Exception:
        pass
    
    collection = client.create_collection(name=config.collection_name)
    
    # Process all PDFs
    all_chunks = []
    pdf_files = [f for f in os.listdir(config.pdf_directory) if f.endswith('.pdf')]
    
    for pdf_file in pdf_files:
        logger.info(f"Processing {pdf_file}...")
        pdf_path = os.path.join(config.pdf_directory, pdf_file)
        chunks = extract_chunks_from_pdf(pdf_path)
        all_chunks.extend(chunks)
        logger.info(f"Extracted {len(chunks)} chunks from {pdf_file}")
    
    if not all_chunks:
        return {
            "status": "error",
            "message": "No chunks extracted from PDFs",
            "chunks_created": 0,
            "collection": config.collection_name
        }
    
    # Generate embeddings
    logger.info(f"Generating embeddings for {len(all_chunks)} chunks...")
    texts = [chunk["text"] for chunk in all_chunks]
    embeddings = get_embeddings(texts)
    
    # Add to ChromaDB
    logger.info("Adding chunks to ChromaDB...")
    ids = [f"chunk_{i}" for i in range(len(all_chunks))]
    metadatas = [chunk["metadata"] for chunk in all_chunks]
    
    collection.add(
        ids=ids,
        embeddings=embeddings,
        documents=texts,
        metadatas=metadatas
    )
    
    logger.info(f"Ingestion complete: {len(all_chunks)} chunks added to {config.collection_name}")
    
    return {
        "status": "success",
        "message": f"Successfully ingested {len(pdf_files)} PDFs",
        "chunks_created": len(all_chunks),
        "collection": config.collection_name
    }
