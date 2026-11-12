"""Embeddings from a local OpenAI-compatible server (LM Studio, Ollama, ...)."""
import logging
import os
from typing import List

from app.config import config
from app.services.local_client import EMBEDDING_TIMEOUT_S, build_client

logger = logging.getLogger(__name__)

LOCAL_EMBED_BATCH = int(os.getenv("LOCAL_EMBED_BATCH", "16"))

# bge-large-en-v1.5 has a 512-token window. Chunks are sized in ingestion.py to stay below it;
# this clip is only a safety net so one oversized text can't make a whole batch fail.
MAX_EMBED_CHARS = int(os.getenv("MAX_EMBED_CHARS", "1000"))

# Prefixes for the embedding model (check your model card), e.g.
#   bge-*-en-v1.5: query = "Represent this sentence for searching relevant passages: ", documents = no prefix
#   nomic:         EMBED_QUERY_PREFIX="search_query: "   EMBED_DOC_PREFIX="search_document: "
#   EmbeddingGemma: EMBED_QUERY_PREFIX="task: search result | query: "   EMBED_DOC_PREFIX="title: none | text: "
# Defaults below are for bge-large-en-v1.5. If you set these env vars (even to ""), they win.
QUERY_PREFIX = os.getenv("EMBED_QUERY_PREFIX", "Represent this sentence for searching relevant passages: ")
DOC_PREFIX = os.getenv("EMBED_DOC_PREFIX", "")


def get_embeddings(texts: List[str], is_query: bool = False) -> List[List[float]]:
    """Embed texts with the configured local embedding model, in batches."""
    client = build_client(config.embedding_base_url, EMBEDDING_TIMEOUT_S)
    prefix = QUERY_PREFIX if is_query else DOC_PREFIX
    embeddings: List[List[float]] = []

    for start in range(0, len(texts), LOCAL_EMBED_BATCH):
        batch = []
        for t in texts[start:start + LOCAL_EMBED_BATCH]:
            if len(t) > MAX_EMBED_CHARS:
                logger.warning(f"Text of {len(t)} chars clipped to {MAX_EMBED_CHARS} for embedding")
                t = t[:MAX_EMBED_CHARS]
            batch.append(prefix + t)

        response = client.embeddings.create(
            model=config.embedding_model,
            input=batch,
        )
        data = sorted(response.data, key=lambda d: d.index)
        embeddings.extend(item.embedding for item in data)

        done = min(start + LOCAL_EMBED_BATCH, len(texts))
        if (start // LOCAL_EMBED_BATCH) % 10 == 0:
            logger.info(f"Generated {done}/{len(texts)} embeddings")

    return embeddings