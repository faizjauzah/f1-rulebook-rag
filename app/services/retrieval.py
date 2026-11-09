"""
Retrieval service: vector search over ChromaDB + user-friendly source building.

retrieve_chunks() returns a list of *sources* (one per regulation clause, not per
chunk). Every item looks like this:

    {
        "ref": 1,                                   # 1-based number, matches [Source 1] in the prompt
        "id": "chunk_17",                           # first chunk id (debugging)
        "chunk_ids": ["chunk_17", "chunk_18"],      # all chunks merged into this source
        "label": "Article C4.1 – Minimum Mass",
        "section_label": "Section C [Technical]",
        "parent_label": "Article C4: Mass",
        "page": 59,
        "issue": "21",
        "date": "2026-10-01",
        "citation": "Section C [Technical] · Article C4.1 – Minimum Mass · p. 59 · Issue 21 (2026-10-01)",
        "text": "Full clause text (internal prefixes removed, parts merged) - sent to the LLM",
        "paragraphs": ["C4.1.1 The minimum mass ...", "C4.1.2 ..."],   # same text, reflowed for display
        "similarity": 0.83,                         # 1.0 for direct article-number matches
        "match": "semantic" | "article_number",
        "truncated": False,                         # True if a very long clause was cut
        "metadata": {...},                          # raw metadata of the first part
    }

filter_by_threshold() keeps its name and signature.
"""
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

import chromadb

from app.config import config
from app.services.ingestion import get_embeddings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tunables
# ---------------------------------------------------------------------------
CANDIDATE_MULTIPLIER = 3      # fetch top_k * 3 chunks, because several chunks collapse into one clause
MAX_DIRECT_SOURCES = 2        # max sources coming from an explicit article number in the question
MAX_PARTS_PER_SOURCE = 4      # a clause is split into ~1000-char parts; lower this if your LLM context is small

_QUERY_INCLUDE = ["documents", "metadatas", "distances"]
_GET_INCLUDE = ["documents", "metadatas"]


# ---------------------------------------------------------------------------
# ChromaDB access
# ---------------------------------------------------------------------------
_client = None


def _get_client():
    """Reuse one HTTP client. (The collection is NOT cached: /ingest recreates it.)"""
    global _client
    if _client is None:
        try:
            _client = chromadb.HttpClient(host=config.chroma_host, port=config.chroma_port)
        except Exception as e:
            raise RuntimeError(
                f"Cannot connect to ChromaDB at {config.chroma_host}:{config.chroma_port}: {e}"
            ) from e
    return _client


def _get_collection():
    name = config.collection_name
    client = _get_client()
    try:
        return client.get_collection(name=name)
    except Exception as e:
        msg = str(e).lower()
        missing = (
            "does not exist" in msg
            or "not found" in msg
            or type(e).__name__ in {"NotFoundError", "InvalidCollectionException"}
        )
        if missing:
            logger.error(f"Collection {name} not found: {e}")
            # routes.py turns ValueError into HTTP 400
            raise ValueError(f"Collection '{name}' not found. Please run /ingest first.") from e
        # Anything else (server down, timeout, ...) is NOT a missing collection
        raise RuntimeError(f"ChromaDB error while opening collection '{name}': {e}") from e


def _rows_from_query(results: Dict[str, Any]) -> List[Dict[str, Any]]:
    ids = (results.get("ids") or [[]])[0]
    docs = (results.get("documents") or [[]])[0]
    metas = (results.get("metadatas") or [[]])[0]
    dists = (results.get("distances") or [[]])[0]

    rows = []
    for i, chunk_id in enumerate(ids):
        distance = dists[i] if i < len(dists) else None
        # Collection uses cosine distance, so similarity = 1 - distance.
        # Missing distance means "unknown", never "perfect match".
        similarity = 1 - distance if distance is not None else 0.0
        rows.append({
            "id": chunk_id,
            "text": (docs[i] or "") if i < len(docs) else "",
            "metadata": (metas[i] or {}) if i < len(metas) else {},
            "similarity": similarity,
        })
    return rows


def _rows_from_get(results: Dict[str, Any]) -> List[Dict[str, Any]]:
    ids = results.get("ids") or []
    docs = results.get("documents") or []
    metas = results.get("metadatas") or []
    return [
        {
            "id": chunk_id,
            "text": (docs[i] or "") if i < len(docs) else "",
            "metadata": (metas[i] or {}) if i < len(metas) else {},
            "similarity": 0.0,
        }
        for i, chunk_id in enumerate(ids)
    ]


