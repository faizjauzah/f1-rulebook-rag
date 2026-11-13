#!/bin/bash

set -e

LMS_BIN="${LMS_BIN:-$HOME/.lmstudio/bin/lms}"
JUDGE_LOADED=0
GEN_MODEL=""
JUDGE_MODEL=""

require_api() {
  if ! docker-compose exec -T api true >/dev/null 2>&1; then
    echo "API container is not running. Start it with ./run.sh start."
    exit 1
  fi
}

model_name() {
  docker-compose exec -T api python -m eval.run_eval print-model "$1" | tr -d '\r' | tail -n 1
}

# Run the eval CLI inside the API container, forwarding the iteration filters.
# docker-compose exec does not inherit the host environment by default, so these
# have to be passed explicitly.
eval_exec() {
  docker-compose exec -T \
    -e EVAL_IDS="${EVAL_IDS:-}" \
    -e EVAL_CATEGORY="${EVAL_CATEGORY:-}" \
    -e EVAL_LIMIT="${EVAL_LIMIT:-}" \
    -e EVAL_TIMEOUT="${EVAL_TIMEOUT:-180}" \
    -e EVAL_API_URL="${EVAL_API_URL:-http://localhost:8000}" \
    api python -m eval.run_eval "$@"
}

require_lms() {
  if [ ! -x "$LMS_BIN" ]; then
    echo "LM Studio CLI not found at $LMS_BIN."
    echo "Set LMS_BIN to the lms binary, or load the models by hand and use"
    echo "  ./run.sh eval collect <run-id>"
    echo "  ./run.sh eval score <run-id>"
    exit 1
  fi
}

ensure_generator() {
  require_lms
  if "$LMS_BIN" ps 2>/dev/null | grep -Fq "$GEN_MODEL"; then
    return
  fi
  "$LMS_BIN" unload "$JUDGE_MODEL" >/dev/null 2>&1 || true
  echo "Loading generator $GEN_MODEL..."
  "$LMS_BIN" load "$GEN_MODEL" -y
}

load_judge() {
  if [ "$GEN_MODEL" = "$JUDGE_MODEL" ]; then
    echo "Generator and judge are the same model; leaving it loaded."
    return
  fi
  require_lms
  "$LMS_BIN" unload "$GEN_MODEL" >/dev/null 2>&1 || true
  echo "Loading judge $JUDGE_MODEL..."
  "$LMS_BIN" load "$JUDGE_MODEL" -y
  JUDGE_LOADED=1
}

restore_generator() {
  if [ "$JUDGE_LOADED" = "1" ] && [ "${EVAL_KEEP_JUDGE:-0}" != "1" ]; then
    echo "Restoring generator $GEN_MODEL..."
    "$LMS_BIN" unload "$JUDGE_MODEL" >/dev/null 2>&1 || true
    "$LMS_BIN" load "$GEN_MODEL" -y || true
    JUDGE_LOADED=0
  fi
}

new_run_id() {
  echo "$(date -u +%Y%m%dT%H%M%SZ)-$(git rev-parse --short HEAD 2>/dev/null || echo nogit)"
}

eval_command() {
  local stage="${1:-all}"
  local run_arg="$2"
  local compare_arg="$3"

  require_api

  case "$stage" in
    collect)
      local run_id="${run_arg:-$(new_run_id)}"
      echo "📥 Collecting answers into run $run_id..."
      eval_exec collect --run-id "$run_id"
      ;;

    score)
      if [ -n "$run_arg" ]; then
        eval_exec score --run-id "$run_arg"
      else
        eval_exec score
      fi
      ;;

    report)
      if [ -n "$run_arg" ]; then
        eval_exec report --run-id "$run_arg"
      else
        eval_exec report
      fi
      ;;

    bless)
      if [ -z "$run_arg" ]; then
        echo "Usage: ./run.sh eval bless <run-id> [<compare-run-id>]"
        exit 1
      fi
      eval_exec bless --run-id "$run_arg" ${compare_arg:+--compare-run-id "$compare_arg"}
      ;;

    all)
      GEN_MODEL=$(model_name generator)
      JUDGE_MODEL=$(model_name judge)
      local run_id="${run_arg:-$(new_run_id)}"

      ensure_generator
      trap restore_generator EXIT

      echo "📥 Collecting answers into run $run_id..."
      eval_exec collect --run-id "$run_id"

      load_judge
      echo "📊 Scoring run $run_id..."
      eval_exec score --run-id "$run_id"

      restore_generator
      eval_exec report --run-id "$run_id"
      echo ""
      echo "Run directory: eval/runs/$run_id"
      ;;

    *)
      echo "Usage: ./run.sh eval [all|collect|score|report|bless] [run-id] [compare-run-id]"
      exit 1
      ;;
  esac
}

case "$1" in
  start)
    echo "🚀 Starting F1 Rulebook RAG..."
    docker-compose up --build
    ;;
  
  stop)
    echo "🛑 Stopping services..."
    docker-compose down
    ;;
  
  ingest)
    echo "📥 Ingesting PDFs..."
    echo "This takes ~5-10 minutes with a local embedding model..."
    curl -X POST http://localhost:8000/ingest
    echo ""
    ;;
  
  health)
    echo "🏥 Checking health..."
    curl http://localhost:8000/health | python3 -m json.tool
    echo ""
    ;;
  
  query)
    if [ -z "$2" ]; then
      echo "Usage: ./run.sh query \"Your question here\""
      exit 1
    fi
    echo "🔍 Querying: $2"
    curl -X POST http://localhost:8000/query \
      -H "Content-Type: application/json" \
      -d "{\"question\": \"$2\"}" | python3 -m json.tool
    echo ""
    ;;
  
  eval)
    eval_command "${2:-${EVAL_STAGE:-all}}" "${3:-}" "${4:-}"
    ;;
  
  logs)
    docker-compose logs -f api
    ;;
  
  clean)
    echo "🧹 Cleaning up data and containers..."
    docker-compose down -v
    rm -rf data/
    echo "Done! Run './run.sh start' to rebuild."
    ;;
  
  *)
    echo "F1 Rulebook RAG - Helper Script"
    echo ""
    echo "Usage: ./run.sh [command]"
    echo ""
    echo "Commands:"
    echo "  start      - Start all services (API + ChromaDB)"
    echo "  stop       - Stop all services"
    echo "  ingest     - Ingest PDFs into vector store (run once)"
    echo "  health     - Check service health"
    echo "  query      - Query the RAG system"
    echo "               Example: ./run.sh query \"What is DRS?\""
    echo "  eval       - Run the RAGAS evaluation (see below)"
    echo "  logs       - View API logs"
    echo "  clean      - Remove all data and containers"
    echo ""
    echo "Evaluation:"
    echo "  ./run.sh eval                 - collect + score + report (swaps models)"
    echo "  ./run.sh eval collect         - collect answers only"
    echo "  ./run.sh eval score           - score the latest collected run"
    echo "  ./run.sh eval report          - summarise the latest scored run"
    echo "  ./run.sh eval bless <run> [<compare>] - promote a run to the baseline"
    echo ""
    echo "Quick start:"
    echo "  1. Start LM Studio and load the embedding + chat models from config.yaml"
    echo "  2. ./run.sh start"
    echo "  3. Wait for services to be healthy"
    echo "  4. ./run.sh ingest"
    echo "  5. Open http://localhost:8000"
    ;;
esac
