# External Services, Credentials & Configuration Guide

**Platform**: National Weather Big Data Analytics Platform (`SIH26069`)
**Status**: **SYNCHRONIZED WITH CURRENT CODE & WORKER TOPOLOGY**

---

## 1. Local Automated Setup vs. Deferred Cloud Actions

```
┌─────────────────────────────────────────────────────────────┐
│                 AUTOMATED LOCAL MVP SERVICES                │
│  - Local PostgreSQL 16 + PostGIS (Port 5432)                │
│  - Local Redis 7 Container (Port 6379)                      │
│  - Local MinIO S3 Object Storage (Ports 9000/9001)          │
│  - Local Alembic Migrations (0001 -> 0004)                  │
│  - 6 Standalone Worker Processes                            │
│  - Deterministic Seed Feeds & IMD/CWC/NDMA Local Adapters   │
└─────────────────────────────────────────────────────────────┘
                               ▲
                               │ Isolated Boundary
                               ▼
┌─────────────────────────────────────────────────────────────┐
│               DEFERRED PRODUCTION CLOUD ACTIONS             │
│  - Production Managed PostgreSQL with PostGIS (RDS/Neon)    │
│  - Production Managed Redis (AWS ElastiCache / Upstash)     │
│  - Production Cloud Storage (AWS S3 with Private IAM Bucket)│
│  - Production JWT Token Secret & OAuth2 Provider (Keycloak) │
│  - OpenTelemetry / Prometheus APM Monitoring Exporters      │
│  - Process Supervision Units (systemd / Kubernetes Pods)    │
└─────────────────────────────────────────────────────────────┘
```

---

## 2. External Provider Status & Verification Matrix

| Source Provider | Provider Type | Local Simulation / Test | Live Provider Status | Notes |
| :--- | :--- | :---: | :---: | :--- |
| **Demo Seed Feed** | Local Synthetic Feed | **Fully Verified** | **Development Utility** | Deterministic generator for Mumbai/Delhi/Bengaluru weather incidents (development/testing utility; not scheduled in production). |
| **IMD Nowcast** | Official Weather Feed | **Fully Verified (Mock)** | Not Live Verified | Ingests IMD AWS/CAP alert format; official gateway access requires official credentials/IP whitelisting (returns 401 gracefully). |
| **NDMA SACHET** | National Disaster Alerts | **Unit & Live Verified** | **LIVE PROVIDER VERIFIED** | Ingests official CAP/JSON disaster alert feeds via `https://sachet.ndma.gov.in/cap_public_website/FetchAllAlertDetails`; real HTTP POST verified with 66 parsed alerts. |
| **CWC NWDP** | Central Water Commission | **Unit & Live Verified** | **LIVE PROVIDER VERIFIED** | Ingests hydrological river water level telemetry via NWDP CKAN DataStore API (`https://nwdp.nwic.gov.in/api/3/action/datastore_search`); real HTTP GET verified with 5 live telemetry records parsed in the controlled Phase 18 proof (adapter default fetch limit: 50). |
| **GDELT Project** | Global News Feed | **Unit & Live Verified** | **LIVE PROVIDER VERIFIED** | Ingests disaster news via GDELT DOC 2.0 API (`http://api.gdeltproject.org/api/v2/doc/doc`); rate limit interval $\ge 5.0\text{s}$; snippets only in `ArtList` mode. |
| **Mastodon** | Social Emergency Feed | **Unit & Live Verified** | **LIVE PROVIDER VERIFIED** | Queries public disaster hashtags via `https://mastodon.social`; rate limit interval $\ge 1.0\text{s}$; text keyword matching without coordinate fabrication. |

---

## 3. Configuration Reference

All application settings are defined in [app/core/config.py](back-end/app/core/config.py) and populated from `.env`:

### 3.1 Database & Core Infrastructure

| Variable Name | Required | Default Value | Description |
| :--- | :---: | :--- | :--- |
| `DATABASE_URL` | **Yes** | `postgresql+asyncpg://postgres:postgres@localhost:5432/weather_platform` | Asynchronous PostgreSQL + PostGIS connection URI |
| `DATABASE_ECHO` | No | `False` | SQLAlchemy SQL statement logging flag |
| `REDIS_URL` | **Yes** | `redis://localhost:6379/0` | Redis connection URI for streams and caching |
| `REALTIME_STREAM_NAME` | No | `stream:weather:realtime` | Redis Stream key for browser SSE events |
| `REALTIME_STREAM_MAXLEN` | No | `10000` | Approximate cap on Redis Stream retention |

