import ipaddress
import os
from typing import Any
from urllib.parse import urlparse

import yaml
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Hosts that count as "local". host.docker.internal is how a container reaches a
# server running on the host (Docker Desktop, or docker-compose extra_hosts).
_LOCAL_HOSTNAMES = {"localhost", "host.docker.internal"}


def _is_local_url(url: str) -> bool:
    """True if the URL points at loopback, this machine, or a private network."""
    host = urlparse(url).hostname or ""
    if host in _LOCAL_HOSTNAMES:
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return ip.is_loopback or ip.is_private


def _local_base_url(value: Any, name: str) -> str:
    """
    A missing or non-local base_url is a hard error. The OpenAI SDK silently falls
    back to api.openai.com when base_url is None, which this project must never do.
    """
    if not value:
        raise ValueError(
            f"{name}.base_url is required (e.g. http://host.docker.internal:1234/v1)"
        )
    url = str(value)
    if urlparse(url).scheme not in ("http", "https"):
        raise ValueError(f"{name}.base_url must be an http(s) URL, got: {url}")
    if not _is_local_url(url):
        raise ValueError(
            f"{name}.base_url must point at a local server, got: {url}. "
            "This project runs fully local (LM Studio, Ollama, llama.cpp, vLLM, ...)."
        )
    return url


class Config:
    def __init__(self):
        # Load config.yaml
        with open("config.yaml", "r") as f:
            raw = yaml.safe_load(f)

        # Embedding config (local OpenAI-compatible server)
        self.embedding_base_url = _local_base_url(raw["embedding"].get("base_url"), "embedding")
        self.embedding_model = raw["embedding"]["model"]

        # LLM config (same kind of server)
        self.llm_base_url = _local_base_url(raw["llm"].get("base_url"), "llm")
        self.llm_model = raw["llm"]["model"]
        self.llm_temperature = float(raw["llm"]["temperature"])

        # Evaluation. The judge shares the LLM server; only the model differs.
        evaluation = raw.get("evaluation") or {}
        self.evaluation_judge_model = evaluation.get("judge_model") or "qwen/qwen3.5-9b"
        self.evaluation_judge_temperature = float(evaluation.get("judge_temperature", 0.0))
        self.evaluation_embedding_model = evaluation.get("embedding_model") or self.embedding_model
        self.evaluation_timeout_s = int(evaluation.get("timeout_s", 300))
        self.evaluation_max_workers = int(evaluation.get("max_workers", 1))
        if not self.evaluation_judge_model:
            raise ValueError("evaluation.judge_model must not be empty")

        # Collection name
        self.collection_name = raw["collection"]

        # Shared config
        self.top_k = int(os.getenv("TOP_K", raw["top_k"]))
        self.similarity_threshold = float(os.getenv("SIMILARITY_THRESHOLD", raw["similarity_threshold"]))
        self.refusal_threshold = float(os.getenv("REFUSAL_THRESHOLD", raw.get("refusal_threshold", 0.7)))
        self.pdf_directory = os.getenv("PDF_DIRECTORY", raw["pdf_directory"])

        # Local servers ignore the key, but the OpenAI client requires one. Any
        # value works unless the server has authentication turned on.
        self.local_api_key = os.getenv("LOCAL_API_KEY", "lm-studio")

        # Chroma connection (Docker)
        self.chroma_host = os.getenv("CHROMA_HOST", "localhost")
        self.chroma_port = int(os.getenv("CHROMA_PORT", "8001"))


# Global config instance
config = Config()
