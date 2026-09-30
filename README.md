# National Weather Big Data Analytics Platform

**Smart India Hackathon 2026 — Problem Statement ID**: `SIH26069`
**Domain**: Big Data Analytics / Disaster Management / Geospatial Intelligence
**Status**: **SYNCHRONIZED WITH CURRENT CODE & WORKER RUNTIMES**
**Baseline Git Commit**: `ee8e17d` (Round 9b — R2 RSS · R3 Admin · R4 Classification · R5 Demo · R1 data.gov stub)

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
[Citizen Reports, IMD Telemetry, CWC, NDMA, Mastodon, GDELT, RSS News, DemoSeed]
                              │
                              ▼
            [Ingestion Scheduler & Ingestion Adapters]
            (IMD, NDMA, CWC, Mastodon, GDELT, RSS, OpenMeteo, DemoSeed)
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

## 4. Feature Status Table

| Feature / Subsystem | Status | Scope & Implementation Details | Configuration / Gate Flag |
| :--- | :---: | :--- | :--- |
| **Citizen Incident Reporting** | **Implemented** | Multipart form with GPS location, category selection, severity, photo uploads to MinIO/S3, and public tracking page. | None (Core) |
| **Operator Triage & Verification** | **Implemented** | Priority-ranked queue (`/admin/triage`), state transition enforcement (`PENDING` -> `UNDER_REVIEW` -> `VERIFIED`/`REJECTED`/`DUPLICATE`), audit logging. | None (Core) |
| **Geospatial GIS Map Explorer** | **Implemented** | Leaflet interactive map with bounded GeoJSON vector layer (`/api/v1/geo/incidents?limit=500`), severity-coded markers, and PostGIS spatial clustering. | None (Core) |
| **Deduplication & Clustering** | **Implemented** | Spatial-temporal clustering ($R \le 2.5\text{ km}$, $\Delta T \le 120\text{ min}$) and domain-boosted TF-IDF vectorization (`sparse_tfidf_ngram_v1`). | None (Core) |
| **Explainable Credibility Scoring** | **Implemented** | Deterministic multi-factor scorer ($0.0000$ to $0.9800$) with source priors, crowd volume, digital evidence, and positive/negative drivers. | None (Core) |
| **Transactional Outbox & SSE** | **Implemented** | PostgreSQL `realtime_outbox` table with `FOR UPDATE SKIP LOCKED` relay worker to Redis Streams and FastAPI Server-Sent Events (`/api/v1/events/stream`). | None (Core) |
| **Model-Based Physical Corroboration** | **Flag-gated** | Open-Meteo archive/forecast numerical model corroboration, 15-min grid-hour cache, pure evaluator, UI card with English/Hindi explanations. | `PHYSICAL_CORROBORATION_ENABLED` (demo env `true`, code default `false`) |
| **IMD Station Corroboration** | **Stub / Mock** | India Meteorological Department (IMD) Automatic Weather Station corroboration operates via deterministic mock/fixture providers. Live station API requires official MoES credentials. | `PHYSICAL_CORROBORATION_DEMO_FIXTURE_ENABLED` |
| **Image Forensics & Reused Photo Detection** | **Flag-gated** | Perceptual hashing (pHash DCT-II, dHash) across incident photos, safe EXIF timestamp/GPS cross-checks, weak credibility adjustment ($\pm 0.05$). | `IMAGE_FORENSICS_ENABLED` (demo env `true`, code default `false`) |
| **Location-Mismatch Signal** | **Flag-gated** | Text-to-GPS distance verification and credibility penalty for reports where free-text mentions a distant locality. | `LOCATION_MISMATCH_ENABLED` (default `false`) |
| **Autonomous Drone & IoT Telemetry** | **Planned** | Autonomous video stream analysis from disaster reconnaissance UAVs and municipal IoT water-level sensor telemetry. | Future Roadmap |

---

## 5. One-Command Demo Stack Start

The platform includes a containerized demonstration stack running 11 Docker services (Nginx web client at `:8080`, 2 Uvicorn API workers, PostgreSQL 16 + PostGIS, Redis 7, MinIO S3, and 6 background workers).

```bash
# Start and build the entire demo stack in one command:
./scripts/demo-up.sh

# Seed default operator accounts and 500 demo incidents:
./scripts/demo-seed.sh
```

