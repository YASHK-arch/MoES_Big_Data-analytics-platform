#!/usr/bin/env bash
# scripts/demo-seed.sh — Create operator accounts and ~500 clearly-labelled demo reports
# Existing: back-end/scripts/seed_demo_data.py creates admin/operator/citizen accounts
#           and seeds relief centres + forecast advisories.
# Added: seed_bulk_demo_reports seeds ~500 weather reports flagged as [DEMO].
# Usage: ./scripts/demo-seed.sh [API_BASE_URL]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
API_BASE="${1:-http://localhost:8080/api/v1}"
ENV_FILE="$PROJECT_ROOT/.env.demo"
COMPOSE_FILE="$PROJECT_ROOT/docker-compose.demo.yml"

echo "[demo-seed] Seeding database inside the demo api container..."
docker compose \
  -f "$COMPOSE_FILE" \
  --env-file "$ENV_FILE" \
  -p sih-demo \
  exec -T api \
  python3 scripts/seed_demo_data.py

echo "[demo-seed] Verifying operator authentication via $API_BASE/auth/login..."
LOGIN_RESP=$(curl -sf -X POST "$API_BASE/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"username":"operator@weather-platform.gov.in","password":"EmergencyOps2026!"}' || true)

if echo "$LOGIN_RESP" | grep -q "access_token"; then
  echo "[demo-seed] ✅ Operator authenticated successfully!"
else
  echo "[demo-seed] ⚠️ Operator login check failed or API not reachable at $API_BASE."
fi

echo "[demo-seed] Seeding complete: operator accounts, relief centers, advisories, and 500 [DEMO] reports created."