# ---------------------------------------------------------------------------
# Direct lookup by article number ("what does C3.5.2 say?")
# ---------------------------------------------------------------------------
# A dotted code (C3.5.2) is always treated as an article number. A bare code (C3) only
# counts after the word "article", so "F1" (Formula 1) is never mistaken for Article F1.
_CLAUSE_CODE_RE = re.compile(r"\b([A-F]\d+(?:\.\d+)+)\b", re.IGNORECASE)
_ARTICLE_CODE_RE = re.compile(r"\barticles?\s+([A-F]\d+(?:\.\d+)*)\b", re.IGNORECASE)


def extract_article_codes(question: str) -> List[str]:
    found = []
    for rx in (_ARTICLE_CODE_RE, _CLAUSE_CODE_RE):
        for m in rx.finditer(question):
            found.append((m.start(1), m.group(1).upper()))
    codes: List[str] = []
    for _, code in sorted(found):
        if code not in codes:
            codes.append(code)
    return codes


def _lookup_by_article(collection, codes: List[str]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for code in codes:
        try:
            res = collection.get(where={"article": code}, include=_GET_INCLUDE)
        except Exception as e:
            logger.warning(f"Direct lookup for {code} failed: {e}")
            continue
        found = _rows_from_get(res)
        logger.info(f"Direct lookup {code}: {len(found)} chunks")
        rows.extend(found)
    return rows


# ---------------------------------------------------------------------------
# Text cleanup
# ---------------------------------------------------------------------------
_CONTEXT_LINE_RE = re.compile(r"^\[[^\]\n]*\]\n")  # "[C3: TECHNICAL REGULATIONS]\n" added by ingestion
_PAGE_NUMBER_LINE_RE = re.compile(r"^\d{1,3}$")
_BARE_CLAUSE_LINE_RE = re.compile(r"^[A-F]\d+(?:\.\d+)+$")
# Start of a new paragraph: "C4.1.2 ...", "a) ...", "(2) ...", "• ..."
_PARA_START_RE = re.compile(r"^(?:[A-F]\d+(?:\.\d+)+(?:\s|$)|\(?(?:[a-z]|\d{1,2})\)\s|[•▪●-]\s)")


def _clean_part(text: str) -> str:
    """Remove the internal context line and the '<heading> (continued)' line."""
    body = _CONTEXT_LINE_RE.sub("", text, count=1)
    first, _, rest = body.partition("\n")
    if first.rstrip().endswith("(continued)"):
        return rest.strip()
    return body.strip()


def _looks_like_toc(text: str) -> bool:
    """
    Table-of-contents text: the PDF puts every cell on its own line, giving
    'C4.1' / 'Minimum mass' / '59' / 'C4.2' / ... (many bare page numbers AND bare clause codes).
    Both conditions are required so real tables of numbers are not dropped.
    """
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    if len(lines) < 6:
        return False
    numbers = sum(1 for l in lines if _PAGE_NUMBER_LINE_RE.match(l))
    codes = sum(1 for l in lines if _BARE_CLAUSE_LINE_RE.match(l))
    return numbers >= 4 and codes >= 3 and numbers / len(lines) >= 0.2


def _is_junk(row: Dict[str, Any]) -> bool:
    return _looks_like_toc(_clean_part(row["text"]))


def _join_overlapping(pieces: List[str]) -> str:
    """Join consecutive parts, dropping the ~120-char overlap added by split_text()."""
    merged = pieces[0]
    for nxt in pieces[1:]:
        overlap = 0
        for size in range(min(len(merged), len(nxt), 400), 19, -1):
            if merged.endswith(nxt[:size]):
                overlap = size
                break
        merged += nxt[overlap:] if overlap else "\n" + nxt
    return merged


def _split_paragraphs(text: str) -> List[str]:
    """Reflow hard-wrapped PDF lines into paragraphs (a new one starts at a clause number or list marker)."""
    paragraphs: List[str] = []
    current: List[str] = []
    for raw in text.split("\n"):
        line = raw.strip()
        if not line:
            continue
        if current and _PARA_START_RE.match(line):
            paragraphs.append(" ".join(current))
            current = []
        current.append(line)
    if current:
        paragraphs.append(" ".join(current))
    return paragraphs


_ACRONYMS = {"FIA", "F1", "DRS", "ERS", "MGU-K", "MGU-H", "PU", "ICE", "ECU", "FOM", "TV", "CFD", "FOA"}
_SMALL_WORDS = {"AND", "OF", "THE", "FOR", "IN", "ON", "TO", "OR", "AT", "BY"}


def _nice_title(title: Optional[str]) -> str:
    """'GENERAL PRINCIPLES' -> 'General Principles'. Mixed-case titles are left alone."""
    title = (title or "").strip()
    if not title or not title.isupper():
        return title
    words = []
    for i, w in enumerate(title.split()):
        if w in _ACRONYMS:
            words.append(w)
        elif w in _SMALL_WORDS and i > 0:
            words.append(w.lower())
        else:
            words.append(w.capitalize())
    return " ".join(words)


def _build_labels(meta: Dict[str, Any]) -> Dict[str, str]:
    article = str(meta.get("article") or "").strip()
    title = _nice_title(meta.get("article_title"))
    parent = str(meta.get("parent_article") or "").strip()
    parent_title = _nice_title(meta.get("parent_title"))
    section = meta.get("section")
    section_name = meta.get("section_name")
    page = meta.get("page")
    issue = meta.get("issue")
    date = meta.get("date")

    label = f"Article {article}" if article else "Unknown article"
    if title:
        label += f" – {title}"

    section_label = ""
    if section:
        section_label = f"Section {section}" + (f" [{section_name}]" if section_name else "")

    parent_label = ""
    if parent and parent != article:
        parent_label = f"Article {parent}" + (f": {parent_title}" if parent_title else "")

    issue_label = ""
    if issue:
        issue_label = f"Issue {issue}" + (f" ({date})" if date else "")

    parts = [
        section_label or str(meta.get("doc_title", "")),
        label,
        f"p. {page}" if page else "",
        issue_label,
    ]
    return {
        "label": label,
        "section_label": section_label,
        "parent_label": parent_label,
        "citation": " · ".join(p for p in parts if p),
    }


# ---------------------------------------------------------------------------
# Grouping chunks into clauses
# ---------------------------------------------------------------------------
# A clause = same document + same article code + same start page. The page is part of the key
# so the table-of-contents entry for an article is never merged with the article body.
GroupKey = Tuple[str, str, Optional[int]]


def _page_of(meta: Dict[str, Any]) -> Optional[int]:
    try:
        return int(meta.get("page"))
    except (TypeError, ValueError):
        return None


def _group_key(meta: Dict[str, Any]) -> GroupKey:
    return (str(meta.get("doc_title", "")), str(meta.get("article", "")), _page_of(meta))


def _part_no(row: Dict[str, Any]) -> int:
    try:
        return int(row["metadata"].get("part", 1))
    except (TypeError, ValueError):
        return 1


def _expand_clauses(collection, keys: List[GroupKey]) -> Dict[GroupKey, List[Dict[str, Any]]]:
    """Fetch ALL parts of the given clauses, so a source never starts mid-clause."""
    if not keys:
        return {}
    conditions = []
    for doc_title, article, page in keys:
        parts = [{"doc_title": doc_title}, {"article": article}]
        if page is not None:
            parts.append({"page": page})
        conditions.append({"$and": parts})
    where = conditions[0] if len(conditions) == 1 else {"$or": conditions}
    try:
        res = collection.get(where=where, include=_GET_INCLUDE)
    except Exception as e:
        logger.warning(f"Clause expansion failed, using retrieved parts only: {e}")
        return {}

    expanded: Dict[GroupKey, List[Dict[str, Any]]] = {}
    for row in _rows_from_get(res):
        expanded.setdefault(_group_key(row["metadata"]), []).append(row)
    return expanded


def _build_source(rows: List[Dict[str, Any]], similarity: float, match: str) -> Optional[Dict[str, Any]]:
    rows = sorted(rows, key=_part_no)

    kept = []
    for r in rows:
        piece = _clean_part(r["text"])
        if piece and not _looks_like_toc(piece):
            kept.append((r, piece))
    if not kept:
        return None  # nothing but table-of-contents text

    truncated = len(kept) > MAX_PARTS_PER_SOURCE
    kept = kept[:MAX_PARTS_PER_SOURCE]

    text = _join_overlapping([piece for _, piece in kept])
    meta = dict(kept[0][0]["metadata"])
    article = str(meta.get("article") or "")

    # First line is the clause heading ("C4.1 Minimum mass"): the card title already shows it,
    # so the displayed paragraphs start after it. `text` (for the LLM) keeps it.
    first_line, _, rest = text.partition("\n")
    body = rest if (article and first_line.startswith(article) and rest.strip()) else text

    return {
        "ref": 0,  # assigned after sorting / filtering
        "id": kept[0][0]["id"],
        "chunk_ids": [r["id"] for r, _ in kept],
        **_build_labels(meta),
        "page": meta.get("page"),
        "issue": meta.get("issue"),
        "date": meta.get("date"),
        "text": text,
        "paragraphs": _split_paragraphs(body),
        "similarity": similarity,
        "match": match,
        "truncated": truncated,
        "metadata": meta,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def retrieve_chunks(question: str) -> List[Dict[str, Any]]:
    """Retrieve relevant regulation clauses (sources) from ChromaDB."""
    logger.info(f"Retrieving chunks for question: {question}")

    collection = _get_collection()
    top_k = max(int(config.top_k), 1)

    # 1. Explicit article numbers in the question (C3.5.2, "Article C3", ...)
    codes = extract_article_codes(question)
    direct_rows = _lookup_by_article(collection, codes) if codes else []

    # 2. Semantic search
    query_embedding = get_embeddings([question], is_query=True)[0]
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k * CANDIDATE_MULTIPLIER,
        include=_QUERY_INCLUDE,
    )
    semantic_rows = _rows_from_query(results)

    # Drop table-of-contents chunks before they can outrank real content
    n_before = len(direct_rows) + len(semantic_rows)
    direct_rows = [r for r in direct_rows if not _is_junk(r)]
    semantic_rows = [r for r in semantic_rows if not _is_junk(r)]
    dropped = n_before - len(direct_rows) - len(semantic_rows)
    if dropped:
        logger.info(f"Dropped {dropped} table-of-contents chunks")

    # 3. Group chunks by clause. Direct matches first (capped), then semantic ones.
    groups: Dict[GroupKey, Dict[str, Any]] = {}

    direct_keys: List[GroupKey] = []
    for row in direct_rows:
        key = _group_key(row["metadata"])
        if key not in direct_keys:
            direct_keys.append(key)
    direct_keys = direct_keys[:MAX_DIRECT_SOURCES]

    for row in direct_rows:
        key = _group_key(row["metadata"])
        if key not in direct_keys:
            continue
        g = groups.setdefault(key, {"rows": {}, "similarity": 1.0, "match": "article_number"})
        g["rows"][row["id"]] = row

    for row in semantic_rows:
        key = _group_key(row["metadata"])
        g = groups.setdefault(key, {"rows": {}, "similarity": 0.0, "match": "semantic"})
        g["rows"][row["id"]] = row
        g["similarity"] = max(g["similarity"], row["similarity"])

    ordered = sorted(
        groups.items(),
        key=lambda kv: (kv[1]["match"] != "article_number", -kv[1]["similarity"]),
    )[:top_k]

    # 4. Pull in the remaining parts of each clause so the source is complete
    expanded = _expand_clauses(collection, [key for key, _ in ordered])

    sources = []
    for key, g in ordered:
        rows = expanded.get(key) or list(g["rows"].values())
        source = _build_source(rows, g["similarity"], g["match"])
        if source:
            sources.append(source)
    for i, s in enumerate(sources, start=1):
        s["ref"] = i

    logger.info(
        f"Retrieved {len(semantic_rows)} chunks -> {len(sources)} sources"
        f" ({len(direct_keys)} from article numbers)"
    )
    return sources


def filter_by_threshold(chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Filter sources by similarity threshold and renumber `ref` so there are no gaps."""
    kept = [dict(c) for c in chunks if c["similarity"] >= config.similarity_threshold]
    for i, c in enumerate(kept, start=1):
        c["ref"] = i
    logger.info(f"Filtered to {len(kept)} sources above threshold {config.similarity_threshold}")
    return kept