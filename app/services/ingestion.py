import os
import re
import time
import logging
from typing import List, Dict, Any

import fitz  # pymupdf
import chromadb
from openai import OpenAI

from app.config import config

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tunables (override with env vars if needed)
# ---------------------------------------------------------------------------
MAX_CHARS = int(os.getenv("MAX_CHUNK_CHARS", "500"))      # ~250-350 tokens; lower to 700 if the embedder still errors
OVERLAP = int(os.getenv("CHUNK_OVERLAP_CHARS", "120"))
MIN_CHARS = int(os.getenv("MIN_CHUNK_CHARS", "200"))       # smaller sections get merged into the next one
LOCAL_EMBED_BATCH = int(os.getenv("LOCAL_EMBED_BATCH", "16"))

# Prefixes for the LOCAL embedding model (check your model card), e.g.
#   nomic:        EMBED_QUERY_PREFIX="search_query: "   EMBED_DOC_PREFIX="search_document: "
#   EmbeddingGemma: EMBED_QUERY_PREFIX="task: search result | query: "   EMBED_DOC_PREFIX="title: none | text: "
#   bge / most others: leave both empty
QUERY_PREFIX = os.getenv("EMBED_QUERY_PREFIX", "")
DOC_PREFIX = os.getenv("EMBED_DOC_PREFIX", "")

# ---------------------------------------------------------------------------
# Filename metadata
# ---------------------------------------------------------------------------
def extract_metadata_from_filename(filename: str) -> Dict[str, Any]:
    """Extract section info from PDF filename."""
    # Example: "FIA 2026 F1 Regulations - Section B [Sporting] - Iss 09 - 2026-10-01.pdf"
    pattern = r"Section ([A-F]) \[([^\]]+)\].*Iss (\d+).*(\d{4}-\d{2}-\d{2})"
    match = re.search(pattern, filename)

    if match:
        return {
            "section": match.group(1),
            "section_name": match.group(2),
            "issue": match.group(3),
            "date": match.group(4),
            "doc_title": filename.replace(".pdf", ""),
        }
    return {"doc_title": filename.replace(".pdf", "")}


# ---------------------------------------------------------------------------
# PDF parsing
# ---------------------------------------------------------------------------
ARTICLE_RE = re.compile(r"^ARTICLE\s+([A-F]\d+):\s+(.+)$")        # ARTICLE C1: GENERAL PRINCIPLES
CLAUSE_RE = re.compile(r"^([A-F]\d+(?:\.\d+)+)\s+(\S.*)$")        # C3.5.2 Floor Foot
TOC_LINE_RE = re.compile(r"^(?:ARTICLE\s+)?[A-F]\d+(?:\.\d+)*:?\s.*\s\d{1,3}$")  # ends with a page number

NOISE_RES = [
    re.compile(r"^SECTION [A-F]: [A-Z ]+$"),                                          # running page header
    re.compile(r"^[A-F]\d+ \d{4} Formula 1 Regulations - Section [A-F] \[[^\]]+\]$"),  # running footer
    re.compile(r"^©\s?\d{4}\s.*Automobile$"),                                          # copyright
    re.compile(r"^\d{1,2} [A-Za-z]+ \d{4}$"),                                          # 19 October 2026
    re.compile(r"^Issue \d+$"),
    re.compile(r"^[A-F]\d+$"),                                                         # stray "C0"
    re.compile(r"^Advisory Committee:"),                                               # governance notes
    re.compile(r"^Governance:"),
]

