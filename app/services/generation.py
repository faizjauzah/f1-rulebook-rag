import logging
from typing import List, Dict, Any

from app.config import config

logger = logging.getLogger(__name__)


def generate_answer(question: str, chunks: List[Dict[str, Any]]) -> str:
    """Generate answer using LLM based on retrieved chunks."""
    if not chunks:
        return "I couldn't find any relevant F1 regulations to answer your question. Please try rephrasing or ask about a different topic covered in the 2026 F1 regulations."
    
    # Build context from chunks
    context_parts = []
    for i, chunk in enumerate(chunks, 1):
        metadata = chunk["metadata"]
        section = metadata.get("section", "Unknown")
        article = metadata.get("article", "Unknown")
        text = chunk["text"]
        context_parts.append(f"[Source {i}] Section {section}, Article {article}:\n{text}")
    
    context = "\n\n".join(context_parts)
    
    # Build prompt
    prompt = f"""You are an expert on FIA Formula 1 regulations. Answer the following question based ONLY on the provided regulation excerpts. If the excerpts don't contain enough information to answer the question, say so.

Question: {question}

Relevant Regulations:
{context}

Answer the question clearly and concisely, citing specific article numbers when relevant."""
    
    # Call LLM based on provider
    if config.llm_provider == "gemini":
        import google.generativeai as genai
        genai.configure(api_key=config.google_api_key)
        
        model = genai.GenerativeModel(config.llm_model)
        response = model.generate_content(
            prompt,
            generation_config=genai.GenerationConfig(
                temperature=config.llm_temperature
            )
        )
        return response.text
    
    elif config.llm_provider == "local":
        from openai import OpenAI
        
        client = OpenAI(
            base_url=config.llm_base_url,
            api_key=config.openai_api_key or "not-needed"
        )
        
        response = client.chat.completions.create(
            model=config.llm_model,
            messages=[
                {"role": "system", "content": "You are an expert on FIA Formula 1 regulations. Answer questions based only on the provided regulation excerpts."},
                {"role": "user", "content": prompt}
            ],
            temperature=config.llm_temperature
        )
        return response.choices[0].message.content
    
    else:
        raise ValueError(f"Unknown LLM provider: {config.llm_provider}")


def format_sources(chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Format chunks into source objects."""
    sources = []
    for chunk in chunks:
        metadata = chunk["metadata"]
        sources.append({
            "section": metadata.get("section", "Unknown"),
            "section_name": metadata.get("section_name", "Unknown"),
            "doc_title": metadata.get("doc_title", "Unknown"),
            "article": metadata.get("article", "Unknown"),
            "article_title": metadata.get("article_title"),
            "page": metadata.get("page"),
            "text": chunk["text"][:300] + "..." if len(chunk["text"]) > 300 else chunk["text"]  # Truncate long texts
        })
    return sources
