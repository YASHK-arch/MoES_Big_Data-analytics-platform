# Authoritative Project Status & Master Synchronization

**Platform**: National Weather Big Data Analytics Platform (Smart India Hackathon 2026 — Problem Statement ID: `SIH26069`)
**Domain**: Big Data Analytics / Disaster Management / Geospatial Intelligence
**Document Status**: **ACTIVE SOURCE OF TRUTH (ENGINEERING FREEZE AT COMMIT `cca2661`)**
**Last Synchronized**: 2026-09-01

---

## 1. Project Baseline & Repository State

| Attribute | Current Value / State |
| :--- | :--- |
| **Git Branch** | `main` |
| **Current HEAD Commit** | `cca26615d1743078932527ec1e89507ac417fa03` (`cca2661`) |
| **Commit Subject** | `docs: complete Phase 17 GDELT & Mastodon live provider integration audit` |
| **Working Tree State** | **Clean** (`0` uncommitted changes, synchronized with `origin/main`) |
| **Backend Test Baseline** | **345 passed, 1 skipped** (`pytest` across 24 test files) |
| **Frontend Test Baseline** | **160 passed** (`vitest run` across 11 test suites) |
| **Backend Static Gates** | `mypy` (0 issues across 144 source files), `ruff check` (0 errors), `ruff format` (144 files clean) |
| **Frontend Static Gates** | `npm run typecheck` (0 errors), `npm run lint` (0 warnings/errors), `npm run build` (built clean in ~1.8s) |

---

## 2. Core Subsystem Truth Matrix

