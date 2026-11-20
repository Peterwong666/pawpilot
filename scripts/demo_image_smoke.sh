#!/usr/bin/env bash
set -euo pipefail

image="${1:?Usage: bash scripts/demo_image_smoke.sh IMAGE}"
container="$(docker run -d --rm -e PAWPILOT_DEMO_MODE=1 -p 127.0.0.1::8000 "$image")"
trap 'docker rm -f "$container" >/dev/null 2>&1 || true' EXIT

endpoint="http://$(docker port "$container" 8000/tcp)"
for _ in $(seq 1 30); do
  if curl -fsS "$endpoint/health/db" 2>/dev/null | grep -q '"status":"demo"'; then
    curl -fsS -X POST "$endpoint/api/digest" >/dev/null
    curl -fsS -F file=@demo/seller-central-sales.csv "$endpoint/api/import-csv" |
      python3 -c 'import json,sys; p=json.load(sys.stdin); assert p["preview_only"] and p["rows_validated"] == 2'
    exit 0
  fi
  sleep 2
done

docker logs "$container"
exit 1
