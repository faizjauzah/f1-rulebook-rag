import logging
import math
import os
import re
from typing import List, Dict, Any, Set

from app.config import config
from app.services.local_client import LLM_TIMEOUT_S, build_client

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Context budget for an 8k-token LLM (gemma): prompt + answer must fit in 8192 tokens.
# 12,000 chars of regulation text is ~3-4k tokens (digits and codes tokenize worse than prose),
# leaving room for the instructions, the question and the answer.
# ---------------------------------------------------------------------------
MAX_CONTEXT_CHARS = int(os.getenv("LLM_MAX_CONTEXT_CHARS", "12000"))   # total excerpt text sent to the LLM
MIN_SOURCE_CHARS = 300                                                   # don't send a source squeezed below this
LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "1500"))               # answer budget (reasoning models: raise)

# ---------------------------------------------------------------------------
# Tunables for "which paragraph supports the answer"
# ---------------------------------------------------------------------------
MAX_HIGHLIGHTS = 2            # max highlighted paragraphs per source
MIN_HIGHLIGHT_SCORE = 2.0     # below this, a source gets no highlight (raise = stricter)
MIN_PARAGRAPH_CHARS = 30      # ignore headings / fragments


# ---------------------------------------------------------------------------
# Answer generation
# ---------------------------------------------------------------------------
def _build_context(chunks: List[Dict[str, Any]]) -> str:
    """Build the excerpts block, in rank order, within MAX_CONTEXT_CHARS. The number MUST match the `ref` shown in the UI."""
    parts: List[str] = []
    used = 0
    for i, chunk in enumerate(chunks, 1):
        metadata = chunk["metadata"]
        ref = chunk.get("ref", i)
        header = chunk.get("citation") or (
            f"Section {metadata.get('section', 'Unknown')}, Article {metadata.get('article', 'Unknown')}"
        )
        prefix = f"[Source {ref}] {header}:\n"

        remaining = MAX_CONTEXT_CHARS - used - len(prefix) - 2
        if remaining < MIN_SOURCE_CHARS:
            logger.warning(f"Context budget reached: sources from #{ref} on were not sent to the LLM")
            break

        text = chunk["text"]
        if len(text) > remaining:
            logger.warning(f"Source {ref} cut from {len(text)} to ~{remaining} chars to fit the LLM context")
            text = text[:remaining].rsplit("\n", 1)[0] + "\n[... excerpt truncated ...]"

        block = prefix + text
        parts.append(block)
        used += len(block) + 2

    logger.info(f"LLM context: {used} chars from {len(parts)}/{len(chunks)} sources")
    return "\n\n".join(parts)


def generate_answer(question: str, chunks: List[Dict[str, Any]]) -> str:
    """Generate answer using LLM based on retrieved chunks."""
    if not chunks:
        return "I couldn't find any relevant F1 regulations to answer your question. Please try rephrasing or ask about a different topic covered in the 2026 F1 regulations."

    context = _build_context(chunks)

    # Build prompt
    prompt = f"""You are an expert on FIA Formula 1 regulations. Answer the following question based ONLY on the provided regulation excerpts. If the excerpts don't contain enough information to answer the question, say so.

Question: {question}

Relevant Regulations:
{context}

Tables in the excerpts are written as rows of cells separated by " | " ("-" means an empty cell). Read the header rows first to see which column is which before you quote a value.

Answer the question clearly and concisely in Markdown, citing specific article numbers when relevant. After each statement, cite the excerpt it comes from with its source number in square brackets, for example [1] or [2][3]. Only cite excerpts you actually used."""

    # Call the local model server
    client = build_client(config.llm_base_url, LLM_TIMEOUT_S)

    response = client.chat.completions.create(
        model=config.llm_model,
        messages=[
            {"role": "system", "content": "You are an expert on FIA Formula 1 regulations. Answer questions based only on the provided regulation excerpts."},
            {"role": "user", "content": prompt}
        ],
        temperature=config.llm_temperature,
        max_tokens=LLM_MAX_TOKENS,
    )
    answer = (response.choices[0].message.content or "").strip()
    if not answer:
        logger.warning("LLM returned an empty answer (out of tokens or context?)")
        return "The model returned an empty answer. Please try again; if it keeps happening, raise LLM_MAX_TOKENS or the model's context length."
    return answer


