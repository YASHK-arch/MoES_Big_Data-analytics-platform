#!/usr/bin/env bash
# scripts/demo-seed.sh — Create operator accounts and ~500 clearly-labelled demo reports
# Existing: back-end/scripts/seed_demo_data.py creates admin/operator/citizen accounts
#           and seeding relief centres + forecast advisories.
# Added here: POST ~500 weather reports via the running API flagged as demo data.
# Usage: ./scripts/demo-seed.sh [API_BASE_URL]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
API_BASE="${1:-http://localhost:8080/api/v1}"
ENV_FILE="$PROJECT_ROOT/.env.demo"

# Source env for DB URL (seed_demo_data needs direct DB access)
if [[ -f "$ENV_FILE" ]]; then
  set -o allexport
  source "$ENV_FILE"
  set +o allexport
fi

echo "[demo-seed] Step 1: Seeding users, relief centres, and forecast advisories via DB..."
# Run the existing seed script against the demo DB inside the postgres container
DB_URL="postgresql+asyncpg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@localhost:5433/${POSTGRES_DB}" \
docker compose \
  -f "$PROJECT_ROOT/docker-compose.demo.yml" \
  --env-file "$ENV_FILE" \
  -p sih-demo \
  exec -T api \
  python3 back-end/scripts/seed_demo_data.py 2>/dev/null || \
python3 -c "
import asyncio, os, sys
sys.path.insert(0, '$PROJECT_ROOT/back-end')
os.environ.setdefault('DATABASE_URL', 'postgresql+asyncpg://${POSTGRES_USER:-weather_demo}:${POSTGRES_PASSWORD:-demo}@localhost:5433/${POSTGRES_DB:-weather_demo}')
from scripts.seed_demo_data import main as seed_main
asyncio.run(seed_main())
" 2>&1 || echo "[demo-seed] Warning: DB seed step skipped (run manually if needed)"

echo "[demo-seed] Step 2: Authenticating as operator to POST demo reports..."
# Login and get token
TOKEN=$(curl -sf -X POST "$API_BASE/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email":"operator@weather-platform.gov.in","password":"EmergencyOps2026!"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])" 2>/dev/null || echo "")

if [[ -z "$TOKEN" ]]; then
  echo "[demo-seed] ERROR: Could not authenticate as operator. Is the stack running? (./scripts/demo-up.sh)"
  exit 1
fi

echo "[demo-seed] Step 3: Posting ~500 demo reports (clearly labelled '[DEMO]')..."
python3 - "$API_BASE" "$TOKEN" <<'PYEOF'
import sys, json, time, random
import urllib.request, urllib.error

api_base, token = sys.argv[1], sys.argv[2]

# Demo data: flagged clearly as [DEMO] in title, description says "Demo data for SIH evaluation"
CATEGORIES = [
    "FLOOD_WATERLOGGING", "HEAVY_RAINFALL", "CYCLONE_STORM", "LANDSLIDE",
    "HEATWAVE", "COLD_WAVE", "FOG", "DUST_STORM", "STRONG_WIND",
    "URBAN_FLOOD", "DROUGHT", "LIGHTNING", "EARTHQUAKE", "OTHER",
]
SEVERITIES = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
LOCATIONS = [
    (28.6139, 77.2090, "New Delhi"), (19.0760, 72.8777, "Mumbai"),
    (22.5726, 88.3639, "Kolkata"), (13.0827, 80.2707, "Chennai"),
    (12.9716, 77.5946, "Bengaluru"), (17.3850, 78.4867, "Hyderabad"),
    (26.9124, 75.7873, "Jaipur"), (23.0225, 72.5714, "Ahmedabad"),
    (11.0168, 76.9558, "Coimbatore"), (25.5941, 85.1376, "Patna"),
]

def post_report(i, cat, severity, lat, lng, city):
    payload = {
        "title": f"[DEMO] {cat.replace('_',' ').title()} incident near {city} #{i}",
        "description": f"Demo data for SIH evaluation. Category: {cat}. Severity: {severity}. Auto-generated report {i}.",
        "reported_category": cat,
        "severity": severity,
        "latitude": lat + random.uniform(-0.5, 0.5),
        "longitude": lng + random.uniform(-0.5, 0.5),
        "location_name": f"{city} District",
        "location_description": f"Demo report near {city}",
    }
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{api_base}/reports",
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status
    except urllib.error.HTTPError as e:
        return e.code

ok = err = 0
for i in range(1, 501):
    lat, lng, city = random.choice(LOCATIONS)
    cat = CATEGORIES[i % len(CATEGORIES)]
    sev = SEVERITIES[i % len(SEVERITIES)]
    code = post_report(i, cat, sev, lat, lng, city)
    if code in (200, 201):
        ok += 1
    else:
        err += 1
    if i % 50 == 0:
        print(f"  {i}/500 posted (ok={ok} err={err})")
    time.sleep(0.05)  # gentle rate limiting

print(f"[demo-seed] Done: {ok} reports created, {err} errors")
PYEOF
