# System Architecture & Technical Design

**Problem Statement ID**: `SIH26069`
**Platform**: National Weather Big Data Analytics Platform
**Status**: **SYNCHRONIZED WITH CURRENT CODE & WORKER RUNTIMES**
**Baseline Git Commit**: `ee8e17d` (Round 9b)

---

## 1. System Overview & End-to-End Topology

The platform is architected as an asynchronous, event-driven data processing pipeline backed by a high-performance spatial database (PostgreSQL 16 + PostGIS) and a reactive presentation layer (React 18 + Leaflet + TanStack Query).

```mermaid
flowchart TD
    subgraph Ingestion_Layer["1. Ingestion & Multi-Source Feeds"]
        CR["Citizen Reports (Multipart HTTP /form)"]
        SCHED["Ingestion Scheduler (run_scheduler)"]
        IMD["IMD AWS Telemetry Adapter"]
        NDMA["NDMA SACHET Alert Adapter"]
        CWC["CWC River Flood Gauge Adapter"]
        MAST["Mastodon Emergency Social Adapter"]
        GDELT["GDELT Disaster News Adapter"]
        RSS["RSS Indian Weather News Adapter (R2)"]
        OMETEO["OpenMeteo Forecast Adapter"]
        SEED["Demo Seed Ingestion Adapter"]
    end

    subgraph Streaming_Buffers["2. Redis Streams Buffering Tier"]
        STR_EVT[("stream:weather:events")]
        STR_OBS[("stream:weather:observations")]
        STR_EVD[("stream:weather:evidence")]
        STR_ORCH[("stream:weather:orchestration")]
        STR_RT[("stream:weather:realtime")]
        STR_DLQ[("stream:weather:dead_letter")]
    end

    subgraph Consumer_Workers["3. Modular Consumer Worker Daemons"]
        W_ING["Ingestion Worker (run_ingestion_worker)"]
        W_OBS["Observation Worker (run_observation_worker)"]
        W_EVD["Evidence Worker (run_evidence_worker)"]
        W_OUT["Outbox Worker (run_outbox_worker)"]
        W_DISP["Orchestration Dispatcher (run_dispatcher)"]
    end

    subgraph Intelligence_Engine["4. 5-Stage Incident Intelligence Pipeline"]
        S_LOC["1. LOCATION (Geocoding & Spatial Geometry)"]
        S_DUP["2. DUPLICATE (PostGIS ST_DWithin + TF-IDF Vectorizer)"]
        S_EVD["3. EVIDENCE (Cross-Platform Digital News Linking)"]
        S_OBS["4. OBSERVATION (Physical Weather Sensor Corroboration)"]
        S_CRD["5. CREDIBILITY (Explainable Multi-Factor Scoring)"]
    end

    subgraph Storage_Tier["5. System of Record & Object Storage"]
        PG[("PostgreSQL 16 + PostGIS (17 Tables, SRID 4326)")]
        MINIO[("MinIO / S3 Storage (Media Blobs)")]
        OUTBOX[("Transactional Outbox (realtime_outbox)")]
    end

    subgraph Presentation_Layer["6. Operator & Analytics Frontend"]
        SSE["FastAPI SSE Transport (/api/v1/events/stream)"]
        RTS["RealtimeService Singleton (EventSource)"]
        CACHE["TanStack React Query Cache"]
        DASH["Dashboard & KPI Telemetry (/dashboard)"]
        MAP["Live GIS Leaflet Map (/map)"]
        QUEUE["Verification Queue (/admin/queue)"]
        ADMIN["Admin Export / Bulk / Audit Log (/admin/audit-log)"]
        ANALYTICS["Weather Analytics Platform (/analytics)"]
        EXPLORER["Incident Explorer & Deep-Dive (/incidents)"]
    end

    %% Ingestion to Streams
    SCHED --> IMD & NDMA & CWC & MAST & GDELT & RSS & OMETEO & SEED
    SCHED -->|Normalized Events| STR_EVT
    SCHED -->|Sensor Metrics| STR_OBS
    SCHED -->|News / Media| STR_EVD

    %% Streams to Workers
    STR_EVT --> W_ING
    STR_OBS --> W_OBS
    STR_EVD --> W_EVD

    %% Persistence
    W_ING -->|Persist Reports (QUEUED)| PG
    W_ING -->|Stage Outbox Trigger| OUTBOX
    W_OBS -->|Persist Sensor Data| PG
    W_EVD -->|Persist News Articles| PG

    %% Citizen Intake
    CR -->|POST /api/v1/reports| PG
    CR -->|Upload Photos| MINIO
    CR -->|Stage dual outbox rows| OUTBOX

    %% Outbox Relay
    OUTBOX -->|SKIP LOCKED Poll| W_OUT
    W_OUT -->|Relay Orchestration Triggers| STR_ORCH
    W_OUT -->|Relay UI SSE Events| STR_RT

    %% Dispatcher to Pipeline
    STR_ORCH --> W_DISP
    W_DISP --> S_LOC --> S_DUP --> S_EVD --> S_OBS --> S_CRD
    S_CRD -->|Persist Intelligence & COMPLETED| PG
    S_CRD -->|Stage report.intelligence_ready| OUTBOX

    %% Realtime Push to Frontend
    STR_RT --> SSE --> RTS --> CACHE
    CACHE --> DASH & MAP & QUEUE & ANALYTICS & EXPLORER
```

