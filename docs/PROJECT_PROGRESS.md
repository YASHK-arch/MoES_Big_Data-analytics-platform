# SIH 2026 – PS 26069 Weather Platform: Progress & Workflow

> **Living document.** Every agent/contributor prompt must end by updating this file (see [Update protocol](#12-update-protocol-for-agents)).
> Suggested location in repo: `docs/PROJECT_PROGRESS.md` (link it from `README.md` and `AGENTS.md`).

- **Problem statement:** SIH 2026 PS 26069 (weather event intelligence platform)
- **Team status:** Selected from IIT Madras internal round; now competing on this PS with other colleges
- **Goals of the current phase:** (1) architecture that stays fast after deployment, (2) intact and recoverable pipelines, (3) full PS requirement coverage, (4) standout features
- **Last updated:** 2026-10-01 (A-items 6-8: demo stack enable, SSE event wiring, report_service rollback fix)
- **Deployment status:** Local isolated Docker compose demo stack (`sih-demo`) tested & operational at `:8080`. Total memory: ~1.07 GB idle across 11 containers. Production guardrails & smoke tests verified.
- **Legend:** ✅ done · 🟡 in progress · ⬜ todo · ❌ failed / blocked · 🔎 needs verification

---

## 1. Architecture snapshot (as reviewed)

| Layer | Tech |
|---|---|
| API | FastAPI (async), SQLAlchemy async, Alembic |
| DB | PostgreSQL + PostGIS |
| Streaming / queue | Redis Streams (custom async Redis client in `app/core/redis.py`) |
| Object storage | MinIO / S3 |
| Workers | outbox, dispatcher, ingestion, observation, evidence, scheduler |
| Intelligence | rule-based category/credibility, TF-IDF duplicate clustering, gazetteer entity extraction, CWC water-level corroboration |
| Frontend | React + Vite + TypeScript, Leaflet, Recharts, Vitest |
| Realtime | SSE backed by Redis Streams + transactional outbox |

**Design strengths to keep and showcase:** outbox pattern, explainable credibility scoring, physical (sensor) corroboration, idempotent ingestion (verified, B6), `EventPublisher` abstraction.

---

## 2. PS 26069 requirement coverage

| Requirement | Status | Notes / next action |
|---|---|---|
| Collect from social media, public datasets, APIs, citizen reports | 🔎 | 8 adapters + 1 demo. Historical datasets exist; live API not verified; no key configured (K1-6, audit/logs/K1_6.log). No current data.gov.in adapter. No X/Bluesky/Telegram/YouTube. |
| Posts with `#IMD` and weather hashtags | ✅ | `imd` added to Mastodon hashtag defaults (F6). |
| Metadata: time, city, state, GPS, photos, videos, category | ✅ | Photos/video accepted (A8). Magic-byte validation works. |
| Categories incl. fog, dust storm, strong wind | 🔎 | R4: 60-post regression suite (fog/dust/wind EN+HI) 100% (60/60). 30-post hold-out (agent-authored, not blind) scored 21/30 (70.0% accuracy; FOG 8/10, DUST_STORM 7/10, STRONG_WIND 6/10; 9 misses in audit/logs/K1_2.log). Category rules frozen. RSS 120 items classified: 104 NONE, 16 weather. |
| ML/AI for fake reports, untrusted sources, duplicates | 🔎 | Duplicates strong. Hoax vs genuine credibility (audit/logs/K1_3.log): 10 genuine posts mean 0.6500 (min/max 0.6500); 10 hoaxes mean 0.4821 (min 0.4215, max 0.5427). 5 old-video hoaxes < 0.45 (0.4215); 5 foreign-location hoaxes > 0.45 (0.5427) because location contradiction is not yet a credibility signal. No image forensics yet. |
| Big-data tech, real-time large-scale ingestion | ⬜ | Need measured load numbers and a Kafka/Redpanda + ClickHouse/Timescale story. |
| Dashboard: date/event/location filters, verification tracking, real-time charts | ✅ | Exists. DEMO badge + hide-demo toggle added (R5). |
| Admin panel | ✅ | R3: operator-only CSV/GeoJSON export (50k max, streamed), bulk verify/reject (100 ids, 1 txn), audit-log table + viewer page, frontend buttons. 401/limit/audit-row tests pass. |

---

## 3. Baseline audit results (before fixes)

Run on isolated DB `weather_platform_audit`, Redis DB 5, 100k seeded rows.

| ID | Result | Finding |
|---|---|---|
| A1 | ❌ | 407 passed on Redis DB 0 (188.8 s). **Deadlock on non-zero Redis DB** (lock re-entrancy in `connect()`). Ruff: 27 errors. |
| A2 | ✅ | Typecheck 0 errors; Vitest 174 passed; single JS chunk 1,274.98 kB (341 kB gzip). |
| A3 | ❌ | Category mismatch backend (8) vs frontend (10). |
| A4 | ❌ | `imd` missing from Mastodon hashtag defaults. |
| A5 | ✅ | Verification endpoints return 401 without auth. *(An earlier review wrongly said they were unauthenticated.)* |
| A6 | ❌ | 0/100 requests throttled on `POST /api/v1/reports`. |
| A7 | ❌ | Insecure default `SECRET_KEY`, `DEBUG=True`, public `/docs`. |
| A8 | ✅ | Disguised EXE rejected, >15 MB rejected, PNG/MP4 accepted. |
| A9 | ❌ | No app Dockerfiles, no `/metrics`, no worker health checks. |
| A10 | ❌ | No `React.lazy`, no `GZipMiddleware`, no Redis TLS, no `XAUTOCLAIM`, no DB pool. |
| B1 | 🟡 | 53.1 RPS, p50 917 ms, p95 1364 ms, **46 DB connections** for 50 users (NullPool). |
| B2 | ✅ | 100k reports + 20k related rows seeded in 6.96 s (COPY). |
| B3 | 🟡 | Dashboard summary 70 ms **with Seq Scan**; bbox/index queries 1.7–6.4 ms. |
| B4 | 🟡 | 42.2 RPS, p50 1177 ms, p95 1673 ms, 0% errors. |
| B5 | 🟡 | 50 SSE clients → **+50 Redis connections** (1 per client); 100% event delivery. |
| B6 | ✅ | Idempotency perfect: 0 duplicates after replaying 50 identical reports. |
| B7 | ❌ | 0/200 events processed after worker SIGKILL/restart; all stayed QUEUED. 🔎 Not fully explained (see open questions). |

---

## 4. Workflow overview

```
Phase 0  Audit baseline                ✅ done
Phase 1  Batch 1: correctness/safety   ✅ implemented (verify items pending)
Phase 2  Batch 2: performance          🟡 implemented, gaps open (P3, B7)
Phase 3  Re-audit (before/after)       🟡 round 1 done, follow-ups pending
Phase 4  Batch 3: ops & deployability  ⬜
Phase 5  Requirement gaps (PS)         ⬜
Phase 6  Standout features             ⬜
Phase 7  Scale proof (load report)     ⬜
Phase 8  Polish & demo readiness       ⬜
```

Rule: **one batch → tests green → re-audit affected checks → update this file → next batch.** One git commit per item so any change can be reverted independently.

---

## 5. Phase 1 – Batch 1: correctness & safety ✅

Result: **419 backend tests passed, 1 skipped, 0 failed; 174 frontend tests passed; `tsc` 0 errors; ruff clean on changed files.**

| ID | Change | Status |
|---|---|---|
| F1 | Fix `AsyncRedisClient` lock deadlock: internal unlocked `_send_command`, `connect()` uses it for `SELECT`; test with DB 5 | 🔎 |
| F2 | Stream recovery: `XAUTOCLAIM` of idle pending messages (`STREAM_CLAIM_IDLE_MS`), max delivery attempts, dead-letter after N | 🟡 |
| F3 | Per-IP rate limit on `POST /api/v1/reports` (new `core/rate_limiter.py`, 429 + Retry-After) | ✅ |
| F4 | Production guards: refuse default `SECRET_KEY`/`DEBUG`/wildcard CORS in production; docs disabled in production; `DEBUG` default → False | 🟡 |
| F5 | Added `FOG`, `DUST_STORM`, `STRONG_WIND`; aligned backend/frontend categories; migration `20260930_0009` | ✅ |
| F6 | `imd` hashtag defaults (+ `.env.example`, test) | ✅ |

**Canonical category decisions**
- `HEATWAVE` canonical (alias `EXTREME_HEAT`)
- `CYCLONE_STORM` canonical (alias `CYCLONE_GALE`)
- `DROUGHT` and `URBAN_FLOOD` kept as separate categories

**Items still to verify (carried into Batch 2 as V0):**
- 🔎 Rate limiter takes client IP from `request.client.host`; trusts `X-Forwarded-For` only when `TRUSTED_PROXY_COUNT > 0`
- 🔎 Rate limiter **fails open** (with warning log) if Redis is down
- 🔎 Migration `0009` upgrade → downgrade → upgrade works on a DB with data
- 🔎 B7 recovery actually reaches 200/200 in the re-audit

---

## 6. Phase 2 – Batch 2: performance 🟡 (implemented; verification gaps below)

| ID | Change | Target | Status |
|---|---|---|---|
| V0 | Verify the four items above | — | ✅ |
| P1 | Real DB pool (`DB_POOL_SIZE=10`, `MAX_OVERFLOW=20`, `TIMEOUT=30`, `RECYCLE=1800`); `DB_DISABLE_POOL` for tests | connections ≈ pool size | ✅ |
| P2 | `GZipMiddleware`, `ORJSONResponse`, ETag/Cache-Control on geo endpoint | smaller payloads, 304s | 🟡 |
| P3 | Redis cache (TTL 10 s, single-flight) for dashboard/analytics + index removing Seq Scan on summary | dashboard summary ≪ 70 ms | ✅ |
| P4 | SSE fan-out: one shared subscriber + per-client bounded queues, replay via `XRANGE` | Redis connections constant | ✅ |
| P6 | Frontend: debounce SSE-triggered query invalidation (2 s trailing) | no refetch storms | 🔎 |

**Targets after Batch 2 (re-audit B1/B3/B4/B5/B7):**

| Metric | Before | Target |
|---|---|---|
| Dashboard p50 @50 users | 917 ms | < 200 ms |
| Incident list p50 @50 users | 1177 ms | < 250 ms |
| Postgres connections @50 users | 46 | ≤ pool size + overflow |
| Redis connections @50 SSE clients | +50 | ~constant |
| B7 recovery | 0/200 | 200/200 |

### Re-audit round 1 results (2026-09-30)

Honest scorecard (agent's own PASS labels re-checked against the raw numbers):

| Test | Before | After | Verdict |
|---|---|---|---|
| A3 categories | BE 8 vs FE 10 | 13 unified in BE and FE | ✅ resolved |
| A4 hashtags/adapters | no `imd` | `imd`, `imdweather`, `imdindia`; 8 adapters | ✅ resolved |
| A6 report rate limit | 0/100 throttled | 90/100 throttled (10 allowed) | ✅ resolved |
| A7 prod hygiene | insecure defaults | `DEBUG=False` default confirmed; **`/docs` disabling in production not demonstrated** (server ran without `ENVIRONMENT=production`) | 🟡 partial |
| A10 stack | 5 gaps | GZip, `XAUTOCLAIM` code, DB pool present; **React.lazy and Redis TLS still absent** | 🟡 partial |
| B1 dashboard load | 53 RPS, p50 917 ms, 46 DB conns | 423 RPS, p50 72 ms, 2 DB conns | 🟡 real gain, but **largely Redis cache hits**; true (cache-miss) speed unmeasured |
| B3 summary query | 70 ms, Seq Scan | **206 ms, still Seq Scan** (slower) | ❌ P3 index goal not met |
| B3 page 500 | 6.4 ms | **112.8 ms** (about 18x slower) | ❌ regression, cause unknown |
| B4 reports/geo load | 42 RPS, p50 1177 ms, p95 1673 ms | 128 RPS, p50 286 ms, p95 1048 ms | 🟡 better, target (< 250 ms p50) not met |
| B5 SSE | +50 Redis conns | +0 (shared subscriber), 10/10 events | ✅ resolved |
| B7 crash recovery | 0/200 | pending 6 → 6 → **7** after 60 s; oldest pending ID unchanged and still owned by `orchestrator-worker-1`; stream lag 1665 → 1605 (about 1 event/s consumed) | ❌ **not proven** (agent's test was edited to treat "PEL retained" as pass; 200/200 completion never reported) |

Also noted: the re-audit API ran with `REDIS_URL=.../0` (dev Redis DB 0), not the isolated DB 5, so stream lag may include non-audit events and F1 was not exercised for real.

---

## 7. Phase 3 – Re-audit (cheap, targeted) 🟡 (round 1 done 2026-09-30)

Re-run only: **A3, A4, A6, A7, A10, B1, B3, B4, B5, B7** (same DB, same methods). For B7 also record `XINFO GROUPS` and `XPENDING` before kill, after kill, and 60 s after restart. Record results in [Section 13](#13-audit-history).

---

## 8. Phase 4 – Batch 3: ops & deployability ⬜

> Priority note: O1 (Dockerfiles + one-command compose) is the first item here because a public demo URL is the goal. O6 (Redis TLS), O8 (multi-worker, PgBouncer) and production-mode checks (issue #14) are deferred until a deploy target is chosen.

| ID | Task | Status |
|---|---|---|
| O1 | Dockerfiles for API, workers, frontend; single `docker compose up` starts everything | ✅ |
| O2 | Health/readiness endpoints for API and every worker | ✅ |
| O3 | Prometheus metrics: stream lag (`XPENDING`), outbox age, queue depth, request latency | ✅ |
| O4 | Structured JSON logging with request/correlation IDs | ⬜ |
| O5 | Frontend route-level code splitting (`React.lazy`), target main chunk < 400 kB | ✅ |
| O6 | Redis TLS (`rediss://`) support or migrate to `redis.asyncio` + `hiredis` | ⬜ |
| O7 | Partition/retention plan for `weather_reports`, `evidence_items`, observations; keyset pagination for deep pages | ⬜ |
| O8 | Multi-worker uvicorn/gunicorn config; PgBouncer note for production | ⬜ |
| O9 | Fix any remaining lint debt (baseline had 27 ruff errors) | 🔎 |
| O10 | CI pipeline (tests, typecheck, lint, build) with badge | ⬜ |

---

## 9. Phase 5 – Remaining PS requirement gaps ⬜

| ID | Task | Status |
|---|---|---|
| R1 | `data.gov.in` adapter (config key exists, no adapter) | 🔎 |
| R2 | More social/news sources: Bluesky, Telegram public channels, RSS news | 🔎 |
| R3 | Admin panel: export (CSV/GeoJSON), bulk verify/reject, source management, audit-log viewer | ✅ |
| R4 | End-to-end classification test for fog / dust storm / strong wind posts (English + Hinglish) | 🔎 |
| R5 | Clearly label demo/simulated data vs live data in UI and README | ✅ |

---

## 10. Phase 6 – Standout features ⬜ (ordered by impact)

| ID | Feature | Why it wins | Status |
|---|---|---|---|
| S1 | **Physical corroboration** beyond CWC: IMD AWS/ARG rainfall, temperature, wind | Uses MoES's own data; strongest differentiator | 🔎 |
| S2 | **Image forensics**: EXIF time/GPS vs claim, perceptual-hash reuse detection, AI-generated image score | Directly addresses "fake reports" | ⬜ |
| S3 | **NDMA alert overlay**: reports inside/outside active alert polygons; flag "impact reported, no alert issued" | Actionable insight for authorities | ⬜ |
| S4 | **Indian languages**: Hindi/regional post classification (Bhashini / IndicBERT) + Hindi UI | India-specific, jury-visible | ⬜ |
| S5 | **Low-connectivity intake**: offline-queueing PWA, WhatsApp/Telegram bot | Answers "why hasn't this been solved" | ⬜ |
| S6 | **Burst detection**: per-district report-rate anomaly alerts | Early-warning signal | ⬜ |
| S7 | **Authority outputs**: CSV/GeoJSON/Parquet export, public API, CAP alerts from verified incidents, auto district situation report | Completes the loop to decision makers | ⬜ |
| S8 | **Big-data proof**: Kafka/Redpanda adapter behind `EventPublisher`, ClickHouse/Timescale profile in compose | Matches PS "big data" wording | ⬜ |

---

## 11. Phase 7–8 – Scale proof and demo readiness ⬜

- **Load report (k6 or Locust):** ingest events/sec, dashboard p50/p95/p99, SSE clients supported, worker recovery time. Publish numbers in README.
- **Demo checklist:** seeded realistic dataset, scripted live-report demo, verification workflow demo, failure-recovery demo (kill worker, show recovery), architecture diagram, one-page requirement-mapping table, 3-minute pitch script.
- **Repo hygiene:** remove hard-coded local paths from `AGENTS.md`; make README status claims match tests and CI output.

---

## 12. Update protocol for agents

**Every prompt given to a coding agent must end with the following block** (copy verbatim):

```text
PROGRESS FILE (mandatory, last step)
Update docs/PROJECT_PROGRESS.md before finishing:
1. Change the status icon of every item you worked on (✅ done, 🟡 in progress, ❌ failed, 🔎 needs verification). Do not mark ✅ unless its tests pass.
2. Add one row to the "Change log" table (date, item IDs, commit hash(es), one-line summary, test counts).
3. If you ran audit/measurement tests, add the numbers to "Audit history" (before/after) and update the metric targets table if relevant.
4. Add any new bug, risk or open question to "Open issues".
5. Update "Last updated" at the top and keep the file's structure unchanged. Do not delete history.
Keep your edits to this file under 40 lines. In your final reply, only state "PROGRESS.md updated" plus what you could not complete.
```

**Rules for the file**
- Never rewrite history; add rows, change status icons.
- IDs (F1, P3, S2…) are permanent; refer to them in commits and prompts.
- If a task is split or abandoned, keep its row and note why.

---

## 13. Audit history

| Date | Scope | Key numbers | Notes |
|---|---|---|---|
| 2026-09-30 | Baseline (Part A + B, 100k rows) | B1 p50 917 ms / 46 DB conns; B4 p50 1177 ms; B5 +50 Redis conns; B7 0/200 | See Section 3 |
| 2026-09-30 | Re-audit round 1 (A3, A4, A6, A7, A10, B1, B3, B4, B5, B7) | B1 423 RPS / p50 72 ms / 2 DB conns (cache-assisted); B3 summary 206 ms Seq Scan; B3 page 500 112.8 ms; B4 128 RPS / p50 286 ms; B5 +0 Redis conns; B7 pending 6→7, not recovered | See Section 6 scorecard |
| 2026-09-30 | Re-audit round 2 (DB 5, S0–S5) | B1 uncached: 99.4 RPS, p50 11.3 ms, 11 conns; B1 cached: 446.6 RPS, p50 64.7 ms, 2 conns; B3 summary: 22.1–35.5 ms Index-Only Scan (no Seq Scan); B3 p500: 2.8–3.7 ms; B4 uncached: 85.1 RPS, p50 562 ms; B4 cached: 83.6 RPS, p50 555 ms; B7: 200/200 COMPLETED in 30s | S0 DB 5 validated; B7 recovered; V0/S5 verified |
| 2026-09-30 | Re-audit round 3 (C1–C4, 100k rows) | C1 200/200 100% cred match; C2 TTL=0 bypass 196.6 RPS/p50 178ms vs TTL=10 388.9 RPS/p50 77.9ms; C3 4w 219.5 RPS/p50 146.6ms (limit=50 only, not what the frontend sends) | C1–C4 completed; C2 precision table evaluated on synthetic test fixture rows |
| 2026-09-30 | Re-audit round 4 (D1–D5) | D1: 0 only-in-OLD, 3261 only-in-NEW, 1186 identical; C1 credibility equivalence invalid (in-memory); D3: default 500 (~26KB gzip); D4: Redis c50 p50 0.21ms | Full equivalence verified; Redis pooling active; zero duplicate indexes |
| 2026-09-30 | Re-audit round 5 (E1–E5, 100k rows) | E1: 0/10 neg controls, 80% plausibility; E3: honest B4 (/geo 500 gzip + /reports) 1w 79.2 RPS/p50 488ms vs 4w 77.5 RPS/p50 541ms; E4: c50 RTT p50 0.17–0.38ms, auto-reconnect 0.03s; E5: 18 idxs (52MB), 20k COPY 6978 rps | E1–E5 verified; geo payload reduced -6.5% raw (-16.5KB); local commits cleanly split |
| 2026-09-30 | Re-audit round 6 (G1–G5, 100k rows) | G1 test isolation (weather_platform_test); G2 geo p50 104.2ms cached (4w)/156.1ms (1w), uncached 487.5ms; G3 bench 100% prec/rec (synthetic); G5 migration 0013 dropped 2 dup idxs, 20k COPY +26.7% (1237ms) | G1–G5 complete; G3 metrics evaluated on 10,000 synthetic test fixture rows in audit DB |
| 2026-09-30 | Round 8 Deployability (O1–O5, V1–V6) | Web :8080 SPA; API :8000; 11 containers healthy; memory 1097 MiB (< 3.5GB); smoke 10/10 cats + rate limit 429 + SSE pass; prod 404 docs; redis 20s stop 503->200 without api restart; down/up persist 623 rpts; main chunk 24.66 kB | Fully deployed, isolated demo compose stack verified |
| 2026-09-30 | Round 8b Verification | 452/452 pytest pass; ruff 0; mypy 0; alembic 0015; P0(c) p1 0.19ms / p500 8.01ms; H1 6 backfilled; H2 delta 0.0435 / max 0.1742; H3 prec 5.9%/10.3%/13.3%; scheduler 256m, api 512m; conn budget 23 | All Round 8b checks verified |
| 2026-09-30 | K0 Round 9 verification (R1–R5, L4) | Initial R1-R5 checks; RSS 3 feeds 200 / 2 feeds 404; dev/test/audit Alembic 0017; pytest 476/0 | Commits b4a74c9, 7ce9624, ee8e17d, 4c1ad25, 7babb02, fd9632e |
| 2026-10-01 | K1 Round 9 close (R1–R5, static gates) | Pytest 479/479 passed (random seed 20261001 & normal); mypy 9 errors in 2 files (0 in feedback.py); ruff check/format clean; alembic check exit 0 (mig 0018); R4 holdout 21/30 (70.0%); Hoax mean 0.4821 (5 old-video <0.45, 5 foreign-location 0.5427) vs genuine 0.6500; RSS 120 items snapshot (audit/rss_snapshot_k1.json), summary capped at 280 chars, IMD/NDTV 404 commented; R3 parity verified (single & bulk staging unified); audit DB 10,000 synthetic test fixtures reconciled | Commits 4a52c11, 806c35c, ee0d466, 56c8712, 6c03511, f606088, e63b3ac, 0d398f8, f32b4f0, ba4d349 |

---

## 14. Change log

| Date | Item IDs | Commit | Summary | Tests |
|---|---|---|---|---|
| 2026-09-30 | F1–F6 | _baseline_ | Redis deadlock fix, stream recovery (XAUTOCLAIM + DLQ), report rate limit, production guards, new categories + alignment, `imd` hashtag | BE 419 pass / 1 skip; FE 174 pass; tsc 0 errors; ruff clean |
| 2026-09-30 | V0, P1–P4, P6 | _batch2_ | DB pool, gzip, dashboard cache, shared SSE subscriber, frontend debounce | BE 435 pass; FE 177 pass; tsc 0 errors |
| 2026-09-30 | S1, S2, P3, O9 | `d9f717d`, `a1b95e8`, `383ee6b` | Fix XREADGROUP BLOCK 0 & XAUTOCLAIM cursor (B7), add migration 0011 summary covering index (B3), optimize evidence linking 1-to-N | BE 436 pass / 0 fail; FE 177 pass; tsc 0 errors; ruff clean |
| 2026-09-30 | D1–D5, B4, C1–C4 | `6efda69`, `b0e72af` | Evidence linking equivalence restored (0 only-in-OLD), Redis connection pooling (c50 p50 0.21ms), geo limit, regression tests | BE 441 pass; FE 177 pass; tsc 0 errors; ruff clean |
| 2026-09-30 | E1–E5 | `276f106`, `9e33220`, `9052ca5`, `a553fd3` | Round 5: precision tightening, honest B4 load test, unused geo property drop, Redis pool audit & reconnect, 18-index analysis | BE 442 pass; FE 177 pass; tsc 0 errors; ruff clean |
| 2026-09-30 | G1–G5 | `current` | Round 6: test DB isolation, geo Redis byte caching (compresslevel=4), evidence linking analysis, migration 0013 dropping duplicate indexes | BE 442 pass; FE 177 pass; tsc 0 errors; ruff clean |
| 2026-09-30 | O1–O3, O5, V | `d605aa6..b31931a` | Round 8 deployability: Docker multi-stage images, health/ready, metrics Prometheus, React.lazy/chunks, smoke & failure acceptance | BE 442 pass; FE 177 pass; tsc clean; ruff clean |
| 2026-09-30 | R3, R1–R5, L4 | _working tree_ | Bulk verify/reject emits outbox/SSE event; test DB resets once per session with seeded reference rows; region precedence fixed | R3 SSE regression passes; BE 476/0 ×3; Ruff/mypy clean; format 62 files; Alembic check drift |
| 2026-10-01 | S1 (1–16) | `s1-physical-corroboration` | S1 Physical Corroboration: pure evaluator, Open-Meteo provider, mig 0019, worker integration, credibility engine, UI card (EN/HI), Prometheus metrics & drills, replay evaluation | BE 523 pass / 0 fail (full & seed 42); FE 182 pass, tsc/lint/build clean; mypy/ruff clean |
| 2026-10-01 | A (6–8) | `4f74716` | Demo stack: PHYSICAL_CORROBORATION_ENABLED=true in compose, DEMO_FIXTURE opt-in (default false); SSE RealtimeEventType.INCIDENT_PHYSICAL_CORROBORATION_COMPLETED added; report_service rollback fix | 7 passed (corroboration_api + pipeline); enum import OK; logs/A_6.log |

---

## 15. Open issues / risks

| # | Issue | Severity | Owner | Status |
|---|---|---|---|---|
| 1 | **B7 resolved**: worker kill & stream recovery cleanly claims in-flight messages; 200/200 reached COMPLETED in DB within 30s | High | — | ✅ |
| 2 | Rate limiter IP source and proxy trust (`X-Forwarded-For` spoofing): verified with `TRUSTED_PROXY_COUNT=1`, async Redis rate limiter, 11th request 429 | High | — | ✅ |
| 3 | Rate limiter behaviour when Redis is down: verified fail-open with warning log | Medium | — | ✅ |
| 4 | Migration `0009` downgrade path: verified downgrade to `0008` and upgrade to `0011` on populated DB | Medium | — | ✅ |
| 5 | Dashboard summary Seq Scan: resolved via covering index migration `0011` (Index-Only Scan, 22.1 ms) | High | — | ✅ (P3) |
| 6 | Hand-written Redis client: connection pooling (pool_size=8) implemented, concurrency 50 RTT p50 down from 5.39ms to 0.21ms | Medium | — | ✅ (D4) |
| 7 | Entity extractor uses one regex per gazetteer key; gazetteer only ~460 entries | Medium | — | ⬜ |
| 8 | Live-map cap of 500 markers hides data at scale (need server-side grid/H3 aggregation) | Medium | — | ⬜ |
| 9 | Fake-report detection has no image forensics or trained model | Medium | — | ⬜ (S2) |
| 10 | B3 incident list page 500: Index Scan 2.8–3.7 ms on warm cache (earlier 112 ms was cold/noisy outlier) | High | — | ✅ |
| 11 | Dashboard summary Seq Scan: removed via migration `0011` covering index (`idx_weather_reports_summary_cov`) | High | — | ✅ (P3) |
| 12 | B1/B4 numbers cache-off baseline: measured (B1 99.35 RPS / 11.3 ms; B4 85.10 RPS / 562 ms) | Medium | — | ✅ |
| 13 | Earlier B4 result was limit=50 only, not what the frontend sends. Honest B4 (/geo default 500 gzip + /reports active) measured: 79.2 RPS, p50 488 ms (1w) / 77.5 RPS, p50 541 ms (4w) | Medium | — | ✅ (E3) |
| 14 | A7: verify `/docs` and startup guards with `ENVIRONMENT=production`: verified exit on weak key, 404 on docs | Medium | — | ✅ (V3) |
| 15 | Re-audit ran on Redis DB 0: verified fresh on Redis DB 5 | Medium | — | ✅ |
| 16 | Audit test scripts freeze: B7 frozen and verified 200/200 pass | Medium | — | ✅ |
| 17 | Test DB isolation: pytest redirected to dedicated `weather_platform_test` database and Redis DB 15 | High | — | ✅ (G1) |
| 18 | H1: All event_category rows ensured via migration 0014; NULL category_id backfilled from reported_category; DUST_STORM/STRONG_WIND now appear in dashboard | High | — | ✅ (H1) |
| 19 | H2: 200-incident credibility analysis — mean delta 0.0435; 68.5% increased, 13.5% decreased; RELATED links inflate scores by mean 0.0637 | Medium | — | ✅ (H2/analysis-only) |
| 20 | H3: Evidence precision checker repaired (None-safe city/state lookup); evaluated at thresholds 0.45/0.50/0.55 | Medium | — | ✅ (H3) |
| 21 | H4: Migration 0015 partial geo-sort index `(occurred_at DESC NULLS LAST, created_at DESC) WHERE geom IS NOT NULL` — Seq Scan 30ms → Index Scan 3ms; 50-user load 100% Redis-served, Postgres CPU 0% | High | — | ✅ (H4) |
| 22 | H4: max_connections=100; pg_stat_activity under 50-user geo load: active=1 (sampler only), Postgres never queried | Medium | — | ✅ (H4) |
| 23 | H5: Geo gzip size variation (G2: 19-20KB, R5/now: 37KB): explained by row count difference — 2047 geo-tagged reports in 24h window now vs fewer at earlier measurement | Low | — | ✅ (H5) |
| 24 | H5: Mypy errors a1b95e8→HEAD: **31 → 31** (no regression); all 31 are pre-existing in feedback.py (Column[T] assignment type narrowing) | Low | — | ✅ (H5) |
| 25 | Weak-link cap (0.03 max boost) & L1 location gate implemented; 0 crossings, F1 1.0 on benchmark v2 | High | — | ✅ (Round 9a) |
| 26 | Remote Git backup: pushed all commits up to Round 8 and audit suite to `origin/main` | High | — | ✅ |
| 27 | Accidental `FLUSHALL` risk on shared Redis instances (mitigated by isolated demo container stack) | High | — | ✅ |
| 28 | L4 test marker: is_test_fixture column added (mig 0016); 10k fixture items tagged in audit DB | Low | — | ✅ (Round 9a) |
| 29 | R1 data.gov.in: historical datasets exist; live API not verified; no key configured (K1-6 log audit/logs/K1_6.log) | Medium | — | 🔎 |
| 30 | R2 live RSS: Snapshot audit/rss_snapshot_k1.json (120 items); IMD & NDTV URLs returned 404 (disabled in config with comment); summary capped at 280 chars in DB storage; 30-item labeling sample written to audit/rss_label_sample.csv | Medium | — | 🔎 |
| 31 | R4 holdout & credibility: 30-post holdout (agent-authored, not blind) scored 21/30 (70.0% accuracy; 9 misses listed in audit/logs/K1_2.log); hoax mean 0.4821 vs genuine 0.6500 (5 foreign-location >0.45; audit/logs/K1_3.log); category_rules.py diff empty | High | — | 🔎 |
| 32 | `alembic check`: migration 0018 added for archive metadata & ORM index alignment; PostGIS filter added to env.py; alembic check exit 0; audit DB upgrade head -> downgrade -1 -> upgrade head verified (audit/logs/K1_7.log) | Medium | — | ✅ |
| 33 | Test DB is truncated once per session and seeded; observation test uses unique location; full suite 476/0 three consecutive runs | Medium | — | ✅ |

---

## 16. Reference: environment & commands

- Audit DB: `weather_platform_audit`; audit Redis DB: `5`; audit bucket: `weather-media-audit` (set through env vars only, never edit `.env`)
- Backend tests: `PYTHONPATH=back-end back-end/.venv/bin/pytest back-end/tests -q` (about 3 minutes)
- Lint/type: `ruff check .`, `mypy app tests`; frontend: `npm run typecheck`, `npx vitest run`, `npm run build`
- Audit scripts and logs live in `audit/` (outside `back-end/` and `front-end/src/`)