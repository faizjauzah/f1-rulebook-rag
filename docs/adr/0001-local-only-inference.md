# Local-only inference: no cloud providers

The project originally supported a Gemini cloud profile and a local profile behind a `profile:` switch. We removed the cloud path entirely: embeddings and generation now come from one OpenAI-compatible local server, `config.yaml` has a single flat shape, and `app/config.py` refuses to start with a non-local `base_url` so the OpenAI SDK can never fall back to `api.openai.com`. The motivation is that "fully local" must be a property the code enforces, not a configuration a user remembers to pick — and the cloud path was already broken (it imported a removed SDK) while its API key, rate-limit retries and second vector collection multiplied everything that needed testing.

## Considered Options

- **Keep both profiles.** Rejected: two dispatch sites, two collections, two sets of docs, a live API key, and a cloud branch that no longer imported a shipped dependency.
- **Keep cloud behind an environment flag.** Rejected: the same egress risk with less testing; a flag is not a guarantee.
- **Support only LM Studio.** Rejected: constraining the endpoint to a local address keeps the privacy guarantee while still allowing Ollama, llama.cpp, vLLM, or a server on the LAN.

## Consequences

- Answer quality is capped by the local model you load; the eval numbers describe your hardware, not a hosted model.
- The app can no longer be deployed to a cloud host without changing `config.yaml` to a LAN-accessible server — which the guard allows, but the reasoning above still applies.
- `f1-regs-local` was replaced by `f1-regs`; changing the embedding model invalidates the collection and requires re-ingestion.
- Any future cloud support must supersede this ADR, not just add a branch.