### 3.2 Outbox & Worker Settings

| Variable Name | Required | Default Value | Description |
| :--- | :---: | :--- | :--- |
| `OUTBOX_WORKER_ENABLED` | No | `True` | Enables/disables outbox worker poll loop |
| `OUTBOX_WORKER_BATCH_SIZE` | No | `50` | Number of outbox rows claimed per batch |
| `OUTBOX_WORKER_POLL_INTERVAL_SECONDS` | No | `1.0` | Active polling loop frequency / idle sleep (seconds) |
| `OUTBOX_WORKER_MAX_ATTEMPTS` | No | `5` | Maximum delivery attempts before moving to `DEAD_LETTER` |
| `OUTBOX_WORKER_PRUNE_INTERVAL_SECONDS` | No | `3600` | Interval in seconds between historical prune runs |
| `OUTBOX_WORKER_RETENTION_HOURS` | No | `72` | Retention window in hours before pruning `PUBLISHED` rows |

### 3.3 Media Storage (MinIO / S3)

| Variable Name | Required | Default Value | Description |
| :--- | :---: | :--- | :--- |
| `S3_ENDPOINT_URL` | No | `http://localhost:9000` | MinIO / S3 API endpoint |
| `S3_ACCESS_KEY_ID` | No | `minioadmin` | S3 / MinIO access key ID |
| `S3_SECRET_ACCESS_KEY` | No | `minioadmin` | S3 / MinIO secret access key |
| `S3_BUCKET_NAME` | No | `weather-media` | Object storage bucket for report attachments |
| `S3_REGION` | No | `us-east-1` | S3 region identifier |

### 3.4 External Feed Settings

| Variable Name | Required | Default Value | Description |
| :--- | :---: | :--- | :--- |
| `IMD_API_ENDPOINT` | No | `https://api.imd.gov.in/api/v1` | IMD official API base URL |
| `IMD_API_KEY` | No | `""` | IMD API key (requires official IP whitelisting / credentials) |
| `NDMA_SACHET_RSS_URL` | No | `https://sachet.ndma.gov.in/cap_public_website/FetchAllAlertDetails` | NDMA SACHET CAP alert URL (Public POST) |
| `CWC_NWDP_API_ENDPOINT`| No | `https://nwdp.nwic.gov.in/api/3/action/datastore_search` | CWC river telemetry API endpoint |
| `CWC_NWDP_RESOURCE_ID` | No | `d80798b9-4b11-4626-8b63-964202ba7216` | NWDP CKAN DataStore resource identifier |
| `CWC_FETCH_LIMIT` | No | `50` | Default record fetch limit for CWC queries |
| `GDELT_DOC_ENDPOINT` | No | `http://api.gdeltproject.org/api/v2/doc/doc` | GDELT 2.0 Document API endpoint (Public GET) |
| `GDELT_MIN_REQUEST_INTERVAL_SECONDS` | No | `5.0` | Monotonic rate limit spacing between outbound GDELT requests |
| `MASTODON_INSTANCE_URL`| No | `https://mastodon.social` | Mastodon instance URL (Public GET) |
| `MASTODON_MIN_REQUEST_INTERVAL_SECONDS` | No | `1.0` | Monotonic rate limit spacing between outbound Mastodon requests |
| `MASTODON_HASHTAGS` | No | `["mumbairains","delhirains","bengalururains","chennairains","assamfloods","monsoon","flood","cyclone","heatwave"]` | JSON-formatted array of monitored disaster hashtags |

---

## 4. Operational Runbook: How to Run the Entire Project Locally

The platform is architected around an event-driven decoupled topology. To run the full system on a local workstation:

### 4.1 Recommended Startup Order & Dependency Rationale

