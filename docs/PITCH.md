# PITCH.md — 3-Minute Presentation Script & Hard Questions Sheet

## Part 1: 3-Minute Presentation Pitch Script

### [0:00 – 0:40] The Problem: The Last-Mile Blindspot in Disaster Management
"Good morning, evaluators. During the 2023 North India floods and the Chennai cyclones, disaster authorities faced a recurring bottleneck: the **last-mile ground truth blindspot**.

The India Meteorological Department (IMD) provides world-class synoptic radar and satellite forecasts at regional grid resolutions. But District Emergency Operation Centers (DEOCs) and NDRF field commanders cannot see hyper-local street realities: which underpass is submerged by four feet of water, which railway track has subsided, and where stranded families need rescue boats.

Citizen reports on social media could fill this gap, but emergency commanders cannot rely on unverified social feeds where up to 70% of posts are unverified, outdated, or recycled misinformation from past disasters."

---

### [0:40 – 1:20] The Solution: The National Weather Big Data Analytics Platform
"Our solution—**Problem Statement ID: SIH26069**—is the **National Weather Big Data Analytics Platform**.

We combine crowdsourced citizen reports with meteorological sensor telemetry, government emergency alerts (NDMA SACHET, CWC), and open media into an **explainable, AI-augmented intelligence engine**.

Instead of a black box, our engine calculates a transparent **Machine Credibility Score (0.0000 to 0.9800)** backed by:
1. **Spatial-Temporal Clustering**: Groups reports within 2.5 km and 120 minutes so crowd volume does not artificially inflate confidence.
2. **Physical Sensor Corroboration**: Cross-verifies citizen reports against meteorological observations.
3. **Image Forensics**: Detects recycled photos using perceptual hashing (pHash/dHash) and verifies EXIF capture consistency.
4. **Digital Evidence Linking**: Cross-corroborates events against independent news feeds."

---

### [1:20 – 2:20] Live Technical Proof & Resiliency
"This is not a slide deck—it is a running, production-hardened platform:

- **Ingestion Scale**: Our event streaming architecture ingests **14,913 events per second** directly through Redis Streams pipelines (`logs/C_4.log:109`).
- **Load Capacity**: In automated load testing with Locust across 100 concurrent users, the platform sustained **576 requests per second** with **0.00% error rate** and sub-15ms cache-hit response times (`logs/C_4.log:90, 97`).
- **Disaster-Grade Resiliency**: We conducted a live chaos drill where the primary ingestion worker was abruptly killed mid-load. The container recovered in **2.47 seconds** with **zero lost events and zero duplicate records** verified in PostgreSQL (`logs/C_4.log:137, 161-164`).
- **Operator Workflow**: Priority triage queues enable DEOC operators to review AI-flagged evidence side-by-side and transition verified incidents to field dispatch in seconds."

---

### [2:20 – 3:00] Operational Integrity & Impact
"Crucially, our system enforces strict ethical and operational boundaries:
- **Machine assessment is never ground truth**: Only authorized human commanders can verify or deploy resources.
- **Privacy by design**: Citizen EXIF metadata is processed ephemerally and never persisted.
- **Fairness**: Missing metadata or photos stripped of EXIF by messaging apps remain completely neutral (Product Rule P1) and never penalize honest citizens.

With the National Weather Platform, India’s disaster management authorities gain instant, verified situational awareness to save lives when every minute counts. Thank you."

---

## Part 2: 10-Question Hard-Questions Sheet (With Honest Answers Citing Logs)

### Q1: What is the real-world statistical accuracy of your AI models?
**Honest Answer**:
The empirical statistical accuracy (precision, recall, and false-positive rates) on authentic, uncurated disaster field events has **not been clinically measured**.
Our multilingual hazard classifier achieves $\ge 85\%$ accuracy on our 60-post regression suite (`logs/C_2.log`), and image forensics successfully detects 100% of synthetic photo-reuse fixtures. However, because real disaster telemetry is inherently noisy, our platform treats AI outputs strictly as an advisory score ($0.0000$ to $0.9800$), requiring human operator authorization for all life-safety actions.

---

### Q2: Do you have real, live access to IMD Automatic Weather Station (AWS) networks?
**Honest Answer**:
**No; IMD AWS access is currently mock-only.**
Live telemetry ingestion from IMD automatic weather stations requires official Ministry of Earth Sciences (MoES) enterprise credentials and gateway IP whitelisting that are not publicly provisioned. In our current architecture, physical corroboration integrates Open-Meteo gridded model telemetry and deterministic simulation fixtures (`logs/C_3.log:52-65`). The service is designed with a pluggable provider interface ready for live IMD station integration once official credentials are provided.

---

