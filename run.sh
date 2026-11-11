#!/bin/bash

set -e

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
    echo "📊 Running evaluation..."
    docker-compose exec api python eval/run_eval.py
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
    echo "  eval       - Run evaluation suite"
    echo "  logs       - View API logs"
    echo "  clean      - Remove all data and containers"
    echo ""
    echo "Quick start:"
    echo "  1. Start LM Studio and load the embedding + chat models from config.yaml"
    echo "  2. ./run.sh start"
    echo "  3. Wait for services to be healthy"
    echo "  4. ./run.sh ingest"
    echo "  5. Open http://localhost:8000"
    ;;
esac
