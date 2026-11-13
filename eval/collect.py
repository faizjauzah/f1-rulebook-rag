"""Phase 1: ask the running API every question and save the raw answers."""

from __future__ import annotations

import os
import time
from typing import Any, Dict, List

import requests

from eval.common import (
    append_jsonl,
    config_snapshot,
    filter_questions,
    git_sha,
    load_questions,
    read_jsonl,
    require_model_loaded,
    run_path,
    utc_now,
    write_json,
)


def collect_timeout_s() -> float:
    return float(os.getenv("EVAL_TIMEOUT", "180"))


def api_url() -> str:
    return os.getenv("EVAL_API_URL", "http://localhost:8000").rstrip("/")


def collect_one(question: Dict[str, Any], timeout_s: float) -> Dict[str, Any]:
    record: Dict[str, Any] = {
        "question_id": int(question["id"]),
        "question": question["question"],
        "category": question.get("category"),
        "section": question.get("section"),
    }
    started = time.time()
    try:
        response = requests.post(
            f"{api_url()}/query",
            json={"question": question["question"]},
            timeout=timeout_s,
        )
        record["response_time_s"] = round(time.time() - started, 3)
        if response.status_code != 200:
            record.update(
                status="error",
                error=f"HTTP {response.status_code}: {response.text[:500]}",
            )
            return record
        data = response.json()
        record.update(
            status="success",
            answer=data.get("answer", ""),
            sources=data.get("sources", []),
            metadata=data.get("metadata", {}),
        )
        return record
    except Exception as exc:  # noqa: BLE001 - a failed question must not abort the run
        record.update(
            status="error",
            response_time_s=round(time.time() - started, 3),
            error=f"{type(exc).__name__}: {exc}",
        )
        return record


def run_collect(run_id: str, force: bool = False) -> int:
    questions = filter_questions(load_questions())
    if not questions:
        raise SystemExit("No questions selected. Check EVAL_IDS / EVAL_CATEGORY / EVAL_LIMIT.")

    snapshot = config_snapshot()
    require_model_loaded(snapshot["generator_model"], snapshot["llm_base_url"], "generator")

    path = run_path(run_id)
    path.mkdir(parents=True, exist_ok=True)
    samples_path = path / "samples.jsonl"

    if force and samples_path.exists():
        samples_path.unlink()

    existing = {}
    if samples_path.exists():
        existing = {r["question_id"]: r for r in read_jsonl(samples_path)}

    started_at = utc_now()
    errors: List[int] = []
    skipped: List[int] = []

    print(
        f"Collecting {len(questions)} question(s) for run {run_id} "
        f"via {api_url()} (timeout {collect_timeout_s():.0f}s).\n"
    )

    for index, question in enumerate(questions, start=1):
        question_id = int(question["id"])
        previous = existing.get(question_id)
        if previous and previous.get("status") == "success":
            skipped.append(question_id)
            print(f"[{index}/{len(questions)}] Q{question_id} already collected, skipping.")
            continue

        print(f"[{index}/{len(questions)}] Q{question_id} ({question.get('category')}) - {question['question'][:90]}")
        record = collect_one(question, collect_timeout_s())
        append_jsonl(samples_path, record)

        if record["status"] == "success":
            print(
                f"    ok in {record['response_time_s']:.1f}s, "
                f"{len(record.get('sources') or [])} source(s)"
            )
        else:
            errors.append(question_id)
            print(f"    FAILED: {record.get('error')}")

    write_json(
        path / "collect.json",
        {
            "run_id": run_id,
            "stage": "collect",
            "started_at": started_at,
            "finished_at": utc_now(),
            "git_sha": git_sha(),
            "api_url": api_url(),
            "timeout_s": collect_timeout_s(),
            "config": config_snapshot(),
            "question_ids": [int(q["id"]) for q in questions],
            "skipped_existing": skipped,
            "errors": errors,
        },
    )

    print(f"\nCollected {len(questions) - len(errors) - len(skipped)} new, {len(skipped)} reused, {len(errors)} failed.")
    if errors:
        print(f"Failed questions: {', '.join(f'Q{i}' for i in errors)}")
        return 1
    return 0
