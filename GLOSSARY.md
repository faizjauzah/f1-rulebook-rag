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

### Evaluation

**Reference answer**:
The human-verified ideal answer to an evaluation question. Written as plain prose without citation markers; the clauses it relies on are recorded separately.
_Avoid_: Gold answer, expected output, target

**Reference clause**:
A clause code a correct answer must rely on, written as it appears in the regulations, e.g. `C4.1`. Used to check retrieval without a judge.
_Avoid_: Expected source, ground-truth chunk

**Judge**:
The chat model that scores an evaluation run. It is not the generator: it runs after generation, in a separate phase, and may be a stronger model.
_Avoid_: Critic, scorer, evaluator model

**Evaluation context**:
The text of one source as handed to a metric. One context per source; never a paragraph or a chunk.
_Avoid_: Document, passage

**Evaluation run**:
One collection of answers and one scoring pass under a fixed generator, judge and retrieval configuration.
_Avoid_: Test, benchmark (for a single run)

**Baseline**:
The evaluation run that later runs are compared against, together with the noise measured on this machine.
_Avoid_: Reference run, golden run

**Faithfulness**:
The share of claims in an answer that the retrieved sources support.
_Avoid_: Accuracy, groundedness score

**Context recall**:
The share of the reference answer's claims that the retrieved sources cover.
_Avoid_: Retrieval accuracy, hit rate

**Context precision**:
How highly the retrieved sources rank the ones that actually support the reference answer.
_Avoid_: Relevance

**Answer correctness**:
Agreement between an answer and its reference answer, combining factual overlap and semantic similarity.
_Avoid_: Score, grade
