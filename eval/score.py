"""Phase 2: score the saved answers with RAGAS and deterministic checks."""

from __future__ import annotations

import csv
import math
import platform
import re
from typing import Any, Dict, List, Optional

from eval.common import (
    RAGAS_METRICS,
    config_snapshot,
    fmt,
    load_questions,
    mean,
    median,
    read_jsonl,
    require_model_loaded,
    run_path,
    source_text,
    stdev,
    strip_citations,
    utc_now,
    write_json,
)

REFUSAL_RE = re.compile(
    r"(couldn'?t|could not|can'?t find|cannot find|no relevant|not (covered|specified|found)|"
    r"unable to find|not in the (provided )?regulations)",
    re.IGNORECASE,
)
CITATION_RE = re.compile(r"\[(\d+)\]")

RAGAS_COLUMNS = {
    "faithfulness": "faithfulness",
    "context_recall": "context_recall",
    "llm_context_precision_with_reference": "context_precision",
    "answer_correctness": "answer_correctness",
}


def clause_matches(expected: str, retrieved: str) -> bool:
    """C4.1 matches C4.1, C4.1.2 and itself; comparisons stay on dot boundaries."""
    expected = expected.strip().upper()
    retrieved = retrieved.strip().upper()
    if not expected or not retrieved:
        return False
    return (
        expected == retrieved
        or expected.startswith(retrieved + ".")
        or retrieved.startswith(expected + ".")
    )


def deterministic_metrics(question: Dict[str, Any], sample: Dict[str, Any]) -> Dict[str, Any]:
    sources = sample.get("sources") or []
    answer = sample.get("answer") or ""

    expected_clauses = [
        str(code).strip()
        for code in (question.get("reference_clauses") or [])
        if str(code).strip()
    ]
    expected_clauses = list(dict.fromkeys(expected_clauses))
    retrieved_codes = [
        str(source.get("article")).strip()
        for source in sources
        if source.get("article")
    ]
    found = [
        code
        for code in expected_clauses
        if any(clause_matches(code, retrieved) for retrieved in retrieved_codes)
    ]
    missing = [code for code in expected_clauses if code not in found]
    clause_recall = (len(found) / len(expected_clauses)) if expected_clauses else None

    refs = [int(value) for value in CITATION_RE.findall(answer)]
    citations_resolve = all(1 <= ref <= len(sources) for ref in refs)
    cited_sources = sum(1 for source in sources if source.get("cited"))
    cited_ratio = (cited_sources / len(sources)) if sources else 0.0

    return {
        "clause_recall": clause_recall,
        "reference_clauses": expected_clauses,
        "missing_clauses": missing,
        "citation_count": len(refs),
        "distinct_citations": len(set(refs)),
        "has_citation": bool(refs),
        "citations_resolve": citations_resolve,
        "uncited_sources": max(len(sources) - cited_sources, 0),
        "cited_ratio": round(cited_ratio, 6),
        "sources_count": len(sources),
        "response_time_s": sample.get("response_time_s"),
    }


def check_negative(sample: Dict[str, Any]) -> Dict[str, Any]:
    answer = sample.get("answer") or ""
    sources = sample.get("sources") or []
    cited = bool(CITATION_RE.search(answer))
    refused = bool(REFUSAL_RE.search(answer))
    passed = (not sources) or (refused and not cited)
    reason = "no sources" if not sources else ("explicit refusal" if refused else "returned sources without refusing")
    return {
        "question_id": sample.get("question_id"),
        "question": sample.get("question"),
        "status": sample.get("status"),
        "answer": answer,
        "sources_count": len(sources),
        "invented_citation": cited,
        "passed": passed,
        "reason": reason,
    }


