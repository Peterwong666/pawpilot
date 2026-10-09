#!/usr/bin/env bash
# One-command smoke test for the full Docker Compose stack.
# Usage: ./scripts/docker_smoke_test.sh
set -euo pipefail

COMPOSE_FILE="docker/docker-compose.full.yml"

cleanup() {
  echo "Teardown stack..."
  docker-compose -f "$COMPOSE_FILE" down -v >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "Building and starting stack..."
docker-compose -f "$COMPOSE_FILE" up -d --build

echo "Waiting for API /health..."
for i in $(seq 1 30); do
  if curl -fs http://localhost:8000/health >/dev/null 2>&1; then
    echo "API is healthy"
    break
  fi
  sleep 2
done

echo "Checking endpoints..."
curl -fs http://localhost:8000/health | python -m json.tool
curl -fs http://localhost:8000/health/db | python -m json.tool
curl -fs http://localhost:8000/health/embed | python -m json.tool

echo "Smoke test passed."
