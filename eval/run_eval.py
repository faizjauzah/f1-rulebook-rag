"""CLI for the evaluation pipeline.

Run from the API container (or through `./run.sh eval`):

    python -m eval.run_eval collect [--run-id ID] [--force]
    python -m eval.run_eval score   [--run-id ID]
    python -m eval.run_eval report  [--run-id ID]
    python -m eval.run_eval bless   [--run-id ID] [--compare-run-id ID]
    python -m eval.run_eval print-model {generator|judge|embedding}
"""

from __future__ import annotations

import argparse
import sys
from typing import Optional

from eval.collect import run_collect
from eval.common import (
    RUNS_DIR,
    make_run_id,
    resolve_run_id,
    run_path,
    validate_run_id,
)
from eval.report import run_bless, run_report
from eval.score import run_score


def latest_scored_run_id() -> Optional[str]:
    if not RUNS_DIR.exists():
        return None
    candidates = sorted(
        (p.name for p in RUNS_DIR.iterdir() if p.is_dir() and (p / "scores.json").exists()),
        reverse=True,
    )
    return candidates[0] if candidates else None


def require_scored_run(run_id: Optional[str]) -> str:
    found = run_id or latest_scored_run_id()
    if not found:
        raise SystemExit("No scored run found. Run `./run.sh eval score` first.")
    found = validate_run_id(found)
    if not (run_path(found) / "scores.json").exists():
        raise SystemExit(f"No scores.json in eval/runs/{found}.")
    return found


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m eval.run_eval")
    sub = parser.add_subparsers(dest="command", required=True)

    collect = sub.add_parser("collect", help="Ask the API every question and save answers")
    collect.add_argument("--run-id", default=None)
    collect.add_argument("--force", action="store_true", help="Re-collect even if a run already has answers")

    score = sub.add_parser("score", help="Score saved answers with RAGAS")
    score.add_argument("--run-id", default=None)

    report = sub.add_parser("report", help="Write summary.md for a scored run")
    report.add_argument("--run-id", default=None)

    bless = sub.add_parser("bless", help="Promote one or two runs to the baseline")
    bless.add_argument("--run-id", default=None)
    bless.add_argument("--compare-run-id", default=None)

    print_model = sub.add_parser("print-model", help="Print a configured model name")
    print_model.add_argument("role", choices=["generator", "judge", "embedding"])

    args = parser.parse_args(argv)

    if args.command == "print-model":
        from app.config import config

        model = {
            "generator": config.llm_model,
            "judge": config.evaluation_judge_model,
            "embedding": config.evaluation_embedding_model,
        }[args.role]
        print(model)
        return 0

    if args.command == "collect":
        run_id = args.run_id or make_run_id()
        return run_collect(run_id, force=args.force)

    if args.command == "score":
        run_id = resolve_run_id(args.run_id)
        return run_score(run_id)

    if args.command == "report":
        return run_report(require_scored_run(args.run_id))

    if args.command == "bless":
        return run_bless(
            require_scored_run(args.run_id),
            require_scored_run(args.compare_run_id) if args.compare_run_id else None,
        )

    parser.error(f"Unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
