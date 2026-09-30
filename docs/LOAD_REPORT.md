# LOAD_REPORT.md — Measured Load and Resilience Report

## 1. Test Environment & Machine Specifications
All metrics in this report were measured during this session on the isolated Docker compose demo stack (`sih-demo`).
Raw command outputs are logged in `logs/C_4.log`.

- **Host Machine**: Apple MacBook Air
- **Operating System**: macOS Darwin 25.5.0 (Kernel Version 25.5.0, `arm64`)
- **Processor**: Apple M4 (10 cores)
- **Physical Memory**: 16.0 GB (17,179,869,184 bytes)
- **Load Generation Tool**: Locust 2.46.6 (headless mode)
- **Target URL**: `http://localhost:8080` (reverse-proxied via Nginx web container to 2 Uvicorn API workers)
- **Database / Cache**: PostgreSQL 16 + PostGIS, Redis 7 (internal Docker network `demo_net`)
- **Evidence Log**: `logs/C_4.log`

---

## 2. HTTP API Load Test Results

The load test exercised a realistic operational mix of 6 endpoints:
1. `GET [CACHE_HIT] /dashboard/summary`: fixed parameters (`time_range=24h`), served from Redis cache.
2. `GET [CACHE_HIT] /geo/incidents?limit=500`: frontend default limit (500) with fixed window (`hours_ago=24`), served from Redis cache.
3. `GET [CACHE_MISS] /dashboard/summary`: dynamic bounding boxes, triggering SQL analytical aggregation.
4. `GET [CACHE_MISS] /geo/incidents?limit=500`: dynamic bounding boxes, triggering PostGIS spatial queries.
5. `GET /incidents (list)`: paginated incident list (`page_size=20`).
6. `GET /incidents/{id} (detail)`: incident detail including machine credibility score and forensic findings.

### Summary Table across Concurrency Tiers

| Tier | Total Requests | Error Rate | Aggregate RPS | Aggregate p50 | Aggregate p95 | Aggregate p99 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **10 Users** (20s) | 5,037 | 0.00% (0 fails) | 254.31 req/s | 5 ms | 17 ms | 49 ms |
| **50 Users** (20s) | 11,318 | 0.00% (0 fails) | 570.07 req/s | 29 ms | 150 ms | 260 ms |
| **100 Users** (20s) | 11,441 | 0.00% (0 fails) | 576.33 req/s | 35 ms | 460 ms | 760 ms |

---

### Detailed Endpoint Breakdown: Cache Hit vs Cache Miss

#### 10 Concurrent Users (Ramp 5/s, Duration 20s)
*Source: `logs/C_4.log:12-41`*

| Endpoint | Requests | RPS | Error % | Min | p50 (Med) | p90 | p95 | p99 | Max |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `[CACHE_HIT] /dashboard/summary` | 1,262 | 63.72 | 0.00% | 1 ms | 3 ms | 5 ms | 8 ms | 21 ms | 127 ms |
| `[CACHE_HIT] /geo/incidents?limit=500` | 1,288 | 65.03 | 0.00% | 3 ms | 5 ms | 9 ms | 14 ms | 43 ms | 252 ms |
| `[CACHE_MISS] /dashboard/summary` | 400 | 20.20 | 0.00% | 1 ms | 7 ms | 13 ms | 21 ms | 60 ms | 411 ms |
| `[CACHE_MISS] /geo/incidents?limit=500` | 422 | 21.31 | 0.00% | 1 ms | 5 ms | 10 ms | 14 ms | 50 ms | 234 ms |
| `/incidents (list)` | 851 | 42.96 | 0.00% | 4 ms | 8 ms | 16 ms | 23 ms | 140 ms | 283 ms |
| `/incidents/{id} (detail)` | 814 | 41.10 | 0.00% | 3 ms | 7 ms | 15 ms | 23 ms | 72 ms | 280 ms |
| **Aggregated (10 Users)** | **5,037** | **254.31** | **0.00%** | **1 ms** | **5 ms** | **11 ms** | **17 ms** | **49 ms** | **411 ms** |

#### 50 Concurrent Users (Ramp 10/s, Duration 20s)
*Source: `logs/C_4.log:43-72`*