---

## 2. Redis Streams Topology & Responsibilities

The platform utilizes **6 dedicated Redis streams** with explicit architectural roles:

| Stream Key | Publisher | Consumer | Purpose | Payload Schema |
| :--- | :--- | :--- | :--- | :--- |
| `stream:weather:events` | `run_scheduler` | `run_ingestion_worker` (`group:weather:ingestion`) | Buffers raw incident events from external adapters | `NormalizedIngestionEvent` |
| `stream:weather:observations` | `run_scheduler` | `run_observation_worker` (`group:weather:observations`) | Buffers physical sensor/river gauge telemetry | `NormalizedObservationEvent` |
| `stream:weather:evidence` | `run_scheduler` | `run_evidence_worker` (`group:weather:evidence`) | Buffers digital news articles and social posts | `NormalizedEvidenceEvent` |
| `stream:weather:orchestration` | `run_outbox_worker` & `RealtimeService` | `run_dispatcher` (`group:weather:orchestrators`) | Asynchronous triggers executing the 5-stage `IncidentPipeline` | `OrchestrationEvent` |
| `stream:weather:realtime` | `run_outbox_worker` & `RealtimeService` | Browser clients via `/api/v1/events/stream` | Real-time UI updates and cache invalidation | `RealtimeEvent` envelope |
| `stream:weather:dead_letter` | `OrchestrationDispatcher` & `RealtimeOutboxWorker` | Operational DLQ monitor | Poison pills and exhausted retry events | `DeadLetterRecord` |

---

## 3. Worker Process Topology & Execution

The backend architecture separates operational responsibilities into **6 modular standalone worker daemons**:

```
┌────────────────────────┬────────────────────────────────────────────────────────────────────────┐
│ Worker Entrypoint      │ Operational Responsibility                                             │
├────────────────────────┼────────────────────────────────────────────────────────────────────────┤
│ run_scheduler          │ Polls registered ingestion adapters and dispatches typed stream events │
│ run_ingestion_worker   │ Drains stream:weather:events, persists reports (QUEUED), stages outbox │
│ run_observation_worker │ Drains stream:weather:observations, persists to weather_observations   │
│ run_evidence_worker    │ Drains stream:weather:evidence, persists to evidence_items             │
│ run_outbox_worker      │ Drains PostgreSQL realtime_outbox, relays to realtime & orchestration  │
│ run_dispatcher         │ Drains stream:weather:orchestration, executes 5-stage IncidentPipeline │
└────────────────────────┴────────────────────────────────────────────────────────────────────────┘
```

### Execution Commands:
```bash
# Ingestion scheduler
python -m app.workers.run_scheduler

# Stream consumer workers
python -m app.workers.run_ingestion_worker
python -m app.workers.run_observation_worker
python -m app.workers.run_evidence_worker

# Transactional outbox relay worker
python -m app.workers.run_outbox_worker

# Intelligence pipeline orchestration dispatcher
python -m app.workers.run_dispatcher
```

---

## 4. Canonical 5-Stage Intelligence Pipeline

The intelligence subsystem processes reports through a deterministic 5-stage pipeline:

```
[Incident Ingested]
        ↓
  1. LOCATION       → Resolves coordinates/WKT geometry into PostGIS Point (SRID 4326)
        ↓
  2. DUPLICATE      → Queries candidates via ST_DWithin (2.5 km) & TF-IDF n-gram cosine similarity
        ↓
  3. EVIDENCE       → Queries spatial/temporal evidence_items and creates incident_evidence_links
        ↓
  4. OBSERVATION    → Queries proximate weather_observations and creates corroboration records
        ↓
  5. CREDIBILITY    → Evaluates multi-factor explainability score (0.0000 - 0.9800) and drivers
        ↓
[Persist COMPLETED] → Stages report.intelligence_ready event to realtime_outbox
```