1. **Infrastructure Containers (`docker compose up -d`)**: Boots PostgreSQL 16 + PostGIS, Redis 7, and MinIO. All backend processes depend on these databases being healthy.
2. **Database Migrations (`alembic upgrade head`)**: Ensures all 17 relational tables, spatial indexes, and schema constraints are applied before application runtime starts.
3. **Backend API Server (`uvicorn app.main:app`)**: Starts FastAPI on `http://127.0.0.1:8000` to serve REST endpoints, citizen form submissions, and the SSE stream `/api/v1/events/stream`.
4. **Frontend Development Server (`npm run dev`)**: Starts the React/Vite client on `http://localhost:5173`.
5. **Transactional Outbox Worker (`run_outbox_worker`)**: Drains `realtime_outbox` in PostgreSQL and relays events to Redis streams (`stream:weather:realtime` and `stream:weather:orchestration`).
6. **Orchestration Dispatcher (`run_dispatcher`)**: Drains `stream:weather:orchestration` and executes the 5-stage `IncidentPipeline` on newly ingested incidents or late corroborations.
7. **Incident Ingestion Worker (`run_ingestion_worker`)**: Drains `stream:weather:events` and persists normalized incidents to PostgreSQL `weather_reports`.
8. **Observation Worker (`run_observation_worker`)**: Drains `stream:weather:observations` and persists physical sensor telemetry to `weather_observations`.
9. **Evidence Worker (`run_evidence_worker`)**: Drains `stream:weather:evidence` and persists news/social articles to `evidence_items`.
10. **Ingestion Polling Scheduler (`run_scheduler`)**: Polls external adapters (GDELT, Mastodon, NDMA, CWC, IMD) at configured intervals and publishes typed events to the Redis stream buffering tier.

---

### 4.2 Terminal Summary Table

| Terminal | Target Subsystem | Command | Operational Purpose |
| :---: | :--- | :--- | :--- |
| **1** | Docker Infrastructure | `docker compose up -d` | PostgreSQL 16 (5432), Redis 7 (6379), MinIO (9000/9001) |
| **2** | Migrations & Backend API | `alembic upgrade head && uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload` | Database schema initialization & FastAPI REST / SSE server |
| **3** | Frontend Web Client | `npm run dev` (run `npm install` on first setup) | React 18 / Vite operator dashboard on `http://localhost:5173` |
| **4** | Outbox Relay Worker | `python -m app.workers.run_outbox_worker` | Polls PostgreSQL `realtime_outbox`, publishes to Redis Streams |
| **5** | Orchestration Dispatcher | `python -m app.workers.run_dispatcher` | Consumes `stream:weather:orchestration`, runs 5-stage pipeline |
| **6** | Incident Ingestion Worker | `python -m app.workers.run_ingestion_worker` | Consumes `stream:weather:events`, writes to `weather_reports` |
| **7** | Observation Worker | `python -m app.workers.run_observation_worker` | Consumes `stream:weather:observations`, writes to `weather_observations` |
| **8** | Evidence Worker | `python -m app.workers.run_evidence_worker` | Consumes `stream:weather:evidence`, writes to `evidence_items` |
| **9** | Ingestion Polling Scheduler | `python -m app.workers.run_scheduler` | Polls registered external adapters, dispatches to Redis Streams |

---

### 4.3 Terminal-by-Terminal Copy-Paste Runbook

Open separate terminal tabs from the project root directory (`<project-root>`):

#### Terminal 1 — Infrastructure (Docker Compose)
```bash
cd <project-root>
docker compose up -d

# Verify container health
docker compose ps
```

#### Terminal 2 — Database Migrations & Backend API Server
```bash
cd <project-root>/back-end
source .venv/bin/activate

# Apply Alembic schema migrations (17 relational tables)
alembic upgrade head

# Launch FastAPI development server
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

#### Terminal 3 — Frontend Web Application
```bash
cd <project-root>/front-end
# Run npm install on initial checkout
npm install
# Start Vite development server
npm run dev
```

#### Terminal 4 — Transactional Outbox Relay Worker
```bash
cd <project-root>/back-end
source .venv/bin/activate
python -m app.workers.run_outbox_worker
```

#### Terminal 5 — Intelligence Orchestration Dispatcher
```bash
cd <project-root>/back-end
source .venv/bin/activate
python -m app.workers.run_dispatcher
```

#### Terminal 6 — Incident Ingestion Worker
```bash
cd <project-root>/back-end
source .venv/bin/activate
python -m app.workers.run_ingestion_worker
```

#### Terminal 7 — Observation Worker
```bash
cd <project-root>/back-end
source .venv/bin/activate
python -m app.workers.run_observation_worker
```

#### Terminal 8 — Evidence Worker
```bash
cd <project-root>/back-end
source .venv/bin/activate
python -m app.workers.run_evidence_worker
```

#### Terminal 9 — Ingestion Polling Scheduler (Optional / On-Demand)
```bash
cd <project-root>/back-end
source .venv/bin/activate
python -m app.workers.run_scheduler
```

---

### 4.3 System Health Checks

Verify that all subsystems are running and responsive:

```bash
# 1. FastAPI API Health & DB Connection Check
curl -s http://127.0.0.1:8000/api/v1/health | jq .

