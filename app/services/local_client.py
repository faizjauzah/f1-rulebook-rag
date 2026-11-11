"""One place that builds the OpenAI-compatible client for the local model server."""
import httpx
from openai import OpenAI

from app.config import config

# A down server should fail visibly instead of hanging a request forever. The read
# timeouts are generous because a cold local model can take a while to answer.
CONNECT_TIMEOUT_S = 10
EMBEDDING_TIMEOUT_S = 120
LLM_TIMEOUT_S = 300


def build_client(base_url: str, timeout_s: float) -> OpenAI:
    return OpenAI(
        base_url=base_url,
        api_key=config.local_api_key,
        timeout=httpx.Timeout(timeout_s, connect=CONNECT_TIMEOUT_S),
    )