| Subsystem / Area | Implementation Status | Verification Classification | Evidence & Implementation Location |
| :--- | :--- | :---: | :--- |
| **Citizen Intake** | Mobile-friendly reporting form, photo upload to MinIO, PostGIS spatial point generation, instant tracking ID. | **MANUALLY & RUNTIME VERIFIED** | [CitizenReportForm.tsx](file:///Users/akshatjain/Documents/SIH/front-end/src/features/reports/CitizenReportForm.tsx), `POST /api/v1/reports`, report `RPT-20260831-B848D18A`. |
| **Public Tracking** | Public tracking lookup for status, timeline, and administrative resolution. | **RUNTIME VERIFIED** | [ReportTrackingPage.tsx](file:///Users/akshatjain/Documents/SIH/front-end/src/pages/ReportTrackingPage.tsx), `GET /api/v1/reports/{id}`. |
| **External Ingestion Framework** | Multi-source adapter framework (IMD, NDMA, CWC, Mastodon, GDELT, DemoSeed). | **BUILT & TESTED** | [back-end/app/ingestion/](file:///Users/akshatjain/Documents/SIH/back-end/app/ingestion/), `registry.py`, `test_external_ingestion_integration.py`. |
| **NDMA SACHET Feed** | Official national disaster alert CAP/JSON feed adapter. | **LIVE PROVIDER VERIFIED** | Real HTTP POST to `https://sachet.ndma.gov.in/cap_public_website/FetchAllAlertDetails` (HTTP 200, 66 alerts parsed, normalized, streamed to `stream:weather:events`, persisted to PostgreSQL). |
| **CWC NWDP River Feed** | Official river water level telemetry adapter. | **LIVE PROVIDER VERIFIED** | Real HTTP GET to `https://nwdp.nwic.gov.in/api/3/action/datastore_search` (HTTP 200, resource `d80798b9-4b11-4626-8b63-964202ba7216`, telemetry parsed, normalized, streamed to `stream:weather:observations`, persisted to PostgreSQL). |
| **GDELT News Feed** | News feed ingestion adapter for disaster headlines. | **LIVE PROVIDER VERIFIED** | Live HTTP query verified (`http://api.gdeltproject.org/api/v2/doc/doc`), rate limited ($\ge 5.0\text{s}$ interval), normalized, persisted to `evidence_items`, and verified in corroboration pipeline. |
| **Mastodon Social Feed** | Social feed ingestion adapter for emergency weather hashtags. | **LIVE PROVIDER VERIFIED** | Live HTTP query verified (`https://mastodon.social/api/v1/timelines/tag/*`), rate limited ($\ge 1.0\text{s}$ interval), normalized, persisted to `evidence_items` (specific live post linkage not separately isolated). |
| **IMD Nowcast Feed** | Official weather nowcast and AWS station adapter. | **BUILT & TESTED (MOCK)** | Ingests IMD AWS/CAP format; live production access requires official credentials/IP whitelisting (HTTP 401 handled gracefully via `AdapterFetchError`). |
| **Demo Seed Feed** | Synthetic weather incident generator. | **DEVELOPMENT UTILITY** | Development/testing utility for local evaluation; not part of scheduled production adapter set. |
| **Ingestion Scheduler** | Polling scheduler with typed event routing across Redis streams. | **RUNTIME VERIFIED** | [run_scheduler.py](file:///Users/akshatjain/Documents/SIH/back-end/app/workers/run_scheduler.py), `IngestionScheduler`. |
| **Ingestion Consumer Worker** | Consumes `stream:weather:events`, persists reports (`QUEUED`), stages outbox triggers. | **RUNTIME VERIFIED** | [run_ingestion_worker.py](file:///Users/akshatjain/Documents/SIH/back-end/app/workers/run_ingestion_worker.py), `IngestionWorker`. |
| **Observation Worker** | Consumes `stream:weather:observations`, persists to `weather_observations`. | **RUNTIME VERIFIED** | [run_observation_worker.py](file:///Users/akshatjain/Documents/SIH/back-end/app/workers/run_observation_worker.py), `ObservationWorker`. |
| **Evidence Worker** | Consumes `stream:weather:evidence`, persists to `evidence_items`. | **RUNTIME VERIFIED** | [run_evidence_worker.py](file:///Users/akshatjain/Documents/SIH/back-end/app/workers/run_evidence_worker.py), `EvidenceWorker`. |
| **Intelligence Pipeline** | 5-stage deterministic pipeline (`LOCATION`, `DUPLICATE`, `EVIDENCE`, `OBSERVATION`, `CREDIBILITY`). | **RUNTIME VERIFIED** | [pipeline.py](file:///Users/akshatjain/Documents/SIH/back-end/app/intelligence/pipeline.py), `IncidentPipeline`, `test_live_intelligence_integration.py`. |
| **Duplicate Detection Engine** | Spatial ($R \le 2500\text{m}$) + Temporal ($\Delta T \le 3\text{h}$) + Domain-Boosted TF-IDF Vectorizer (`sparse_tfidf_ngram_v1`). | **RUNTIME VERIFIED** | [duplicate_scorer.py](file:///Users/akshatjain/Documents/SIH/back-end/app/intelligence/duplicate_scorer.py), [semantic_similarity.py](file:///Users/akshatjain/Documents/SIH/back-end/app/intelligence/semantic_similarity.py). Zero FastEmbed/ONNX dependencies in live duplicate path. |
| **Orchestration Dispatcher** | Consumes `stream:weather:orchestration`, runs pipeline or single stages, transitions reports to `COMPLETED`. | **RUNTIME VERIFIED** | [run_dispatcher.py](file:///Users/akshatjain/Documents/SIH/back-end/app/workers/run_dispatcher.py), `OrchestrationDispatcher`. |
| **Transactional Outbox** | PostgreSQL `realtime_outbox` with `SKIP LOCKED` batch claiming and 72h historical pruning. | **RUNTIME VERIFIED** | [run_outbox_worker.py](file:///Users/akshatjain/Documents/SIH/back-end/app/workers/run_outbox_worker.py), `RealtimeOutboxWorker`. |
| **Redis Streams Buffer** | 6 dedicated streams (`realtime`, `events`, `observations`, `evidence`, `orchestration`, `dead_letter`). | **RUNTIME VERIFIED** | Local Redis 7 container, microsecond buffering. |
| **Realtime SSE Transport** | Persistent Server-Sent Events endpoint with cursor replay and comment heartbeats. | **RUNTIME VERIFIED** | `GET /api/v1/events/stream`, [events.py](file:///Users/akshatjain/Documents/SIH/back-end/app/api/v1/events.py). |
| **Frontend Realtime Manager** | Singleton `RealtimeService` with bounded deduplication (1,000 items) and React Query invalidation. | **MANUALLY & RUNTIME VERIFIED** | [realtimeService.ts](file:///Users/akshatjain/Documents/SIH/front-end/src/services/realtimeService.ts), live dashboard update without refresh. |
| **Late Reactive Corroboration** | Late evidence/observation ingestion re-triggers credibility scoring and pushes SSE updates to UI. | **MANUALLY & RUNTIME VERIFIED** | Evidence/Observation $\rightarrow$ Outbox $\rightarrow$ Redis $\rightarrow$ Dispatcher $\rightarrow$ Recalculation $\rightarrow$ SSE $\rightarrow$ UI without refresh. |
| **Executive Dashboard & Map** | Live Leaflet map with bounded GeoJSON (`GET /api/v1/geo/incidents`, 500-bound), macro KPI cards. | **MANUALLY & RUNTIME VERIFIED** | [DashboardPage.tsx](file:///Users/akshatjain/Documents/SIH/front-end/src/pages/DashboardPage.tsx), [LiveMapPage.tsx](file:///Users/akshatjain/Documents/SIH/front-end/src/pages/LiveMapPage.tsx). |
| **Verification & Triage Queue** | Priority triage queue with side-by-side evidence inspection and immutable audit logging. | **MANUALLY & RUNTIME VERIFIED** | [AdminVerificationQueuePage.tsx](file:///Users/akshatjain/Documents/SIH/front-end/src/pages/AdminVerificationQueuePage.tsx), `POST /api/v1/verification/*`. |
| **Analytics Platform** | Server-aggregated activity trends and two-tier regional demographics. | **RUNTIME VERIFIED** | [AnalyticsPage.tsx](file:///Users/akshatjain/Documents/SIH/front-end/src/pages/AnalyticsPage.tsx), `GET /api/v1/analytics/*`. |
| **Operator Auth & Route Guard (Part 5)** | JWT access token creation/validation (`pyjwt`) and bcrypt password hashing (`users` table). `POST /api/v1/auth/login` endpoint; `get_current_operator` FastAPI dependency locking `/api/v1/verification/*`; `ProtectedRoute.tsx` frontend route guard. | **IMPLEMENTED & RUNTIME VERIFIED** | [security.py](file:///Users/akshatjain/Documents/SIH/back-end/app/core/security.py), [deps.py](file:///Users/akshatjain/Documents/SIH/back-end/app/api/deps.py), [auth.py](file:///Users/akshatjain/Documents/SIH/back-end/app/api/v1/auth.py), [AuthContext.tsx](file:///Users/akshatjain/Documents/SIH/front-end/src/context/AuthContext.tsx), [ProtectedRoute.tsx](file:///Users/akshatjain/Documents/SIH/front-end/src/components/auth/ProtectedRoute.tsx). |
| **Location Onboarding Gate (Feature 1)** | Geolocation detection with Nominatim reverse-geocode fallback, session storage persistence, and manual city search prompt. | **IMPLEMENTED & RUNTIME VERIFIED** | [LocationContext.tsx](file:///Users/akshatjain/Documents/SIH/front-end/src/context/LocationContext.tsx), [LocationGateModal.tsx](file:///Users/akshatjain/Documents/SIH/front-end/src/components/common/LocationGateModal.tsx). |
| **"My Area" Citizen Dashboard (Feature 2)** | Hyper-local incident proximity map, distance sorting, verified incidents query (`GET /api/v1/geo/incidents/nearby`), and public safety radius filters. | **IMPLEMENTED & RUNTIME VERIFIED** | [CitizenDashboardPage.tsx](file:///Users/akshatjain/Documents/SIH/front-end/src/pages/CitizenDashboardPage.tsx), [geo.py](file:///Users/akshatjain/Documents/SIH/back-end/app/api/v1/geo.py). |
| **Real Road Routing Corridor Check (Feature 3)** | OSRM road routing engine integration; PostGIS `ST_Buffer` (2 km corridor) and `ST_Intersects` against verified disaster incidents. Dynamic risk polyline rendering. | **IMPLEMENTED & RUNTIME VERIFIED** | [routes.py](file:///Users/akshatjain/Documents/SIH/back-end/app/api/v1/routes.py), [osrm_service.py](file:///Users/akshatjain/Documents/SIH/back-end/app/services/osrm_service.py), [RouteBlockageChecker.tsx](file:///Users/akshatjain/Documents/SIH/front-end/src/components/common/RouteBlockageChecker.tsx). |
| **National Map & Forecast Advisories (Feature 4)** | All-India + EEZ maritime boundary layer, verified nationwide incidents, official IMD/NDMA cyclone tracks & forecast bulletins (`forecast_advisories` table, `GET /api/v1/geo/forecasts`), and density heatmap toggle (B5). | **IMPLEMENTED & RUNTIME VERIFIED** | [NationalMapPage.tsx](file:///Users/akshatjain/Documents/SIH/front-end/src/pages/NationalMapPage.tsx), [forecast.py](file:///Users/akshatjain/Documents/SIH/back-end/app/models/forecast.py), [geo.py](file:///Users/akshatjain/Documents/SIH/back-end/app/api/v1/geo.py). |
| **Relief Center Locator (B1)** | Admin-curated emergency shelters & evacuation camps; PostGIS `ST_DWithin` spatial proximity API (`GET /api/v1/geo/relief-centers`); Leaflet shelter map layer (`🏕️`). | **IMPLEMENTED & RUNTIME VERIFIED** | [relief_center.py](file:///Users/akshatjain/Documents/SIH/back-end/app/models/relief_center.py), [relief_centers.py](file:///Users/akshatjain/Documents/SIH/back-end/app/api/v1/relief_centers.py). |
| **Vernacular Language Support (B2)** | `react-i18next` Hindi & English bilingual localization across citizen-facing interfaces, navbars, and incident descriptors. | **IMPLEMENTED & RUNTIME VERIFIED** | [i18n/index.ts](file:///Users/akshatjain/Documents/SIH/front-end/src/i18n/index.ts), [Navbar.tsx](file:///Users/akshatjain/Documents/SIH/front-end/src/components/layout/Navbar.tsx). |
| **Real-Time Proximity Alerts (B3)** | Real-time SSE listener comparing incoming weather alerts against user GPS position; 25 km threshold animated emergency banner toast. | **IMPLEMENTED & RUNTIME VERIFIED** | [useProximityAlerts.ts](file:///Users/akshatjain/Documents/SIH/front-end/src/hooks/useProximityAlerts.ts), [CitizenDashboardPage.tsx](file:///Users/akshatjain/Documents/SIH/front-end/src/pages/CitizenDashboardPage.tsx). |
| **Community Crowd Validation (B4)** | Citizen "still accurate?" confirm/dispute crowd feedback loop (`incident_feedback` model & API `POST /api/v1/incidents/{id}/feedback`). | **IMPLEMENTED & RUNTIME VERIFIED** | [feedback.py](file:///Users/akshatjain/Documents/SIH/back-end/app/models/feedback.py), [FeedbackWidget.tsx](file:///Users/akshatjain/Documents/SIH/front-end/src/components/incident/FeedbackWidget.tsx). |
| **One-Tap Emergency Contacts (B7)** | Quick-dial telephone directory card for NDRF (1078), SDRF (1070), DEOC (1077), and CWC (1800-11-2020). | **IMPLEMENTED & RUNTIME VERIFIED** | [EmergencyContactsCard.tsx](file:///Users/akshatjain/Documents/SIH/front-end/src/components/common/EmergencyContactsCard.tsx). |

---

## 3. Real Intelligence Verification Proof

- **Live Manual Report**: `RPT-20260831-B848D18A` (`ID: fbb34eb2-ce5c-4e86-8b39-8666b26273a4`)
  - Title: `INTELLIGENCE TEST 001`
  - Processing Status: `COMPLETED`
  - Credibility Score: `0.537`
  - Readiness: `INTELLIGENCE_READY`
  - Proven Chain: Citizen submit -> PostgreSQL outbox -> Outbox Worker -> Orchestration Stream -> Dispatcher -> 5-Stage Pipeline -> Persisted Result -> Frontend UI.

---

## 4. Operational Boundaries & Known Limitations

1. **At-Least-Once Delivery**: Redis streams operate under at-least-once delivery semantics. Relevant processing paths are designed and tested to tolerate duplicate delivery. The frontend suppresses duplicate UI reactions using its bounded 1,000-entry ring buffer.
2. **External Live Providers**:
   - **NDMA SACHET**: Live verified against `https://sachet.ndma.gov.in/cap_public_website/FetchAllAlertDetails` (66 alerts parsed, normalized, streamed, and persisted).
   - **CWC NWDP**: Live verified against `https://nwdp.nwic.gov.in/api/3/action/datastore_search` (5 live telemetry records parsed in the controlled Phase 18 proof; normalized, streamed, and persisted; adapter default fetch limit: 50).
   - **GDELT DOC 2.0**: Live verified against `http://api.gdeltproject.org/api/v2/doc/doc`. Queries retrieve article metadata and excerpts in `ArtList` mode; full body scraping is out-of-band. Rate limited to $\ge 5.0\text{s}$ interval.
   - **Mastodon Social**: Live verified against public hashtag timelines (`https://mastodon.social/api/v1/timelines/tag/{hashtag}`). Posts do not include native GPS coordinates; spatial matching operates via text keyword heuristics without coordinate fabrication. Rate limited to $\ge 1.0\text{s}$ interval.
   - **IMD Nowcast**: Adapter implemented and tested. Live production access is blocked by the official gateway credential / IP whitelisting requirement.
   - **DemoSeed**: Development/testing utility, not a scheduled production source.
3. **Duplicate Detection Model**: The live duplicate path uses `CandidateGenerator` (PostGIS spatial radius $R \le 2500\text{m}$, temporal window $\Delta T \le 3\text{h}$) and `SemanticVectorizer` (`sparse_tfidf_ngram_v1`), combining domain synonym normalization and term boosting. FastEmbed is not used in the production duplicate path.
4. **Map Query 500-Feature Bound**: GeoJSON map queries enforce a 500-feature bound (`LIMIT 500`) to protect browser memory and rendering performance. Macro totals remain authoritatively computed via server summary endpoints.
5. **Worker Supervision**: The 6 worker processes run as standalone Python CLI modules. Production supervisor configuration (`systemd`, Kubernetes) remains an infrastructure deployment responsibility.
6. **Dead-Letter Handling**: The `stream:weather:dead_letter` stream stores unroutable messages. Dead letter inspection and replay are performed programmatically/manually, with no continuous monitor daemon unless running.
