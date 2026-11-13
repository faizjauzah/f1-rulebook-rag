# Evaluate with RAGAS, a local judge, and a two-phase run

The evaluation suite used to be a latency harness: it recorded completion, response time and source counts, then discarded the sources it had retrieved. Nothing was scored, so the only question it could answer was "is the API up", not "is the answer any good". Evaluation is now a RAGAS suite with human-verified ground truth, a local judge, deterministic retrieval and citation checks, and a per-run report that separates retrieval quality from generation quality.

The suite runs in two phases because the machine cannot hold two chat models at once. `collect` asks the running API the 30 questions with the generator loaded and saves answers, sources and latency. `score` reloads a stronger model as judge and scores the saved answers with RAGAS; the generator is no longer needed. `./run.sh eval` orchestrates the swap through the host `lms` CLI and restores the generator at the end. A one-model machine can still run a two-model evaluation, at the cost of one load per phase rather than true concurrency.

Three semantic choices are part of the decision, because each one silently changes every score:

- A RAGAS **context** is one **source** — the whole clause, including sources the answer did not cite. It is never a paragraph or a chunk. Scoring paragraphs measures display formatting; dropping uncited sources measures the model's citation habit instead of retrieval.
- Citation markers (`[1]`, `[2]`) are stripped before the judge sees an answer. They are provenance, not claims.
- Only questions marked `verified: true` enter the RAGAS aggregates. References are drafted from the regulation PDFs, never from the system's own answers, and are reviewed by a human before they count.

The project keeps one image. RAGAS brings LangChain, `datasets`, `tiktoken` and `pandas` into the runtime image, and forces `openai` to 2.x. `openai` is pinned `>=2.45,<3`: version 3 makes HTTPX2 the default client and stops installing `httpx`, while `app/services/local_client.py` passes an `httpx.Timeout`. That cap is a temporary coupling, not a preference.

## Considered Options

- **A separate evaluation image.** Rejected: it keeps the app image small and isolates RAGAS's dependency graph, but it adds a second build, a second set of pins and a second way for `./run.sh eval` to fail. The accepted cost is a larger app image and a shared `openai` pin.
- **A cloud judge.** Rejected by [ADR-0001](0001-local-only-inference.md). The whole point of the guard is that evaluation data never leaves the machine.
- **The generator as its own judge.** Rejected: a weaker model judging its own answers is the clearest case of self-preference, and it would make faithfulness scores look better than they are.
- **One context per paragraph.** Rejected: paragraph boundaries are a display decision, so the score would move when the UI changed.
- **Judge-free metrics only** (clause recall, citation validity, latency). Rejected as the *only* signal: they cannot tell whether an answer is correct or whether a cited clause actually supports it.
- **Fail the command when a score drops.** Rejected for now: with no baseline the threshold would be a guess, and local scores have a measurable noise floor. The suite is report-only until a baseline and its noise band exist.

## Consequences

- Scores describe this machine, this generator and this judge. They are not comparable across judge models, quantization levels or hardware, and the run record includes all three so a future reader can tell.
- The image grows substantially (LangChain, `datasets`, `tiktoken`, `pandas`). This is the price of one image.
- `openai` must stay below 3 until `local_client.py` migrates to HTTPX2. A future upgrade should supersede this ADR rather than silently float the pin.
- `ragas` is pinned because its judge prompts change between versions and a prompt change moves scores without any change to the system under test.
- Evaluation is no longer a single API call: `collect` and `score` are separate artefacts, and a run directory with raw samples is the unit of comparison.
- Answer correctness is only as good as the reference answers. A wrong or incomplete reference will produce a wrong score, which is why `verified` is part of the schema.
- The first baseline is run twice so the report can distinguish a real change from local sampling noise. Every later comparison inherits that noise band.
