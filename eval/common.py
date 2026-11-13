"""Evaluation support code. Run through the container: `./run.sh eval`."""

from __future__ import annotations

import json
import math
import os
import re
import statistics
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import requests

EVAL_DIR = Path(__file__).resolve().parent
RUNS_DIR = EVAL_DIR / "runs"
QUESTIONS_PATH = EVAL_DIR / "questions.json"
BASELINE_PATH = EVAL_DIR / "baseline.json"

RAGAS_METRICS = [
    "faithfulness",
    "context_recall",
    "context_precision",
    "answer_correctness",
]

MISSING = "-"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return "nogit"


def make_run_id() -> str:
    return f"{utc_stamp()}-{git_sha()}"


def validate_run_id(run_id: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9._-]+", run_id or ""):
        raise SystemExit(f"Invalid run id: {run_id!r}")
    return run_id


def run_path(run_id: str) -> Path:
    return RUNS_DIR / validate_run_id(run_id)


def latest_run_id() -> Optional[str]:
    if not RUNS_DIR.exists():
        return None
    candidates = sorted(
        (p.name for p in RUNS_DIR.iterdir() if p.is_dir() and (p / "samples.jsonl").exists()),
        reverse=True,
    )
    return candidates[0] if candidates else None


def resolve_run_id(run_id: Optional[str], require_samples: bool = True) -> str:
    if run_id:
        run_id = validate_run_id(run_id)
        if require_samples and not (run_path(run_id) / "samples.jsonl").exists():
            raise SystemExit(f"No samples.jsonl in eval/runs/{run_id}. Run collect first.")
        return run_id
    found = latest_run_id()
    if not found:
        raise SystemExit("No evaluation runs found. Run `./run.sh eval collect` first.")
    return found


def read_json(path: Path) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(value, f, indent=2, ensure_ascii=False)
        f.write("\n")


def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    records = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def append_jsonl(path: Path, record: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
        f.flush()


def load_questions(path: Path = QUESTIONS_PATH) -> List[Dict[str, Any]]:
    questions = read_json(path)
    if not isinstance(questions, list) or not questions:
        raise SystemExit(f"{path} must contain a non-empty list of questions.")
    return questions


def _int_list(value: str) -> List[int]:
    return [int(part) for part in re.split(r"[,\s]+", value.strip()) if part]


def filter_questions(questions: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Apply the iteration filters: EVAL_IDS, EVAL_CATEGORY, EVAL_LIMIT."""
    selected = list(questions)

    raw_ids = os.getenv("EVAL_IDS", "").strip()
    if raw_ids:
        ids = set(_int_list(raw_ids))
        selected = [q for q in selected if int(q["id"]) in ids]

    category = os.getenv("EVAL_CATEGORY", "").strip().lower()
    if category:
        selected = [q for q in selected if str(q.get("category", "")).lower() == category]

    raw_limit = os.getenv("EVAL_LIMIT", "").strip()
    if raw_limit:
        limit = int(raw_limit)
        if limit > 0:
            selected = selected[:limit]

    return selected


def config_snapshot() -> Dict[str, Any]:
    # Imported lazily so that helpers such as `git_sha` do not require config.yaml.
    from app.config import config

    return {
        "generator_model": config.llm_model,
        "generator_temperature": config.llm_temperature,
        "judge_model": config.evaluation_judge_model,
        "judge_temperature": config.evaluation_judge_temperature,
        "embedding_model": config.embedding_model,
        "evaluation_embedding_model": config.evaluation_embedding_model,
        "collection": config.collection_name,
        "top_k": config.top_k,
        "similarity_threshold": config.similarity_threshold,
        "llm_base_url": config.llm_base_url,
        "embedding_base_url": config.embedding_base_url,
    }


def strip_citations(text: str) -> str:
    """Remove [1] markers before judging; they are provenance, not claims."""
    cleaned = re.sub(r"\[\d+\]", " ", text or "")
    return re.sub(r"\s+", " ", cleaned).strip()


def source_text(source: Dict[str, Any]) -> str:
    """One RAGAS context = one source (the whole clause)."""
    parts: List[str] = []
    label = (source.get("label") or "").strip()
    if label:
        parts.append(label)
    for paragraph in source.get("paragraphs") or []:
        text = (paragraph.get("text") or "").strip()
        if text:
            parts.append(text)
    return "\n".join(parts).strip()


def _api_root(base_url: str) -> str:
    root = base_url.rstrip("/")
    if root.endswith("/v1"):
        root = root[:-3]
    return root


def model_states(base_url: str) -> Optional[Dict[str, str]]:
    """Return {model_id: state} from LM Studio, or None if the endpoint is absent."""
    try:
        response = requests.get(f"{_api_root(base_url)}/api/v0/models", timeout=10)
        response.raise_for_status()
        return {
            item["id"]: item.get("state", "unknown")
            for item in response.json().get("data", [])
            if "id" in item
        }
    except Exception:
        return None


def require_model_loaded(model: str, base_url: str, role: str, required: bool = True) -> None:
    states = model_states(base_url)
    if states is None:
        print(f"⚠️  Could not read /api/v0/models; assuming {role} model '{model}' is available.")
        return
    if model not in states:
        available = ", ".join(sorted(states))
        message = f"{role} model '{model}' is not available in the local server. Available: {available}"
        if required:
            raise SystemExit(message)
        print(f"⚠️  {message}")
        return
    state = states[model]
    if state == "loaded":
        print(f"✓ {role} model loaded: {model}")
        return
    message = (
        f"{role} model '{model}' is {state}, not loaded. Load it in LM Studio "
        "and retry (or let `./run.sh eval` swap it for you)."
    )
    if required:
        raise SystemExit(message)
    print(f"⚠️  {message}")


def numeric(values: Iterable[Any]) -> List[float]:
    out = []
    for value in values:
        if value is None:
            continue
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if math.isnan(number) or math.isinf(number):
            continue
        out.append(number)
    return out


def mean(values: Iterable[Any]) -> Optional[float]:
    numbers = numeric(values)
    return statistics.fmean(numbers) if numbers else None


def median(values: Iterable[Any]) -> Optional[float]:
    numbers = numeric(values)
    return statistics.median(numbers) if numbers else None


def stdev(values: Iterable[Any]) -> Optional[float]:
    numbers = numeric(values)
    return statistics.stdev(numbers) if len(numbers) > 1 else None


def fmt(value: Any, digits: int = 3) -> str:
    if value is None:
        return MISSING
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if math.isnan(number) or math.isinf(number):
        return MISSING
    return f"{number:.{digits}f}"