### Stage Definitions:
1. **`LOCATION`**: Normalizes text addresses or raw latitude/longitude into a validated PostGIS point geometry (`SRID 4326`) and assigns location resolution status (`RESOLVED`, `STRUCTURED`, `FALLBACK`).
2. **`DUPLICATE`**: Identifies co-located, concurrent reports within spatial radius ($R \le 2500\text{ m}$) and time window ($\Delta T \le 3\text{ hours}$), calculates semantic text similarity via domain-boosted TF-IDF n-grams (`sparse_tfidf_ngram_v1`), and updates `duplicate_clusters` and `duplicate_members`.
3. **`EVIDENCE`**: Corroborates reports against digital news articles, social posts, and official alerts stored in `evidence_items`, generating `incident_evidence_links`.
4. **`OBSERVATION`**: Evaluates proximate Automated Weather Station (IMD AWS) rainfall/wind readings and river level gauges stored in `weather_observations`, generating `incident_observation_corroborations`.
5. **`CREDIBILITY`**: Computes an explainable mathematical credibility score ($0.0000$ to $0.9800$) combining source trust priors, crowd volume signal, physical sensor delta, and digital evidence corroboration.

---

## 5. End-to-End Data Paths

### 5.1 Citizen Report Ingestion Path
```
POST /api/v1/reports (Multipart form)
    ↓
PostgreSQL ACID Transaction
    ├── weather_reports (status = 'QUEUED', tracking_id = 'RPT-...')
    ├── report_media (storage metadata in MinIO)
    ├── realtime_outbox (event_type = 'report.created')
    └── realtime_outbox (event_type = 'orchestration.incident_ingested')
    ↓
Realtime Outbox Worker (run_outbox_worker)
    ├── Relays 'report.created' → stream:weather:realtime (UI SSE)
    └── Relays 'orchestration.incident_ingested' → stream:weather:orchestration
    ↓
Orchestration Dispatcher (run_dispatcher)
    └── Executes IncidentPipeline (LOCATION → DUPLICATE → EVIDENCE → OBSERVATION → CREDIBILITY)
    ↓
Database Update
    └── weather_reports (status = 'COMPLETED', credibility_score = 0.537)
```

### 5.2 External Adapter Ingestion Path
```
run_scheduler (polls IMD, NDMA, CWC, GDELT, Mastodon, DemoSeed)
    ↓
Redis Stream (stream:weather:events)
    ↓
Ingestion Worker (run_ingestion_worker)
    ├── Persists WeatherReport (processing_status = 'QUEUED')
    └── Stages outbox row (orchestration.incident_ingested)
    ↓
Outbox Worker → Dispatcher → IncidentPipeline → COMPLETED
```

### 5.3 Reactive Late Corroboration Flow (Phase 16)
```
New Physical Observation or Digital Evidence Ingested
    ↓
ObservationService / EvidenceService Persists Record to DB
    + Stages RealtimeOutbox Row (orchestration.observation_corroboration_modified OR orchestration.evidence_link_modified)
    ↓
Outbox Worker (run_outbox_worker) Relays Event to stream:weather:orchestration
    ↓
Orchestration Dispatcher (run_dispatcher) Consumes Event
    ↓
Triggers on_observation_ingested() OR on_evidence_ingested()
    ├── Spatial/Temporal Candidate Query for Affected Incidents
    ├── Creates/Updates IncidentObservationCorroboration OR IncidentEvidenceLink
    └── Executes Single-Stage CREDIBILITY Recalculation (IncidentPipeline.execute_single_stage)
    ↓
Database Update on Affected Incidents (Updated credibility_score)
    + Stages RealtimeOutbox Row (report.intelligence_ready)
    ↓
Outbox Worker Relays to stream:weather:realtime
    ↓
FastAPI SSE (/api/v1/events/stream)
    ↓
Frontend RealtimeService Singleton (Deduplicated SSE Message)
    ↓
Targeted TanStack React Query Invalidation (incidentKeys.detail(id))
    ↓
UI Reactive Live Update (Sensor Readings, Evidence Links, Credibility Breakdown without Page Reload)
```

---

## 6. Realtime Delivery & Consistency Guarantees

- **Delivery Semantics**: **At-least-once stream delivery**. Duplicate delivery is possible under network partitions or worker crash recovery.
- **Client-Side Deduplication**: The frontend `RealtimeService` maintains a bounded FIFO ring buffer of 1,000 recent `event_id` UUIDs to suppress duplicate UI reactions.
- **No Exactly-Once Claim**: Relevant processing paths are designed and tested to tolerate duplicate delivery. The system does not guarantee exactly-once processing.
- **Outbox Retention**: Staged outbox records in `realtime_outbox` are pruned after **72 hours** (`OUTBOX_WORKER_RETENTION_HOURS=72`). Dead-letter rows are retained indefinitely.