# The PDF font loses the "fi"/"ff"/"ffi" ligature glyphs ("specifcally", "efect", "defned", "fve").
# (pattern, replacement) pairs; case of the first letter is preserved.
_LIGATURE_FIXES = [
    (r"specifc", "specific"), (r"clarifc", "clarific"), (r"defn", "defin"),
    (r"\bfve\b", "five"), (r"\bfnal", "final"), (r"\bfrst\b", "first"),
    (r"\bfnish", "finish"), (r"\bfx", "fix"), (r"\bftt", "fitt"), (r"\bfgure", "figure"),
    (r"efect", "effect"), (r"afect", "affect"), (r"difer", "differ"),
    (r"difcult", "difficult"), (r"ofcial", "official"), (r"sufcient", "sufficient"),
    (r"efcient", "efficient"), (r"signifc", "signific"), (r"modifc", "modific"),
    (r"identifc", "identific"), (r"notifc", "notific"), (r"classifc", "classific"),
    (r"verifc", "verific"), (r"qualifc", "qualific"), (r"certifc", "certific"),
]
LIGATURE_FIXES = [(re.compile(p, re.IGNORECASE), r) for p, r in _LIGATURE_FIXES]


def _match_case(src: str, repl: str) -> str:
    if len(src) > 1 and src.isupper():
        return repl.upper()
    if src[0].isupper():
        return repl[0].upper() + repl[1:]
    return repl


def clean_line(line: str) -> str:
    line = line.replace("\u2212", "-")          # "re−numbering" -> "re-numbering"
    line = re.sub(r"\s+", " ", line).strip()
    for pat, repl in LIGATURE_FIXES:
        line = pat.sub(lambda m, r=repl: _match_case(m.group(0), r), line)
    return line


def is_noise(line: str) -> bool:
    return any(r.match(line) for r in NOISE_RES)


BARE_CLAUSE_RE = re.compile(r"^[A-F]\d+(?:\.\d+)+$")   # "C4.1" alone on a line
PAGE_NO_RE = re.compile(r"^\d{1,3}$")                  # "59" alone on a line


def is_toc_page(lines: List[str]) -> bool:
    # Style 1: "C4.1 Minimum mass 59" on one line
    if sum(1 for l in lines if TOC_LINE_RE.match(l)) >= 3:
        return True
    # Style 2: the PDF puts every table cell on its own line: "C4.1" / "Minimum mass" / "59"
    triplets = sum(
        1 for i in range(len(lines) - 2)
        if BARE_CLAUSE_RE.match(lines[i]) and PAGE_NO_RE.match(lines[i + 2])
    )
    return triplets >= 3


def join_split_headings(lines: List[str]) -> List[str]:
    """
    Body headings are also split over two lines: "C4.1" / "Minimum mass".
    Join them so CLAUSE_RE can see "C4.1 Minimum mass" and start a new clause.
    """
    out: List[str] = []
    i = 0
    while i < len(lines):
        if (
            BARE_CLAUSE_RE.match(lines[i])
            and i + 1 < len(lines)
            and looks_like_title(lines[i + 1])
            and not PAGE_NO_RE.match(lines[i + 1])
        ):
            out.append(f"{lines[i]} {lines[i + 1]}")
            i += 2
        else:
            out.append(lines[i])
            i += 1
    return out


def looks_like_title(text: str) -> bool:
    """A clause title is short, starts with a capital/digit, and has no sentence punctuation."""
    return (
        len(text) <= 90
        and (text[0].isupper() or text[0].isdigit())
        and not text.endswith((".", ",", ";", ":"))
    )


