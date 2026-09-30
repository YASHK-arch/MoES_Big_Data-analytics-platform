# National Weather Big Data Analytics Platform

**Smart India Hackathon 2026 — Problem Statement ID**: `SIH26069`
**Domain**: Big Data Analytics / Disaster Management / Geospatial Intelligence
**Status**: **SYNCHRONIZED WITH CURRENT CODE & WORKER RUNTIMES**
**Baseline Git Commit**: `cca26615d1743078932527ec1e89507ac417fa03`

---

## 1. Project Overview & Mission

The **National Weather Big Data Analytics Platform** is an AI-augmented big data analytics and geospatial intelligence platform engineered to ingest, corroborate, and analyze multi-source meteorological feeds and crowdsourced citizen incident reports during extreme weather emergencies.

The platform bridges the gap between high-altitude meteorological observations (IMD radar, AWS, hydrological stations) and localized ground realities (urban waterlogging, flash floods, landslides, storm damage) through:
- **High-Throughput Multi-Source Ingestion**: Citizen web submissions with photo uploads, IMD automatic weather stations, NDMA SACHET alerts, CWC flood telemetry, Mastodon posts, and GDELT disaster news.
- **Intelligent Pipeline**: Rule-based categorization, spatial-temporal deduplication clustering ($R \le 2.5\text{ km}$, $\Delta T \le 120\text{ min}$), and digital evidence/physical sensor corroboration.
- **Explainable Credibility Scoring**: Deterministic, multi-factor scoring engine ($0.0000$ to $0.9800$) providing transparent driver breakdowns and uncertainty flags.
- **Interactive Geospatial Dashboards**: Live Leaflet GIS map with bounded GeoJSON vector layers (`LIMIT 500`), server-aggregated weather analytics, and priority-ranked triage queues for disaster management authorities (NDRF, SDRF, DEOCs).
- **Transactional Real-Time Streaming & Reactive Corroboration**: Atomic outbox pattern in PostgreSQL, dedicated worker relay, 6 dedicated Redis Streams topics, persistent FastAPI Server-Sent Events (`GET /api/v1/events/stream`), late observation/evidence reactive corroboration, and automatic React Query cache invalidation.

---

## 2. High-Level Architecture

```
[Citizen Reports, IMD Telemetry, CWC, NDMA, Mastodon, GDELT, DemoSeed]
                              │
                              ▼
            [Ingestion Scheduler & Ingestion Adapters]
                              │
                              ▼
         [Redis Streams Buffering Tier (6 Streams)]
    ├── stream:weather:events       → run_ingestion_worker
    ├── stream:weather:observations → run_observation_worker
    ├── stream:weather:evidence     → run_evidence_worker
    ├── stream:weather:orchestration→ run_dispatcher (5-Stage Pipeline)
    ├── stream:weather:realtime     → FastAPI SSE (/api/v1/events/stream)
    └── stream:weather:dead_letter  → Dead Letter Sink (Programmatic/Manual Replay)
                              │
                              ▼
        [PostgreSQL 16 + PostGIS] ◄──► [MinIO / S3 Storage]
          ├── weather_reports (QUEUED → COMPLETED)
          ├── duplicate_clusters & members
          ├── weather_observations & evidence_items
          ├── verification_events (immutable audit log)
          └── realtime_outbox (status = 'PENDING')
                              │
                              ▼ (SKIP LOCKED Batch Polling)
         [Transactional Outbox Worker: run_outbox_worker]
                              │
                              ▼ (XADD to Realtime & Orchestration)
             [FastAPI SSE: /api/v1/events/stream]
                              │
                              ▼ (Deduplicated Stream Push)
            [Frontend RealtimeService Singleton]
                              │
                              ▼ (Targeted Query Invalidation)
            [TanStack React Query Cache Layer]
                              │
                              ▼ (Authoritative REST Refetch)
      [React 18 + Leaflet + Recharts Operations Dashboard]
```

---

## 3. Core Semantic & Architectural Guarantees