- **Web Dashboard**: [http://localhost:8080](http://localhost:8080)
- **Operator Credentials**: `operator@weather-platform.gov.in` / `EmergencyOps2026!`
- **Citizen Demo Account**: `citizen@example.com` / `CitizenPassword2026!`
- **Health Check**: `curl http://localhost:8080/health`
- **Readiness Check**: `curl http://localhost:8080/ready`

---

## 6. Measured Numbers & Benchmark Evidence

All performance metrics and test results in this section were measured during this session on the isolated demo stack. Raw command outputs are cited with exact log paths.

- **Backend Test Suite**: **609 passed**, 0 failed in 125.15s with randomized execution seed 42 (`logs/C_2.log:443`).
- **Frontend Quality Gates**: **190 tests passed**, 0 TypeScript errors, 0 ESLint warnings, production bundle built in 2.15s (`logs/C_2.log:170-205`).
- **Demo Container Memory**: **1,514 MiB (~1.51 GB)** total memory across all 11 running containers, comfortably under the 3.5 GB platform deployment ceiling (`logs/C_3.log:82-93`).
- **API Load Performance** (Measured with Locust 2.46.6 on Apple M4 10-core, 16 GB RAM; `logs/C_4.log`):
  - **10 Concurrent Users**: 254.31 RPS, median latency 5 ms, p95 17 ms, p99 49 ms, 0.00% error rate (`logs/C_4.log:28-40`).
  - **50 Concurrent Users**: 570.07 RPS, median latency 29 ms, p95 150 ms, p99 260 ms, 0.00% error rate (`logs/C_4.log:59-71`).
  - **100 Concurrent Users**: 576.33 RPS, median latency 35 ms, p95 460 ms, p99 760 ms, 0.00% error rate (`logs/C_4.log:90-102`).
  - **Cache Hit vs. Cache Miss Latencies** (`logs/C_4.log`):
    - *Cache Hit (`/dashboard/summary`)*: p50 = 3 ms (10u), 12 ms (50u), 15 ms (100u).
    - *Cache Hit (`/geo/incidents?limit=500`)*: p50 = 5 ms (10u), 24 ms (50u), 27 ms (100u).
    - *Cache Miss (`/dashboard/summary`)*: p50 = 7 ms (10u), 49 ms (50u), 100 ms (100u).
    - *Cache Miss (`/geo/incidents?limit=500`)*: p50 = 5 ms (10u), 43 ms (50u), 95 ms (100u).
- **Direct Stream Ingestion Throughput**: **14,913.72 events/sec** published directly to `stream:weather:events` via Redis Streams pipeline (`logs/C_4.log:109`).
- **Worker Resiliency & Failure Recovery**: Mid-load abrupt termination of `sih-demo-worker-ingestion-1` recovered to operational health in **2.47 seconds** with **0 lost events** and **0 duplicate records** across the 200-event test batch (`logs/C_4.log:137, 161-164`).

---

## 7. System Limitations & Technical Boundaries

To maintain rigorous scientific and engineering integrity, the platform explicitly acknowledges the following operational boundaries:

1. **IMD Automatic Weather Station Telemetry is Mock-Only**: Station-based meteorological corroboration against India Meteorological Department (IMD) ground stations currently operates through deterministic simulation fixtures. Direct live telemetry ingestion requires MoES/IMD station credentials and API gateway whitelisting that are not publicly provisioned.
2. **Open-Meteo Provides Numerical Model Data, Not Station Sensor Data**: Live physical weather corroboration uses Open-Meteo's historical and forecast APIs, which serve numerical weather prediction model runs (ECMWF, GFS, ERA5 reanalysis). These provide gridded meteorological estimates rather than direct physical sensor measurements from ground stations.
3. **Benchmarks are Synthetic or Agent-Authored**: All performance benchmarks, stress loads, and evaluation datasets (including the 200-incident credibility baseline and the 60-post multilingual classification evaluation) were synthetically generated or curated for verification purposes, not drawn from active emergency operations.
4. **Real-World Predictive Accuracy is Unmeasured**: The statistical accuracy (precision, recall, false-positive/negative rates) of physical weather corroboration, image forensics, and location-mismatch penalties on authentic, uncurated field disaster data has not been empirically measured or clinically validated.
5. **Perceptual Hashing (pHash) Was Evaluated on Synthetic Image Perturbations Only**: Hamming distance thresholds (pHash $\le 10$, dHash $\le 8$) were empirically calibrated against controlled synthetic perturbations (rescaling, Gaussian blur, compression). Resilience against aggressive cross-platform transcoding (WhatsApp image re-compression, social media downsampling) remains to be field-tested on real crowdsourced imagery.
6. **Location-Mismatch Penalty is Disabled by Default**: The `LOCATION_MISMATCH_ENABLED` feature flag defaults to `false` in code and deployment to avoid penalizing legitimate citizen reports until regional geocoding gazetteers, colloquial landmark names, and transliterated district spellings are comprehensively validated.

---

## 8. Manual Local Developer Setup (Without Docker)

For manual step-by-step local development without Docker Compose, see [docs/EXTERNAL_SETUP.md](docs/EXTERNAL_SETUP.md) and [docs/MANUAL_TESTING_GUIDE.md](docs/MANUAL_TESTING_GUIDE.md).

