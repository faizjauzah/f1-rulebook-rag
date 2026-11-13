"""Turn scores into a readable report and manage the committed baseline."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from eval.common import (
    BASELINE_PATH,
    RAGAS_METRICS,
    fmt,
    mean,
    read_json,
    run_path,
    utc_now,
    write_json,
)

BASELINE_KEYS = ("generator_model", "judge_model", "collection", "top_k", "similarity_threshold")


def _baseline_mismatch(baseline: Dict[str, Any], config: Dict[str, Any]) -> List[str]:
    old = baseline.get("config") or {}
    mismatched = []
    for key in BASELINE_KEYS:
        if old.get(key) != config.get(key):
            mismatched.append(f"{key}: {old.get(key)!r} → {config.get(key)!r}")
    return mismatched


def _load_baseline() -> Optional[Dict[str, Any]]:
    if not BASELINE_PATH.exists():
        return None
    return read_json(BASELINE_PATH)


def _table(headers: List[str], rows: List[List[str]]) -> List[str]:
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    lines.extend("| " + " | ".join(row) + " |" for row in rows)
    return lines


def _overall_table(aggregate: Dict[str, Any]) -> List[str]:
    rows = []
    for metric in RAGAS_METRICS:
        stats = aggregate[metric]
        failed = len(aggregate.get("question_ids", [])) - stats["n"]
        rows.append(
            [
                metric,
                fmt(stats["mean"]),
                fmt(stats["median"]),
                str(stats["n"]),
                str(max(failed, 0)),
                fmt(stats["stdev"]),
            ]
        )
    return _table(["Metric", "Mean", "Median", "Scored", "Failed", "Std dev"], rows)


def _grouped_table(title: str, groups: Dict[str, Any]) -> List[str]:
    rows = []
    for name, aggregate in groups.items():
        rows.append(
            [
                name,
                str(aggregate[RAGAS_METRICS[0]]["n"]),
                *(fmt(aggregate[metric]["mean"]) for metric in RAGAS_METRICS),
            ]
        )
    return [f"### {title}", "", *_table(["Group", "n", *RAGAS_METRICS], rows), ""]


def _deterministic_table(aggregate: Dict[str, Any]) -> List[str]:
    det = aggregate["deterministic"]
    rows = [
        ["Clause recall", fmt(det["clause_recall"])],
        ["Answers with a citation", fmt(det["citation_rate"])],
        ["Citations that resolve", fmt(det["citations_resolve_rate"])],
        ["Answers with a resolved citation", fmt(det["citation_validity_rate"])],
        ["Cited sources / returned sources", fmt(det["cited_ratio"])],
        ["Sources per answer", fmt(det["sources_mean"], 2)],
        ["Latency mean (s)", fmt(det["latency_mean_s"], 1)],
        ["Latency median (s)", fmt(det["latency_median_s"], 1)],
    ]
    return _table(["Check", "Value"], rows)


def _baseline_table(document: Dict[str, Any], baseline: Dict[str, Any]) -> List[str]:
    rows = []
    for metric in RAGAS_METRICS:
        old = (baseline.get("metrics") or {}).get(metric) or {}
        new = document["aggregate"][metric]["mean"]
        old_mean = old.get("mean")
        noise = old.get("noise")
        if old_mean is None or new is None:
            rows.append([metric, fmt(old_mean), fmt(new), "-", "-", "-"])
            continue
        delta = new - old_mean
        if noise is None:
            verdict = "no noise band"
        elif abs(delta) <= noise:
            verdict = "within noise"
        else:
            verdict = "changed"
        rows.append([metric, fmt(old_mean), fmt(new), f"{delta:+.3f}", fmt(noise), verdict])
    return _table(["Metric", "Baseline", "This run", "Delta", "Noise", "Verdict"], rows)


def _worst_questions(records: List[Dict[str, Any]], count: int = 5) -> List[str]:
    def key(record: Dict[str, Any]) -> float:
        value = record["scores"].get("answer_correctness")
        return value if isinstance(value, (int, float)) else 2.0

    ranked = sorted(records, key=key)[:count]
    rows = []
    for record in ranked:
        scores = record["scores"]
        available = {
            metric: value
            for metric, value in scores.items()
            if isinstance(value, (int, float))
        }
        weakest = min(available, key=available.get) if available else "no score"
        snippet = " ".join((record.get("answer") or "").split())[:180]
        rows.append(
            [
                f"Q{record['question_id']}",
                record.get("category") or "",
                fmt(scores.get("answer_correctness")),
                f"{weakest} ({fmt(available.get(weakest))})",
                snippet + ("…" if len(record.get("answer") or "") > 180 else ""),
            ]
        )
    return _table(["Question", "Difficulty", "Answer correctness", "Weakest", "Answer"], rows)


def _negative_table(negatives: List[Dict[str, Any]]) -> List[str]:
    if not negatives:
        return ["_No negative questions in this run._", ""]
    rows = []
    for record in negatives:
        rows.append(
            [
                f"Q{record['question_id']}",
                "pass" if record["passed"] else "FAIL",
                str(record["sources_count"]),
                "yes" if record["invented_citation"] else "no",
                record["reason"],
            ]
        )
    return _table(["Question", "Result", "Sources", "Invented citation", "Reason"], rows)


def run_report(run_id: str) -> int:
    path = run_path(run_id)
    scores_path = path / "scores.json"
    if not scores_path.exists():
        raise SystemExit(f"No scores.json in eval/runs/{run_id}. Run score first.")
    document = read_json(scores_path)
    config = document.get("config") or {}
    baseline = _load_baseline()

    lines: List[str] = [
        f"# Evaluation run {run_id}",
        "",
        f"_Generated {document['generated_at']}. Scores describe this machine, this generator "
        f"(`{config.get('generator_model')}`) and this judge (`{config.get('judge_model')}`); "
        "they are not comparable to a hosted model or a different judge._",
        "",
        f"- Questions scored: **{len(document['questions'])}**",
        f"- RAGAS: `{config.get('ragas_version')}`",
        f"- Retrieval: `top_k={config.get('top_k')}`, `similarity_threshold={config.get('similarity_threshold')}`",
        f"- Collection: `{config.get('collection')}`",
    ]
    if document.get("skipped_unverified"):
        lines.append(
            f"- Skipped (unverified or not collected): {', '.join(f'Q{i}' for i in document['skipped_unverified'])}"
        )
    lines.extend(["", "## Overall", "", *_overall_table({**document["aggregate"], "question_ids": document["question_ids"]}), ""])

    lines.extend(_grouped_table("By difficulty", document["by_category"]))
    lines.extend(_grouped_table("By section", document["by_section"]))

    lines.extend(["## Retrieval and citations", "", *_deterministic_table(document["aggregate"]), ""])

    lines.extend(["## Negative questions (out of scope)", "", *_negative_table(document.get("negatives") or []), ""])

    lines.extend(["## Lowest-scoring answers", "", *_worst_questions(document["questions"]), ""])

    lines.extend(["## Baseline", ""])
    if baseline is None:
        lines.append(
            "_No baseline yet. After two clean runs, promote one with "
            "`./run.sh eval bless <run-id> <compare-run-id>`._"
        )
    else:
        lines.append(f"Compared with baseline run `{baseline.get('run_id')}`.")
        mismatched = _baseline_mismatch(baseline, config)
        if mismatched:
            lines.append("")
            lines.append("> ⚠️ The baseline was produced with a different configuration; deltas are not comparable:")
            lines.extend(f"> - {item}" for item in mismatched)
        lines.extend(["", *_baseline_table(document, baseline)])
    lines.append("")

    summary_path = path / "summary.md"
    summary_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Report written to eval/runs/{run_id}/summary.md")
    return 0


def run_bless(run_id: str, compare_run_id: Optional[str] = None) -> int:
    current = read_json(run_path(run_id) / "scores.json")
    compare = None
    if compare_run_id:
        compare = read_json(run_path(compare_run_id) / "scores.json")
        for key in ("generator_model", "judge_model", "collection", "top_k", "similarity_threshold"):
            if (current["config"].get(key)) != (compare["config"].get(key)):
                print(
                    f"⚠️  Baseline runs differ on {key}: "
                    f"{compare['config'].get(key)!r} vs {current['config'].get(key)!r}"
                )

    metrics: Dict[str, Any] = {}
    for metric in RAGAS_METRICS:
        values = [current["aggregate"][metric]["mean"]]
        if compare:
            values.append(compare["aggregate"][metric]["mean"])
        valid = [value for value in values if value is not None]
        noise = None
        if compare:
            a = current["aggregate"][metric]["mean"]
            b = compare["aggregate"][metric]["mean"]
            if a is not None and b is not None:
                noise = abs(a - b)
        metrics[metric] = {"mean": mean(valid), "noise": noise}

    baseline = {
        "run_id": run_id,
        "compare_run_id": compare_run_id,
        "blessed_at": utc_now(),
        "config": current["config"],
        "metrics": metrics,
        "deterministic": current["aggregate"]["deterministic"],
        "runs": [run_id, compare_run_id] if compare_run_id else [run_id],
    }
    write_json(BASELINE_PATH, baseline)
    print(f"Baseline written to eval/baseline.json from {', '.join(baseline['runs'])}.")
    for metric in RAGAS_METRICS:
        print(f"  {metric:<20} mean {fmt(metrics[metric]['mean'])}  noise {fmt(metrics[metric]['noise'])}")
    return 0