1. **Machine Credibility $\ne$ Human Ground Truth**: `credibility_score` ($0.0000$ to $0.9800$) is an algorithmic machine assessment. `verification_status` (`PENDING`, `UNDER_REVIEW`, `VERIFIED`, `REJECTED`, `DUPLICATE`) is the authoritative operational state set by human operators.
2. **Crowd Volume $\ne$ Independent Confirmations**: Duplicate reports are clustered with a single diminishing-returns sub-signal, never summed as independent corroborating proofs.
3. **Stage Execution $\ne$ Domain Corroboration**: Orchestration stage outcomes (`SUCCESS_WITH_RESULTS`) signify that an analysis stage executed and found telemetry, not that the incident was verified.
4. **Zero Client-Side Intelligence Math**: The frontend is a pure presentation consumer and never recalculates credibility, cluster embeddings, or corroboration weights.
5. **No Binary Media in Relational Database**: All images and videos reside in S3/MinIO; only metadata, dimensions, SHA-256 checksums, and signed URIs are stored in PostgreSQL (`report_media`).
6. **Delivery Semantics**: At-least-once stream delivery with bounded frontend deduplication (1,000 items). Relevant processing paths are designed and tested to tolerate duplicate delivery without unverified claims of exactly-once.

---

## 4. Current Implementation Status

| Subsystem / Phase | Scope & Implementation Status | Verification Status |
| :--- | :--- | :---: |
| **Phase 0–3: Foundation & Schemas** | PostgreSQL 16 + PostGIS, 15 domain models (17 relational tables), spatial GiST indexes, Alembic migrations (`0001`–`0004`). | **COMPLETED & VERIFIED** |
| **Phase 4: Citizen Intake** | Multi-part report intake, photo upload to MinIO, GPS geocoding, public tracking. | **COMPLETED & VERIFIED** |
| **Phase 5–6: Ingestion & Streaming** | Adapters for IMD AWS, NDMA SACHET, CWC, Mastodon, GDELT; Redis Stream workers. | **COMPLETED & VERIFIED** |
| **Phase 7–9: AI Intelligence Engine** | Deduplication clustering, digital evidence linking, physical station corroboration, explainable credibility scorer. | **COMPLETED & VERIFIED** |
| **Phase 10: Executive Dashboard** | Live Leaflet map, KPI telemetry cards, category breakdown charts, bounded GeoJSON queries. | **COMPLETED & VERIFIED** |
| **Phase 11: Verification & Triage** | Priority triage queue, side-by-side evidence inspection, status-aware action drawer, immutable audit log. | **COMPLETED & VERIFIED** |
| **Incident Intelligence Frontend** | Multi-filter Incident Explorer (`/incidents`), 5-dimension Deep-Dive (`/incidents/:id`), Operator Portal (`/login`). | **COMPLETED & VERIFIED** |
| **Phase 12: Real-Time Event Streaming** | Transactional outbox pattern, dedicated worker, Redis Streams buffer, FastAPI SSE (`GET /api/v1/events/stream`), and React Query live cache invalidation. | **COMPLETED & VERIFIED** |
| **Phase 13: Analytics Platform & Map** | Server-aggregated trends (`/api/v1/analytics/trends`), summary metrics, regional demographics (`/api/v1/analytics/regional`), and bounded GeoJSON queries. | **COMPLETED & VERIFIED** |
| **Phase 14: Ingestion & Intelligence Runtime** | Multi-stream Redis topology, 6 standalone worker processes, continuous Scheduler -> Worker -> DB -> Intelligence -> SSE chains. | **COMPLETED & VERIFIED** |
| **Phase 15: Truth Audit & Documentation** | Authoritative synchronization of all documentation, contracts, schemas, and runtime procedures. | **COMPLETED & VERIFIED** |
| **Phase 16: Reactive Late Corroboration** | Late observation & evidence ingestion re-triggers credibility scoring and pushes live updates via SSE to frontend without page reload. | **COMPLETED & VERIFIED** |
| **Phase 17: Live GDELT & Mastodon Integration** | Genuine live HTTP ingestion from GDELT DOC 2.0 and Mastodon public hashtag timelines; persistence to `evidence_items` and intelligence corroboration. | **COMPLETED & VERIFIED** |
| **Phase 18: NDMA/CWC Live Proof & Duplicate Truth** | Live HTTP verification of NDMA SACHET and CWC NWDP feeds; verified domain-boosted TF-IDF vectorizer (`sparse_tfidf_ngram_v1`) duplicate path. | **COMPLETED & VERIFIED** |
| **Production Auth & Supervision** | Institutional JWT/RBAC authentication and multi-worker process supervision (`systemd`/Kubernetes). | *Deferred Production Hardening* |

