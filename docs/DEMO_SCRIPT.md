# DEMO_SCRIPT.md — 3-Minute Presentation Walkthrough & Failure Drill

This script provides an exact, click-by-click 3-minute evaluation walkthrough for Smart India Hackathon evaluators, demonstrating live situational awareness, multi-factor intelligence scoring, and container failure recovery.

All commands shown below were executed against the live demo stack (`sih-demo`) and their raw outputs are recorded in `logs/C_7.log`.

---

## 0. Demo Stack Launch & Verification (T-minus 1 Minute)

Ensure the isolated container stack is running and healthy:

```bash
# 1. Start the stack (one-command start)
./scripts/demo-up.sh

# 2. Seed default operator accounts and demo incidents
./scripts/demo-seed.sh
```

### Health & Readiness Verification
```bash
$ curl -s http://localhost:8080/health
{"success":true,"data":{"status":"healthy","service":"National Weather Big Data Analytics Platform","environment":"production","version":"0.1.0"},"meta":{"timestamp":"2026-09-30T22:54:53.701197+00:00"}}

$ curl -s http://localhost:8080/ready
{"success":true,"data":{"status":"ready","checks":{"database":"ok","redis":"ok","alembic":"0020_image_forensics"}},"meta":{"timestamp":"2026-09-30T22:54:53.755789+00:00"}}
```

---

## Minute 1: Situational Awareness & Geospatial Explorer (0:00 – 1:00)

### Step 1: Open Operations Dashboard (`http://localhost:8080`)
1. Navigate to `http://localhost:8080` in Chrome/Firefox.
2. Point out:
   - **Active Incident Counter**: Real-time aggregated incidents across India.
   - **Severity Breakdown Chart**: SQL-aggregated severe vs moderate events.
   - **Amber [DEMO] Badges**: Clearly distinguishes seeded demonstration fixtures from authentic field feeds.
   - **"Hide Demo Data" Toggle**: Toggle ON to demonstrate instant SQL-level exclusion of synthetic data (`?hide_demo=true`).

### Step 2: Interactive GIS Map & Spatial Clusters (`/map`)
1. Click **Live Map** in the primary navigation.
2. View bounded GeoJSON vector rendering with PostGIS spatial clusters (`LIMIT 500`).
3. Zoom into metropolitan hotspots (Mumbai, Bengaluru, Delhi).
4. Click an incident marker to open the quick-inspection popup showing category, severity, and current machine credibility score.

---

## Minute 2: Citizen Intake & Operator Triage Queue (1:00 – 2:00)

### Step 3: Citizen Incident Intake (`/report`)
1. Click **Submit Weather Report**.
2. Select Category: **Flooding & Waterlogging** (`FLOOD_WATERLOGGING`), Severity: **High**.
3. Use GPS coordinate picker or enter locality.
4. Attach an incident photograph and submit.
5. Point out the **Public Tracking ID** (e.g., `RPT-20260930-XXXX`) and show how citizens can track verification progress without requiring login.

### Step 4: Operator Authentication & Verification Queue (`/admin/triage`)
1. Click **Operator Login** (`/login`).
2. Log in with National DEOC Operator credentials:
   - **Email**: `operator@weather-platform.gov.in`
   - **Password**: `EmergencyOps2026!`
3. Verify authentication response:
```bash
$ curl -s -X POST http://localhost:8080/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"operator@weather-platform.gov.in","password":"EmergencyOps2026!"}'
{"success":true,"data":{"access_token":"eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...","token_type":"bearer","expires_in_seconds":86400,"user":{"id":"a1b2c3d4-e5f6-7890-abcd-1234567890ab","email":"operator@weather-platform.gov.in","full_name":"National DEOC Lead Operator","role":"OPERATOR","jurisdiction_code":"NATIONAL_DEOC","home_location_lat":null,"home_location_lng":null,"home_location_name":null,"alert_radius_km":25.0}}}
```
4. View the **Priority Triage Queue**: Incidents are ranked by severity and credibility, allowing emergency dispatchers to focus on high-priority verified threats.

---

## Minute 3: Deep Intelligence & Failure Recovery Drill (2:00 – 3:00)

### Step 5: Explainable Intelligence Inspection (`/incidents/:id`)