# 2. PostgreSQL / PostGIS Health Check
docker exec -it weather_postgres pg_isready -U postgres -d weather_platform

# 3. Redis Streams Health Check
docker exec -it weather_redis redis-cli ping

# 4. MinIO Object Storage Console
# Open in browser: http://localhost:9001 (User: minioadmin | Pass: minioadmin)

# 5. Frontend Client Application
# Open in browser: http://localhost:5173
```

---

### 4.4 Complete Data Pipeline Execution Flow

```
[External Adapter / Citizen Form]
             ↓
[stream:weather:events / observations / evidence]
             ↓
[Consumer Workers: run_ingestion / observation / evidence]
             ↓
[PostgreSQL Database (weather_reports / observations / evidence_items)]
      + [Transactional Outbox (realtime_outbox)]
             ↓
[Outbox Relay Worker: run_outbox_worker]
             ↓
[stream:weather:orchestration]  ──►  [stream:weather:realtime]
             ↓                                      ↓
[Orchestration Dispatcher: run_dispatcher]    [FastAPI SSE Stream]
             ↓                                      ↓
[5-Stage Intelligence Pipeline]               [Frontend RealtimeService]
             ↓                                      ↓
[Database: status=COMPLETED, credibility]     [React Query Invalidation]
      + [Outbox: report.intelligence_ready]         ↓
             ↓                                [Live Dashboard Update]
[Realtime Push to Browser Dashboard]
```

---

### 4.5 Stopping the Project

- **Stop Backend Workers & API**: Press `Ctrl+C` in each terminal window. All workers catch `SIGINT`/`SIGTERM` and shut down cleanly after draining current batch items.
- **Stop Frontend**: Press `Ctrl+C` in Terminal 3.
- **Stop Infrastructure Containers**:
  ```bash
  docker compose down
  # To stop and remove data volumes:
  # docker compose down -v
  ```

---

### 4.6 Troubleshooting Guide

| Issue / Symptom | Root Cause | Resolution |
| :--- | :--- | :--- |
| **Port 8000 already in use** | A stale Uvicorn instance is holding port 8000. | Run `lsof -i :8000` to find the process ID and run `kill -9 <PID>`. |
| **Database connection refused (`ConnectionRefusedError: [Errno 61]`)** | PostgreSQL container is not started or still initializing. | Run `docker compose up -d postgres` and wait until `docker exec weather_postgres pg_isready` returns ready. |
| **Redis connection error (`ConnectionRefusedError`)** | Redis container is not running on port 6379. | Run `docker compose up -d redis` and verify with `redis-cli ping`. |
| **IMD Adapter HTTP 401 Unauthorized** | Official IMD API endpoint requires credentials / IP whitelisting. | Expected behavior in unauthenticated environments; adapter raises `AdapterFetchError` and scheduler continues with remaining live feeds without crashing. |
| **GDELT HTTP 429 Too Many Requests** | Querying GDELT faster than once every 5 seconds. | `GDELTNewsAdapter._apply_rate_limit()` enforces $\ge 5.0\text{s}$ spacing automatically. If manual testing triggered a 429, wait 6 seconds before retrying. |
| **Reports stuck in `QUEUED` state** | Neither `run_outbox_worker` nor `run_dispatcher` is running. | Ensure both `python -m app.workers.run_outbox_worker` and `python -m app.workers.run_dispatcher` are active in background terminals. |
| **SSE Events not received in browser** | Browser SSE connection disconnected or blocked by proxy. | Inspect browser Network tab for `/api/v1/events/stream`; verify `run_outbox_worker` is relaying events to `stream:weather:realtime`. |