def aggregate(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    for metric in RAGAS_METRICS:
        values = [r["scores"].get(metric) for r in records]
        result[metric] = {
            "mean": mean(values),
            "median": median(values),
            "stdev": stdev(values),
            "n": len([v for v in values if isinstance(v, (int, float)) and not math.isnan(v)]),
        }

    deterministic_values = [r["deterministic"] for r in records]
    result["deterministic"] = {
        "clause_recall": mean(d["clause_recall"] for d in deterministic_values),
        "citation_rate": mean(1.0 if d["has_citation"] else 0.0 for d in deterministic_values),
        "citations_resolve_rate": mean(1.0 if d["citations_resolve"] else 0.0 for d in deterministic_values),
        "citation_validity_rate": mean(
            1.0 if (d["has_citation"] and d["citations_resolve"]) else 0.0
            for d in deterministic_values
        ),
        "cited_ratio": mean(d["cited_ratio"] for d in deterministic_values),
        "sources_mean": mean(d["sources_count"] for d in deterministic_values),
        "latency_mean_s": mean(d["response_time_s"] for d in deterministic_values),
        "latency_median_s": median(d["response_time_s"] for d in deterministic_values),
    }
    return result


def grouped(records: List[Dict[str, Any]], key: str) -> Dict[str, Any]:
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for record in records:
        groups.setdefault(str(record.get(key) or "unknown"), []).append(record)
    return {name: aggregate(group) for name, group in sorted(groups.items())}


def _metric_value(scores: Dict[str, Any], metric: str) -> Optional[float]:
    value = scores.get(metric)
    if isinstance(value, (int, float)) and not math.isnan(value):
        return float(value)
    return None


def build_rows(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows = []
    for record in records:
        rows.append(
            {
                "user_input": record["question"],
                "retrieved_contexts": [source_text(source) for source in (record.get("sources") or [])],
                "response": strip_citations(record.get("answer") or ""),
                "reference": record["reference"],
            }
        )
    return rows


def _ensure_langchain_compat() -> None:
    """ragas 0.4.3 imports ChatVertexAI from a module langchain-community 0.4 removed.

    The class is only used in an isinstance check for multi-completion support, so
    an empty stand-in is enough. Remove this once ragas stops importing it.
    """
    import sys
    import types

    module_name = "langchain_community.chat_models.vertexai"
    try:
        __import__(module_name)
        return
    except ModuleNotFoundError:
        pass

    module = types.ModuleType(module_name)
    module.ChatVertexAI = type("ChatVertexAI", (), {})
    sys.modules[module_name] = module
    try:
        import langchain_community.chat_models as chat_models

        chat_models.vertexai = module
    except Exception:  # pragma: no cover - only a convenience alias
        pass


def _patch_ragas_instructor_mode() -> None:
    """LM Studio rejects response_format.type='json_object'; use json_schema mode."""
    _ensure_langchain_compat()
    import instructor
    import ragas.llms.base as base

    original = getattr(base, "_get_instructor_client", None)

    def patched(client, provider):
        provider_lower = str(provider).lower()
        if provider_lower in ("openai", "litellm"):
            return instructor.from_openai(client, mode=instructor.Mode.JSON_SCHEMA)
        if original is not None:
            return original(client, provider)
        return instructor.from_openai(client, mode=instructor.Mode.MD_JSON)

    base._get_instructor_client = patched
    try:
        import ragas.llms as llms

        llms.base._get_instructor_client = patched
    except Exception:
        pass


def score_with_ragas(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    _patch_ragas_instructor_mode()

    from openai import OpenAI, AsyncOpenAI

    from ragas import EvaluationDataset, RunConfig, evaluate
    from ragas.embeddings import embedding_factory
    from ragas.llms import llm_factory
    from ragas.metrics import (
        AnswerCorrectness,
        Faithfulness,
        LLMContextPrecisionWithReference,
        LLMContextRecall,
    )

    from app.config import config

    client = OpenAI(
        base_url=config.llm_base_url,
        api_key=config.local_api_key,
        timeout=config.evaluation_timeout_s,
    )
    async_client = AsyncOpenAI(
        base_url=config.embedding_base_url,
        api_key=config.local_api_key,
        timeout=config.evaluation_timeout_s,
    )
    judge = llm_factory(
        config.evaluation_judge_model,
        client=client,
        temperature=config.evaluation_judge_temperature,
        top_p=1.0,
        max_tokens=4096,
        reasoning_effort="none",
    )
    embeddings = embedding_factory(
        provider="openai",
        model=config.evaluation_embedding_model,
        client=async_client,
    )

    dataset = EvaluationDataset.from_list(build_rows(records))
    result = evaluate(
        dataset,
        metrics=[
            Faithfulness(),
            LLMContextRecall(),
            LLMContextPrecisionWithReference(),
            AnswerCorrectness(),
        ],
        llm=judge,
        embeddings=embeddings,
        run_config=RunConfig(
            timeout=config.evaluation_timeout_s,
            max_workers=config.evaluation_max_workers,
            max_retries=2,
        ),
        raise_exceptions=False,
        show_progress=True,
    )

    scores = result.scores
    if len(scores) != len(records):
        raise SystemExit(
            f"RAGAS returned {len(scores)} score rows for {len(records)} questions."
        )
    return scores


def run_score(run_id: str) -> int:
    path = run_path(run_id)
    samples = read_jsonl(path / "samples.jsonl")
    if not samples:
        raise SystemExit(f"No samples in eval/runs/{run_id}. Run collect first.")

    questions = {int(q["id"]): q for q in load_questions()}
    config = config_snapshot()

    positives: List[Dict[str, Any]] = []
    negatives: List[Dict[str, Any]] = []
    unverified: List[int] = []
    missing: List[int] = []

    for sample in samples:
        question_id = int(sample.get("question_id", 0))
        question = questions.get(question_id)
        if not question:
            missing.append(question_id)
            continue
        if str(question.get("category", "")).lower() == "negative":
            negatives.append(check_negative(sample))
            continue
        if question.get("verified") is not True:
            unverified.append(question_id)
            continue
        if sample.get("status") != "success":
            unverified.append(question_id)
            continue
        positives.append(
            {
                "question_id": question_id,
                "question": question["question"],
                "category": question.get("category"),
                "section": question.get("section"),
                "answer": sample.get("answer", ""),
                "sources": sample.get("sources") or [],
                "metadata": sample.get("metadata") or {},
                "response_time_s": sample.get("response_time_s"),
                "reference": question.get("reference", ""),
                "reference_clauses": question.get("reference_clauses") or [],
            }
        )

    if not positives:
        hint = ""
        if unverified:
            hint = (
                f" {len(unverified)} collected question(s) are not verified: "
                f"{', '.join(f'Q{i}' for i in unverified)}. Set verified: true in eval/questions.json."
            )
        raise SystemExit("No verified, successfully collected questions to score." + hint)

    print(
        f"Scoring {len(positives)} verified question(s) with judge "
        f"{config['judge_model']} (this is the slow phase)."
    )
    if unverified:
        print(f"Skipping {len(unverified)} unverified/unsuccessful question(s): {', '.join(f'Q{i}' for i in unverified)}")
    if missing:
        print(f"⚠️  Samples without a matching question: {', '.join(f'Q{i}' for i in missing)}")

    require_model_loaded(config["judge_model"], config["llm_base_url"], "judge")
    require_model_loaded(
        config["evaluation_embedding_model"],
        config["embedding_base_url"],
        "evaluation embedding",
        required=False,
    )

    ragas_rows = score_with_ragas(positives)

    scored: List[Dict[str, Any]] = []
    for record, row in zip(positives, ragas_rows):
        scores = {}
        for ragas_name, output_name in RAGAS_COLUMNS.items():
            scores[output_name] = _metric_value(row, ragas_name)
        deterministic = deterministic_metrics(questions[record["question_id"]], record)
        scored.append(
            {
                "question_id": record["question_id"],
                "question": record["question"],
                "category": record.get("category"),
                "section": record.get("section"),
                "answer": record["answer"],
                "sources_count": len(record["sources"]),
                "response_time_s": record.get("response_time_s"),
                "scores": scores,
                "deterministic": deterministic,
            }
        )

    import ragas

    document = {
        "run_id": run_id,
        "generated_at": utc_now(),
        "git_sha": run_id.rsplit("-", 1)[-1],
        "config": {
            **config,
            "ragas_version": getattr(ragas, "__version__", "unknown"),
            "python_version": platform.python_version(),
        },
        "metrics": RAGAS_METRICS,
        "question_ids": [record["question_id"] for record in scored],
        "questions": scored,
        "negatives": negatives,
        "aggregate": aggregate(scored),
        "by_category": grouped(scored, "category"),
        "by_section": grouped(scored, "section"),
        "skipped_unverified": unverified,
        "missing_questions": missing,
    }
    write_json(path / "scores.json", document)
    write_scores_csv(path / "scores.csv", scored)

    print("\nRAGAS scores")
    for metric in RAGAS_METRICS:
        stats = document["aggregate"][metric]
        print(f"  {metric:<20} mean {fmt(stats['mean'])}  (n={stats['n']})")

    failed = [
        record["question_id"]
        for record in scored
        if all(record["scores"].get(metric) is None for metric in RAGAS_METRICS)
    ]
    if failed:
        print(f"\n⚠️  No metric returned for: {', '.join(f'Q{i}' for i in failed)}")
        return 1
    return 0


def write_scores_csv(path, records: List[Dict[str, Any]]) -> None:
    fieldnames = [
        "question_id",
        "category",
        "section",
        "status",
        "sources_count",
        "response_time_s",
        "clause_recall",
        "has_citation",
        "citations_resolve",
        "uncited_sources",
        "cited_ratio",
        *RAGAS_METRICS,
    ]
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for record in records:
            row = {
                "question_id": record["question_id"],
                "category": record.get("category"),
                "section": record.get("section"),
                "status": "success",
                "sources_count": record["sources_count"],
                "response_time_s": record["response_time_s"],
                "clause_recall": record["deterministic"]["clause_recall"],
                "has_citation": record["deterministic"]["has_citation"],
                "citations_resolve": record["deterministic"]["citations_resolve"],
                "uncited_sources": record["deterministic"]["uncited_sources"],
                "cited_ratio": record["deterministic"]["cited_ratio"],
            }
            row.update({metric: record["scores"].get(metric) for metric in RAGAS_METRICS})
            writer.writerow(row)