---

## 5. Quickstart & Local Setup

### Prerequisites
- Python 3.11+ (or Python 3.14)
- Node.js 18+ and npm
- Docker & Docker Compose (for PostgreSQL/PostGIS, Redis, and MinIO)

### 1. Start Infrastructure Containers
```bash
docker compose up -d
```

### 2. Apply Database Migrations & Start Backend API Server
```bash
cd back-end
source .venv/bin/activate

# Apply Alembic schema migrations (17 relational tables)
alembic upgrade head

# Start FastAPI server on port 8000
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

### 3. Start Background Workers
In separate terminal tabs / background sessions:
```bash
cd back-end
source .venv/bin/activate

# Transactional Outbox Relay Worker (Relays DB outbox to Redis Streams)
python -m app.workers.run_outbox_worker

# Orchestration Dispatcher (Executes 5-Stage Intelligence Pipeline)
python -m app.workers.run_dispatcher

# Ingestion Stream Consumers
python -m app.workers.run_ingestion_worker
python -m app.workers.run_observation_worker
python -m app.workers.run_evidence_worker

# Ingestion Polling Scheduler (Optional / On-Demand for Live Feeds)
python -m app.workers.run_scheduler
```

### Terminal Summary Table

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

The application is available at `http://localhost:5173`.
Backend health endpoint: `curl http://127.0.0.1:8000/api/v1/health`
For detailed configuration, environment variables, and troubleshooting, consult [docs/EXTERNAL_SETUP.md](docs/EXTERNAL_SETUP.md).

---

## 6. Testing & Quality Verification

### Backend Quality Gates:
```bash
cd back-end
.venv/bin/pytest -q
.venv/bin/mypy app tests
.venv/bin/ruff check .
.venv/bin/ruff format --check .
```

### Frontend Quality Gates:
```bash
cd front-end
npm run typecheck
npm run lint
npx vitest run
npm run build
```

---

## 7. Live vs. Simulated (Demo) Data

To provide a fully deterministic and compelling evaluation environment during Hackathon presentations while ensuring production readiness, the platform strictly segregates live real-world data from simulated test fixtures:

- **Database Flag & Indexing**: The `weather_reports` table includes a dedicated, indexed boolean column `is_demo` (Alembic revision `0017_report_is_demo`).
- **Automatic Classification & Backfill**: Any incident seeded with the `[DEMO]` title prefix or a `DEMO-` tracking identifier is automatically flagged with `is_demo = true`. Real citizen submissions and operational telemetry default to `is_demo = false`.
- **Visible Cues**: An amber **DEMO** badge is prominently rendered across the UI:
  - Situational Awareness Dashboard (recent incident feed)
  - Interactive Leaflet Map (marker popups and selected incident inspector)
  - Unified Incident Cards and Incident Detail Hero
- **"Hide Demo Data" Toggle**:
  - Available on the Dashboard, Live Map, and Incident Directory filter bars.
  - **Default**: `OFF` in the demo stack (`docker-compose.demo.yml`) so evaluators immediately see active scenario fixtures.
  - **Live Filter**: Toggling to `ON` immediately filters out all simulated demo reports, showing only authentic citizen reports and verified field feeds.
- **REST & Geospatial Filtering**: All query endpoints (`/api/v1/incidents`, `/api/v1/reports`, `/api/v1/geo/incidents`, `/api/v1/dashboard/summary`) accept `?hide_demo=true` for SQL-level filtering without client-side overhead.