#### Scenario A (S1): Physical Weather Corroboration (Station Telemetry SUPPORTS)
Inspect incident `DEMO-SIM-S1-CORROB`:
```bash
$ curl -s http://localhost:8080/api/v1/reports/DEMO-SIM-S1-CORROB
{
  "success": true,
  "data": {
    "tracking_id": "DEMO-SIM-S1-CORROB",
    "title": "[SIMULATED S1] Heavy Rainfall Physical Corroboration Scenario",
    "category": {"code": "HEAVY_RAINFALL", "title": "HEAVY_RAINFALL"},
    "severity": "SEVERE",
    "verification_status": "VERIFIED",
    "physical_corroboration": {
      "overall_verdict": "SUPPORTS",
      "overall_provider_status": "OK",
      "total_contribution": 0.0941,
      "items": [
        {
          "variable": "rainfall_24h",
          "observed_value": 142.0,
          "unit": "mm/24h",
          "source": "DEMO_FIXTURE_STATION",
          "distance_km": 1.48,
          "verdict": "SUPPORTS",
          "explanation": "Measured 24h rainfall of 142.0 mm exceeds IMD heavy rain threshold (64.5 mm)",
          "is_simulated": true
        }
      ],
      "is_simulated": true
    },
    "physical_verdict": "SUPPORTS"
  }
}
```
*Show the UI card*: Shows physical sensor observation with +0.0941 credibility boost and clear English/Hindi explanation.

#### Scenario B (S2): Image Forensics & Photo Reuse Contradiction (CONTRADICTS)
Inspect incident `DEMO-SIM-S2-FORENSICS` (`ca5d2a00-aa08-42c6-907b-0274ba8ff64e`):
```bash
$ curl -s http://localhost:8080/api/v1/incidents/ca5d2a00-aa08-42c6-907b-0274ba8ff64e
{
  "success": true,
  "data": {
    "tracking_id": "DEMO-SIM-S2-FORENSICS",
    "title": "[SIMULATED S2] Image Forensics Reused Photo Scenario",
    "category": {"code": "FLOOD_WATERLOGGING", "title": "Flood Waterlogging"},
    "image_forensics": {
      "overall_verdict": "CONTRADICTS",
      "total_credibility_adjustment": -0.05,
      "image_count": 1,
      "is_simulated": true,
      "images": [
        {
          "phash": "a1b2c3d4e5f60000",
          "time_verdict": "SUPPORTS",
          "location_verdict": "SUPPORTS",
          "reuse_verdict": "CONTRADICTS",
          "matched_incident_ids": ["9170f4d7-0252-4094-9d49-3c4fdd04c725"],
          "overall_verdict": "CONTRADICTS",
          "credibility_adjustment": -0.05,
          "checks": [
            {
              "check_type": "IMAGE_REUSE",
              "verdict": "CONTRADICTS",
              "reason": "Perceptual hash match with separate past incident 9170f4d7-0252-4094-9d49-3c4fdd04c725"
            }
          ]
        }
      ]
    }
  }
}
```
*Show the UI card*: Highlights that although EXIF timestamp is valid, perceptual hashing detected photo reuse from past incident `9170f4d7...`, applying a safe -0.05 credibility adjustment.

---

### Step 6: Live Failure-Recovery Drill (Worker Kill & Restart)

Demonstrate platform resilience against unexpected background worker crashes:

```bash
# 1. Kill the primary ingestion worker process mid-load:
$ docker compose -f docker-compose.demo.yml --env-file .env.demo -p sih-demo kill worker-ingestion
Container sih-demo-worker-ingestion-1 Killing
Container sih-demo-worker-ingestion-1 Killed

# 2. Restart the worker container:
$ docker compose -f docker-compose.demo.yml --env-file .env.demo -p sih-demo up -d worker-ingestion
Container sih-demo-worker-ingestion-1 Starting
Container sih-demo-worker-ingestion-1 Started

# 3. Check worker container status:
$ docker compose -f docker-compose.demo.yml --env-file .env.demo -p sih-demo ps | grep worker-ingestion
sih-demo-worker-ingestion-1   sih-backend:latest   "python -m app.worke…"   worker-ingestion   Up 2 seconds (health: starting)   8000/tcp
```

**Measured Resilience Metrics (`logs/C_4.log:137, 161-164`)**:
- **Recovery Time**: **2.47 seconds** to resume processing.
- **Events Lost**: **0 (NONE)**. Redis Streams consumer groups preserve unacknowledged messages.
- **Events Duplicated**: **0 (NONE)**. Ingestion worker enforces idempotent deduplication on `external_id`.

---

### Step 7: Offline Fallback Architecture

If external internet connectivity fails during a field deployment or hackathon evaluation:
- Both `PHYSICAL_CORROBORATION_DEMO_FIXTURE_ENABLED=true` and `IMAGE_FORENSICS_DEMO_FIXTURE_ENABLED=true` are active in the demo environment.
- The platform automatically falls back to deterministic local mock fixtures without external HTTP calls to Open-Meteo or IMD.
- All offline fixtures are strictly tagged with `is_simulated = true`, guaranteeing transparent demonstration without falsifying operational telemetry.