# ---------------------------------------------------------------------------
# Which paragraphs support the answer?
#
# Heuristic, no extra LLM call: every paragraph of a source is scored by how many of the
# answer's (and question's) meaningful words it contains. Numbers and codes ("724", "C4.1")
# count 3x, and the score is divided by sqrt(paragraph size) so long paragraphs don't win
# just by being long. The best paragraph(s) are flagged as `highlight`.
# ---------------------------------------------------------------------------
_CITATION_RE = re.compile(r"\[((?:Sources?\s*)?\d{1,2}(?:\s*,\s*(?:Sources?\s*)?\d{1,2})*)\]", re.IGNORECASE)
_TOKEN_RE = re.compile(r"[a-z0-9]+(?:\.[0-9]+)*")
_STOPWORDS = {
    "the", "and", "for", "are", "not", "that", "this", "with", "any", "all", "its", "has", "have",
    "from", "may", "shall", "must", "will", "can", "been", "which", "when", "where", "than", "then",
    "such", "each", "other", "their", "they", "them", "these", "those", "there", "into", "only",
    "also", "both", "per", "but", "was", "were", "who", "what", "how", "does", "did", "say", "says",
    "article", "regulation", "regulations", "excerpt", "source", "provided", "states", "stated",
}


def _cited_refs(answer: str) -> Set[int]:
    refs: Set[int] = set()
    for m in _CITATION_RE.finditer(answer or ""):
        refs.update(int(n) for n in re.findall(r"\d+", m.group(1)))
    return refs


def _tokens(text: str) -> Set[str]:
    return {t for t in _TOKEN_RE.findall(text.lower()) if len(t) > 1 and t not in _STOPWORDS}


def _weight(token: str) -> float:
    return 3.0 if any(c.isdigit() for c in token) else 1.0


def _build_weights(question: str, answer: str) -> Dict[str, float]:
    weights: Dict[str, float] = {}
    for t in _tokens(question or ""):
        weights[t] = 0.5 * _weight(t)
    answer_clean = _CITATION_RE.sub(" ", answer or "")
    for t in _tokens(answer_clean):
        weights[t] = _weight(t)
    return weights


def _pick_highlights(paragraphs: List[str], weights: Dict[str, float]) -> Set[int]:
    if not weights:
        return set()

    scored = []
    for i, p in enumerate(paragraphs):
        if len(p) < MIN_PARAGRAPH_CHARS:
            continue
        toks = _tokens(p)
        if not toks:
            continue
        overlap = sum(weights[t] for t in toks if t in weights)
        scored.append((overlap / math.sqrt(len(toks)), i))

    if not scored:
        return set()
    best = max(score for score, _ in scored)
    if best < MIN_HIGHLIGHT_SCORE:
        return set()

    ranked = sorted((x for x in scored if x[0] >= 0.6 * best), reverse=True)[:MAX_HIGHLIGHTS]
    return {i for _, i in ranked}


# ---------------------------------------------------------------------------
# Sources for the API response
# ---------------------------------------------------------------------------
def _opt_str(value: Any):
    return None if value is None else str(value)


def format_sources(chunks: List[Dict[str, Any]], answer: str = "", question: str = "") -> List[Dict[str, Any]]:
    """Format retrieved sources for the API: full clause text as paragraphs, with the ones that back the answer highlighted."""
    cited = _cited_refs(answer)
    weights = _build_weights(question, answer) if answer else {}

    sources = []
    for i, chunk in enumerate(chunks, 1):
        metadata = chunk["metadata"]
        ref = chunk.get("ref", i)
        paragraphs = chunk.get("paragraphs") or [chunk["text"]]
        marked = _pick_highlights(paragraphs, weights)

        sources.append({
            "ref": ref,
            "label": chunk.get("label") or f"Article {metadata.get('article', 'Unknown')}",
            "section": str(metadata.get("section", "Unknown")),
            "section_name": str(metadata.get("section_name", "Unknown")),
            "doc_title": str(metadata.get("doc_title", "Unknown")),
            "article": str(metadata.get("article", "Unknown")),
            "article_title": metadata.get("article_title") or None,
            "page": metadata.get("page"),
            "issue": _opt_str(metadata.get("issue")),
            "date": _opt_str(metadata.get("date")),
            "similarity": chunk.get("similarity"),
            "match": chunk.get("match", "semantic"),
            "cited": ref in cited,
            "truncated": bool(chunk.get("truncated", False)),
            "paragraphs": [{"text": p, "highlight": j in marked} for j, p in enumerate(paragraphs)],
        })
    return sources