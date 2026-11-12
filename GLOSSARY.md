# F1 Rulebook RAG

A retrieval system over the 2026 FIA Formula 1 Regulations. It answers questions by finding the regulation clauses that bear on them and citing those clauses rather than paraphrasing from memory.

## Language

### Regulation documents

**Section**:
One of the six PDFs that make up the regulations (A–F: General Provisions, Sporting, Technical, Financial for teams, Financial for power unit manufacturers, Operational).
_Avoid_: Chapter, volume, part

**Article**:
A top-level numbered block inside a section, written `ARTICLE C4: MASS`.
_Avoid_: Heading, section (for this level)

**Clause**:
A numbered provision inside an article, written `C4.1` or `C4.1.2`. The unit that retrieval works in and that answers cite.
_Avoid_: Paragraph (reserved for display), item, rule

**Part**:
A subdivision of a clause created at ingestion time when the clause is too long to embed as one chunk. Parts of a clause are always merged back before being shown or cited.

**Chunk**:
One embedded unit stored in the vector store. Today a chunk is one clause part; it is an implementation detail, not a domain term.

### Retrieval and answers

**Source**:
A clause presented to the user as evidence, with its section, page, issue and full text. One source can be assembled from several chunks.
_Avoid_: Result, hit, excerpt

**Ref**:
The 1-based number in square brackets that ties an answer sentence to a source, e.g. `[2]`. Renumbered with no gaps after filtering.

**Match**:
How a source was found: `article_number` when the question named a clause code, `semantic` when vector similarity found it.

**Similarity**:
`1 - cosine distance` between the question embedding and a chunk embedding. Compared against a threshold to decide whether a source is relevant at all.

**Highlight**:
The paragraph within a source that the heuristic judges to support the answer. A display aid, not a claim of citation.

**Cited**:
True when a source's ref appears in the answer text. Distinct from highlight: a source can be retrieved and highlighted but never cited.

**Truncated**:
True when a clause exceeded `MAX_SOURCE_CHARS` and the source text was cut.

### Inference

**Local server**:
The OpenAI-compatible HTTP endpoint that serves both the embedding model and the chat model. LM Studio by default; Ollama, llama.cpp or vLLM also fit.
_Avoid_: Provider, backend, engine

**Cloud**:
Any inference endpoint outside the machine or its private network. Not supported: the app refuses to start with one.
