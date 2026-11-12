#!/bin/bash

set -e

API_URL="http://localhost:8000"

echo "🧪 F1 Rulebook RAG - Smoke Test"
echo "================================"
echo ""

# Test 1: Health Check
echo "1️⃣  Testing health endpoint..."
response=$(curl -s "$API_URL/health")
status=$(echo $response | python3 -c "import sys, json; print(json.load(sys.stdin)['status'])" 2>/dev/null || echo "error")

if [ "$status" = "healthy" ]; then
  echo "✅ Health check passed"
else
  echo "❌ Health check failed: $status"
  exit 1
fi
echo ""

# Test 2: Easy Question
echo "2️⃣  Testing easy question (F1 Championship)..."
response=$(curl -s -X POST "$API_URL/query" \
  -H "Content-Type: application/json" \
  -d '{"question": "What are the two FIA Formula One World Championship titles awarded each season?"}')

answer=$(echo $response | python3 -c "import sys, json; print(json.load(sys.stdin)['answer'][:50])" 2>/dev/null || echo "error")

if [ "$answer" != "error" ] && [ ! -z "$answer" ]; then
  echo "✅ Easy question passed"
  echo "   Answer preview: $answer..."
else
  echo "❌ Easy question failed"
  exit 1
fi
echo ""

# Test 3: Medium Question
echo "3️⃣  Testing medium question (collision)..."
response=$(curl -s -X POST "$API_URL/query" \
  -H "Content-Type: application/json" \
  -d '{"question": "What happens if a driver causes a collision?"}')

answer=$(echo $response | python3 -c "import sys, json; print(json.load(sys.stdin)['answer'][:50])" 2>/dev/null || echo "error")

if [ "$answer" != "error" ] && [ ! -z "$answer" ]; then
  echo "✅ Medium question passed"
  echo "   Answer preview: $answer..."
else
  echo "❌ Medium question failed"
  exit 1
fi
echo ""

# Test 4: Off-topic Question (should gracefully decline)
echo "4️⃣  Testing off-topic question (weather)..."
response=$(curl -s -X POST "$API_URL/query" \
  -H "Content-Type: application/json" \
  -d '{"question": "What is the weather tomorrow?"}')

answer=$(echo $response | python3 -c "import sys, json; print(json.load(sys.stdin)['answer'])" 2>/dev/null || echo "error")
sources=$(echo $response | python3 -c "import sys, json; print(len(json.load(sys.stdin)['sources']))" 2>/dev/null || echo "-1")

if [ "$sources" = "0" ]; then
  echo "✅ Off-topic handling passed (no sources returned)"
  echo "   Answer: $answer"
else
  echo "⚠️  Off-topic handling unclear (returned $sources sources)"
fi
echo ""

# Test 5: Response Format
echo "5️⃣  Testing response format..."
response=$(curl -s -X POST "$API_URL/query" \
  -H "Content-Type: application/json" \
  -d '{"question": "What are the two FIA Formula One World Championship titles awarded each season?"}')

has_answer=$(echo $response | python3 -c "import sys, json; print('answer' in json.load(sys.stdin))" 2>/dev/null || echo "False")
has_sources=$(echo $response | python3 -c "import sys, json; print('sources' in json.load(sys.stdin))" 2>/dev/null || echo "False")
has_metadata=$(echo $response | python3 -c "import sys, json; print('metadata' in json.load(sys.stdin))" 2>/dev/null || echo "False")

if [ "$has_answer" = "True" ] && [ "$has_sources" = "True" ] && [ "$has_metadata" = "True" ]; then
  echo "✅ Response format valid"
else
  echo "❌ Response format invalid (answer:$has_answer, sources:$has_sources, metadata:$has_metadata)"
  exit 1
fi
echo ""

echo "================================"
echo "✅ All smoke tests passed!"
echo ""
echo "Next steps:"
echo "  - Run full eval: ./run.sh eval"
echo "  - Try web UI: http://localhost:8000"
echo "  - Check API docs: http://localhost:8000/docs"
