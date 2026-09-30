# Repository Audit Report: sih26069-weather-platform

## Environment
- OS: Darwin 25.5.0 arm64 (macOS)
- CPU: Apple M4 (10 cores)
- RAM: 16 GB
- Python: Python 3.14.0 (virtualenv)
- Node: v24.13.0

## Summary Table
| ID | Status | Key Metric / Finding |
|---|---|---|
| A1 | FAIL | 407 passed (188.80s) on DB 0; Deadlocks on DB 5 (re-entrant lock bug); Ruff: 27 errors |
| A2 | PASS | Typecheck 0 errors, Vitest 174 passed (3.06s), Bundle chunk 1,274.98 kB (341 kB gzip) |
| A3 | FAIL | Category mismatches (BE 8 vs FE 10): CYCLONE_GALE/STORM, HEATWAVE/EXTREME_HEAT, DROUGHT, URBAN_FLOOD |
| A4 | FAIL | MASTODON_HASHTAGS missing 'imd' default; 7 live adapters + 1 demo adapter registered |
| A5 | PASS | Unauthenticated queue access rejected (HTTP 401) across all verification endpoints |
| A6 | FAIL | 0/100 requests throttled (429) on POST /api/v1/reports; Rate limiter only guards /auth/login |
| A7 | FAIL | Insecure default SECRET_KEY in code, DEBUG=True default, public /docs OpenAPI active |
| A8 | PASS | Magic bytes reject disguised EXE (400), oversize upload >15MB rejected (400), PNG/MP4 accepted (201) |
| A9 | FAIL | 0 application Dockerfiles, no Prometheus /metrics endpoint, no worker health check endpoints |
| A10 | FAIL | Absent: React.lazy (NO), GZipMiddleware (NO), TLS/SSL Redis (NO), XAUTOCLAIM (NO), DB pooling (NO) |
| B1 | PASS | 53.10 RPS, p50: 916.62 ms, p95: 1364.31 ms, Max 46 DB connections under 50 concurrent users |
| B2 | PASS | 100,000 weather reports + 20,000 related entities seeded via COPY in 6.96s |
| B3 | PASS | Dashboard summary 70.07 ms (Seq Scan: YES); BBox/Index queries 1.74–6.37 ms (Seq Scan: NO) |
| B4 | PASS | 100k rows: 42.15 RPS, p50: 1176.88 ms, p95: 1673.26 ms, 0.00% errors under 50 concurrent users |
| B5 | PASS | 50 SSE clients: +50 Redis connections (1 per client), 100% event receipt (10/10 events per client) |
| B6 | PASS | Perfect idempotency: 0 duplicate records created after replaying 50 identical reports |
| B7 | FAIL | 0/200 events processed; 200/200 remain QUEUED after worker SIGKILL/restart (no auto-recovery) |

## Top 5 Concerns
1. **A1 (Redis Re-entrant Lock Deadlock)**: Non-zero Redis DB configuration deadlocks indefinitely on `SELECT <db>` due to re-entrant acquisition of `_lock`.
2. **A6 (Unprotected Report Ingestion)**: Zero rate limiting on `POST /api/v1/reports` allows volumetric denial of service and ingestion flooding.
3. **B1 / A10 (Connection Exhaustion via NullPool)**: Backend uses `NullPool` without connection limits, opening 46 connections under 50 users and risking DB saturation.
4. **B5 (1:1 Redis Connection Scaling for SSE)**: Every connected SSE subscriber holds a dedicated Redis TCP connection rather than sharing a pub/sub multiplexer.
5. **B7 / A10 (No Redis Stream PEL Claiming)**: Consumers lack `XAUTOCLAIM` / `XCLAIM`, stranding pending messages when workers crash or restart ungracefully.