def split_text(text: str, limit: int) -> List[str]:
    """Split long text on line/sentence boundaries with a small overlap."""
    limit = max(limit, 300)
    if len(text) <= limit:
        return [text]

    parts, start = [], 0
    while start < len(text):
        end = min(start + limit, len(text))
        if end < len(text):
            cut = text.rfind("\n", start + limit // 2, end)
            if cut == -1:
                cut = text.rfind(". ", start + limit // 2, end)
            if cut != -1:
                end = cut + 1
        piece = text[start:end].strip()
        if piece:
            parts.append(piece)
        if end >= len(text):
            break
        start = max(end - OVERLAP, start + 1)
        ws = text.find(" ", start, end)      # don't start mid-word
        if ws != -1:
            start = ws + 1
    return parts


def _new_section(article, article_title, clause, title, page):
    return {
        "article": article, "article_title": article_title,
        "clause": clause, "title": title, "page": page, "lines": [],
    }


def extract_chunks_from_pdf(pdf_path: str) -> List[Dict[str, Any]]:
    """Chunk a regulations PDF by clause (C1.1, C3.5.2, ...), splitting oversized clauses."""
    base = extract_metadata_from_filename(os.path.basename(pdf_path))
    doc = fitz.open(pdf_path)

    sections: List[Dict[str, Any]] = []
    cur = None
    article_id, article_title = "", ""
    seen_clauses = set()

    for page_num, page in enumerate(doc, start=1):
        lines = [clean_line(l) for l in page.get_text().split("\n")]
        lines = [l for l in lines if l and not is_noise(l)]
        if is_toc_page(lines):
            continue
        lines = join_split_headings(lines)

        for line in lines:
            m = ARTICLE_RE.match(line)
            if m:
                article_id, article_title = m.group(1), m.group(2).strip()
                cur = _new_section(article_id, article_title, article_id, article_title, page_num)
                sections.append(cur)
                continue

            m = CLAUSE_RE.match(line)
            if m and article_id:
                clause, rest = m.group(1), m.group(2).strip()
                if (
                    clause.startswith(article_id + ".")   # belongs to the current article
                    and clause not in seen_clauses        # not a repeated cross-reference
                    and looks_like_title(rest)            # header line, not wrapped body text
                ):
                    seen_clauses.add(clause)
                    cur = _new_section(article_id, article_title, clause, rest, page_num)
                    sections.append(cur)
                    continue

            if cur:   # text before the first article (cover page) is dropped
                cur["lines"].append(line)

    doc.close()

    # Build chunks: merge tiny sections into the next one, split oversized ones
    chunks: List[Dict[str, Any]] = []
    carry = ""
    for i, s in enumerate(sections):
        heading = f"{s['clause']} {s['title']}".strip()
        body = "\n".join(s["lines"]).strip()
        text = "\n".join(x for x in (carry, heading, body) if x).strip()
        carry = ""

        nxt = sections[i + 1] if i + 1 < len(sections) else None
        if len(text) < MIN_CHARS and nxt and nxt["article"] == s["article"]:
            carry = text
            continue

        context = f"[{s['article']}: {s['article_title']}]"
        limit = MAX_CHARS - len(context) - len(heading) - 20

        for j, piece in enumerate(split_text(text, limit), start=1):
            if j > 1:
                piece = f"{heading} (continued)\n{piece}"
            chunks.append({
                "text": f"{context}\n{piece}",
                "metadata": {
                    **base,
                    "article": s["clause"],
                    "article_title": s["title"] or "",        # never None
                    "parent_article": s["article"],
                    "parent_title": s["article_title"] or "",
                    "page": s["page"],
                    "part": j,
                },
            })
    return chunks


# ---------------------------------------------------------------------------
# Embeddings
# ---------------------------------------------------------------------------
def get_embeddings(
    texts: List[str],
    is_query: bool = False
) -> List[List[float]]:
    """Generate embeddings with Gemini rate-limit protection or a local OpenAI-compatible server."""

    if config.embedding_provider == "gemini":
        from google import genai

        client = genai.Client(api_key=config.google_api_key)
        embeddings = []

        for i, text in enumerate(texts):
            if is_query:
                content = f"task: search result | query: {text}"
            else:
                content = f"title: FIA Formula One Regulations | text: {text}"

            # Stay below the free-tier limit of 100 requests/minute.
            if i > 0:
                time.sleep(0.7)

            # Retry if Gemini temporarily rejects the request.
            for attempt in range(5):
                try:
                    result = client.models.embed_content(
                        model=config.embedding_model,
                        contents=content
                    )
                    embeddings.append(result.embeddings[0].values)
                    break

                except Exception as e:
                    if "429" not in str(e):
                        raise
                    if attempt == 4:
                        raise

                    wait_time = 45 * (attempt + 1)
                    logger.warning(f"Rate limit reached. Retrying in {wait_time} seconds...")
                    time.sleep(wait_time)

            if (i + 1) % 25 == 0:
                logger.info(f"Generated {i + 1}/{len(texts)} embeddings")

        return embeddings

    elif config.embedding_provider == "local":
        client = OpenAI(
            base_url=config.embedding_base_url,
            api_key="lm-studio"
        )
        prefix = QUERY_PREFIX if is_query else DOC_PREFIX
        embeddings: List[List[float]] = []

        for start in range(0, len(texts), LOCAL_EMBED_BATCH):
            batch = [prefix + t for t in texts[start:start + LOCAL_EMBED_BATCH]]
            response = client.embeddings.create(
                model=config.embedding_model,
                input=batch
            )
            data = sorted(response.data, key=lambda d: d.index)
            embeddings.extend(item.embedding for item in data)

            done = min(start + LOCAL_EMBED_BATCH, len(texts))
            if (start // LOCAL_EMBED_BATCH) % 10 == 0:
                logger.info(f"Generated {done}/{len(texts)} embeddings")

        return embeddings

    else:
        raise ValueError(f"Unknown embedding provider: {config.embedding_provider}")


# ---------------------------------------------------------------------------
# Ingestion
# ---------------------------------------------------------------------------
def clean_metadata(meta: Dict[str, Any]) -> Dict[str, Any]:
    """Chroma only accepts str/int/float/bool: drop None, stringify anything else."""
    cleaned = {}
    for k, v in meta.items():
        if v is None:
            continue
        cleaned[k] = v if isinstance(v, (str, int, float, bool)) else str(v)
    return cleaned


def ingest_pdfs() -> Dict[str, Any]:
    """Ingest all PDFs into ChromaDB."""
    logger.info(f"Starting ingestion for collection: {config.collection_name}")

    # 1. Parse PDFs
    all_chunks: List[Dict[str, Any]] = []
    pdf_files = sorted(f for f in os.listdir(config.pdf_directory) if f.lower().endswith(".pdf"))

    for pdf_file in pdf_files:
        logger.info(f"Processing {pdf_file}...")
        chunks = extract_chunks_from_pdf(os.path.join(config.pdf_directory, pdf_file))
        all_chunks.extend(chunks)
        logger.info(f"Extracted {len(chunks)} chunks from {pdf_file}")

    if not all_chunks:
        return {
            "status": "error",
            "message": "No chunks extracted from PDFs",
            "chunks_created": 0,
            "collection": config.collection_name,
        }

    lengths = [len(c["text"]) for c in all_chunks]
    logger.info(f"Chunk length (chars): min={min(lengths)}, max={max(lengths)}, avg={sum(lengths)//len(lengths)}")

    # 2. Embed BEFORE touching the existing collection, so a failure doesn't wipe your data
    logger.info(f"Generating embeddings for {len(all_chunks)} chunks...")
    texts = [c["text"] for c in all_chunks]
    embeddings = get_embeddings(texts)

    # 3. Recreate collection (cosine distance, so similarity = 1 - distance is correct)
    client = chromadb.HttpClient(host=config.chroma_host, port=config.chroma_port)
    try:
        client.delete_collection(name=config.collection_name)
        logger.info(f"Deleted existing collection {config.collection_name}")
    except Exception:
        pass

    collection = client.create_collection(
        name=config.collection_name,
        metadata={"hnsw:space": "cosine"},
    )

    # 4. Add in batches (Chroma has a max batch size)
    ids = [f"chunk_{i}" for i in range(len(all_chunks))]
    metadatas = [clean_metadata(c["metadata"]) for c in all_chunks]

    try:
        batch_size = min(int(client.get_max_batch_size()), 500)
    except Exception:
        batch_size = 500

    logger.info("Adding chunks to ChromaDB...")
    for start in range(0, len(ids), batch_size):
        end = start + batch_size
        collection.add(
            ids=ids[start:end],
            embeddings=embeddings[start:end],
            documents=texts[start:end],
            metadatas=metadatas[start:end],
        )

    logger.info(f"Ingestion complete: {len(all_chunks)} chunks added to {config.collection_name}")

    return {
        "status": "success",
        "message": f"Successfully ingested {len(pdf_files)} PDFs",
        "chunks_created": len(all_chunks),
        "collection": config.collection_name,
    }