| Endpoint | Requests | RPS | Error % | Min | p50 (Med) | p90 | p95 | p99 | Max |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `[CACHE_HIT] /dashboard/summary` | 2,811 | 141.59 | 0.00% | 1 ms | 12 ms | 25 ms | 40 ms | 96 ms | 141 ms |
| `[CACHE_HIT] /geo/incidents?limit=500` | 2,796 | 140.83 | 0.00% | 3 ms | 24 ms | 47 ms | 78 ms | 120 ms | 177 ms |
| `[CACHE_MISS] /dashboard/summary` | 919 | 46.29 | 0.00% | 1 ms | 49 ms | 140 ms | 180 ms | 310 ms | 573 ms |
| `[CACHE_MISS] /geo/incidents?limit=500` | 942 | 47.45 | 0.00% | 1 ms | 43 ms | 130 ms | 170 ms | 310 ms | 407 ms |
| `/incidents (list)` | 1,842 | 92.78 | 0.00% | 5 ms | 61 ms | 160 ms | 200 ms | 330 ms | 443 ms |
| `/incidents/{id} (detail)` | 2,008 | 101.14 | 0.00% | 4 ms | 64 ms | 150 ms | 190 ms | 300 ms | 567 ms |
| **Aggregated (50 Users)** | **11,318** | **570.07** | **0.00%** | **1 ms** | **29 ms** | **110 ms** | **150 ms** | **260 ms** | **573 ms** |

#### 100 Concurrent Users (Ramp 20/s, Duration 20s)
*Source: `logs/C_4.log:74-103`*

| Endpoint | Requests | RPS | Error % | Min | p50 (Med) | p90 | p95 | p99 | Max |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `[CACHE_HIT] /dashboard/summary` | 2,960 | 149.11 | 0.00% | 2 ms | 15 ms | 36 ms | 50 ms | 100 ms | 180 ms |
| `[CACHE_HIT] /geo/incidents?limit=500` | 2,903 | 146.24 | 0.00% | 4 ms | 27 ms | 61 ms | 95 ms | 240 ms | 436 ms |
| `[CACHE_MISS] /dashboard/summary` | 965 | 48.61 | 0.00% | 4 ms | 100 ms | 440 ms | 580 ms | 820 ms | 1,030 ms |
| `[CACHE_MISS] /geo/incidents?limit=500` | 924 | 46.55 | 0.00% | 3 ms | 95 ms | 430 ms | 540 ms | 870 ms | 1,427 ms |
| `/incidents (list)` | 1,827 | 92.03 | 0.00% | 8 ms | 220 ms | 470 ms | 580 ms | 860 ms | 1,372 ms |
| `/incidents/{id} (detail)` | 1,862 | 93.80 | 0.00% | 6 ms | 220 ms | 480 ms | 600 ms | 880 ms | 1,201 ms |
| **Aggregated (100 Users)** | **11,441** | **576.33** | **0.00%** | **2 ms** | **35 ms** | **370 ms** | **460 ms** | **760 ms** | **1,427 ms** |

---

## 3. Direct Stream Ingestion Throughput
*Source: `logs/C_4.log:105-110`*

Because user-facing HTTP report intake is subject to security rate-limiting (10 reports/minute per IP), backend ingestion pipelines ingest high-volume telemetry and automated sensor feeds directly via Redis Streams.

- **Target Stream**: `stream:weather:events`
- **Published Events**: 1,000 valid `NormalizedIngestionEvent` records
- **Total Ingestion Time**: 0.0671 seconds
- **Measured Ingestion Throughput**: **14,913.72 events/sec**

---

## 4. Mid-Load Worker Failure and Recovery Drill
*Source: `logs/C_4.log:111-147` and `logs/C_4.log:150-165`*

A resiliency drill was executed where a dedicated batch of 200 events was published to `stream:weather:events`, and the primary ingestion worker container was abruptly killed mid-processing.

- **Batch Tag**: `DRILL-KILL-1790808407`
- **Total Published Events**: 200
- **Worker Target**: `sih-demo-worker-ingestion-1`
- **Worker Kill Timestamp**: `1790808408.95`
- **Worker Running Recovery Timestamp**: `1790808411.42`
- **Measured Recovery Time**: **2.47 seconds**
- **Persistence Verification in PostgreSQL (`weather_demo`)**:
  - Expected Events: 200
  - Persisted Rows in DB: **200**
  - Unique Events in DB: **200**
  - Lost Events: **0 (NONE)**
  - Duplicate Rows: **0 (NONE)**

**Conclusion**: Worker failure mid-load resulted in zero event loss and zero duplicate records due to consumer group message acknowledgement semantics and idempotent deduplication on `external_id`.