### Q3: How does your system scale under high-concurrency national disasters?
**Honest Answer**:
On an isolated single-node Apple M4 benchmark host (16 GB RAM), the demo stack demonstrated:
- **14,913.72 events/sec** direct stream ingestion throughput (`logs/C_4.log:109`).
- **576.33 HTTP requests/sec** across 100 concurrent users with **0.00% error rate** (`logs/C_4.log:90`).
- **1,514 MiB (~1.51 GB)** idle memory footprint across 11 running containers (`logs/C_3.log:82-93`).
In a multi-state deployment, the stateless FastAPI API workers and Redis Streams consumers scale horizontally across container clusters, while PostgreSQL utilizes PostGIS spatial indexes and read replicas.

---

### Q4: How does the platform defend against coordinated disinformation or Sybil attacks?
**Honest Answer**:
The platform employs three defense mechanisms:
1. **Deduplication Boundary**: All reports within $2.5\text{ km}$ and $120\text{ min}$ are clustered into a single incident. Multiple reports from the same cluster provide a diminishing sub-signal (capped at $+0.10$), preventing coordinated bots from inflating credibility through raw volume.
2. **Perceptual Hash Forensics**: Recycled photos from past emergencies are automatically detected using pHash DCT-II and dHash comparisons, triggering a negative contradiction penalty (`logs/C_3.log:67-78`).
3. **Physical Baseline Corroboration**: Claims of extreme rainfall or cyclone damage are corroborated against atmospheric observations; reports contradicted by physical data receive zero corroboration lift.

---

### Q5: How do you handle citizen privacy and location surveillance concerns?
**Honest Answer**:
In accordance with Product Rule P4:
- Citizen photographs are stored in isolated MinIO/S3 buckets; binary media is **never** stored in PostgreSQL.
- Embedded EXIF metadata (GPS coordinates and camera timestamps) is extracted ephemerally in worker memory for consistency verification and immediately discarded.
- Only the high-level forensic verdict (`SUPPORTS`, `NEUTRAL`, `CONTRADICTS`) and non-reversible perceptual hashes are stored in the database.
- Furthermore, photos stripped of EXIF metadata (e.g. uploaded via WhatsApp) are treated as completely neutral ($\pm 0.00$ adjustment) under Product Rule P1 to avoid penalizing privacy-conscious citizens.

---

### Q6: If IMD already has radar, satellite, and AWS infrastructure, why is this platform needed?
**Honest Answer**:
IMD operates high-altitude radar and regional grid models ($\approx 10\text{ km}$ resolution). They can forecast that a cloudburst will hit Mumbai, but they cannot observe:
- Which specific underpass or subway is inundated by 4 feet of water.
- Which bridge has suffered structural damage.
- Where citizens are cut off without relief supplies.
This platform bridges high-altitude synoptic meteorology with hyper-local, crowdsourced ground reality.

---

### Q7: Can your image forensics detect AI-generated deepfakes or altered photographs?
**Honest Answer**:
**No.**
Our image forensics subsystem is specifically engineered for **perceptual hash reuse detection** (identifying genuine photographs recycled from past disasters) and **EXIF spatial-temporal consistency**. We intentionally do not deploy unverified deepfake classification models, which introduce uncalibrated false-positive rates and high GPU latency. We prioritize transparent, explainable checks over black-box neural detectors.

---

### Q8: What happens during severe disasters when telecom networks and internet access fail?
**Honest Answer**:
The platform provides two offline operating modes:
1. **Local DEOC Deployment**: The entire platform runs in an isolated local container stack (`docker-compose.demo.yml`) without external cloud dependencies, allowing local operation over emergency intranet or satellite links.
2. **Offline Fixture Fallback**: If external APIs (Open-Meteo, IMD) become unreachable, the system automatically falls back to local simulation fixtures (`logs/C_3.log:1-25`), clearly labeled with `is_simulated = true`.

---

### Q9: How do emergency dispatchers see real-time updates without polling?
**Honest Answer**:
The platform implements a PostgreSQL **transactional outbox pattern**. When an incident is created or verified in PostgreSQL, an outbox record is inserted in the same database transaction. A dedicated relay worker streams these records to Redis Streams, which FastAPI broadcasts over persistent Server-Sent Events (`GET /api/v1/events/stream`). The frontend React Query cache listens to the SSE stream and selectively refetches updated incidents in sub-second time without page reloads.

---

### Q10: Why is the location-mismatch penalty signal disabled by default?
**Honest Answer**:
The feature flag `LOCATION_MISMATCH_ENABLED` defaults to `false` in code (`back-end/app/core/config.py:200`) and deployment configuration (`logs/C_3.log:6`).
In India, citizen descriptions frequently reference distant hometowns, colloquial neighborhood landmarks, or transliterated district names (e.g., "near Old Airport Road" in Bengaluru). Penalizing reports based on naive text-to-GPS distance creates unfair false penalties against genuine emergency reports until localized state gazetteers are comprehensively validated.
