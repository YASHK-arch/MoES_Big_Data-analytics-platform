# S2-lite: Image Forensics & EXIF Consistency Architecture

> **Feature Status**: 🟡 Implemented & Verified in isolated environment (`weather_platform_s2`, test DB 15).
> **Feature Flag**: `IMAGE_FORENSICS_ENABLED` (default: `False`). Demo fixtures opt-in via `IMAGE_FORENSICS_DEMO_FIXTURE_ENABLED` (default: `False`).

---

## 1. Overview & Objective

The **Image Forensics & EXIF Consistency (S2-lite)** subsystem provides deterministic, explainable verification of crowdsourced citizen imagery submitted during meteorological emergencies.

In disaster reporting, malicious hoaxes or viral social media posts frequently misrepresent past storms or distant catastrophes as current local emergencies (e.g., re-uploading Chennai 2015 flood imagery during a 2026 Mumbai rainfall event). S2-lite combats this misinformation by:
1. **Perceptual Hashing (pHash & dHash)**: Detecting image reuse across distinct incidents separated in space or time.
2. **Safe EXIF Consistency Analysis**: Comparing embedded camera capture timestamps and GPS coordinates against declared incident declarations.
3. **Weak, Capped Credibility Adjustments**: Feeding explainable mathematical signals into the credibility engine while leaving authoritative verification decisions strictly to human disaster authorities.

---

## 2. Product Rules (P1–P7)

| Rule | Principle | Implementation Guarantee |
|:---|:---|:---|
| **P1** | **Missing EXIF is Neutral** | Modern messaging platforms (WhatsApp, Telegram, Signal) and web uploaders routinely strip EXIF metadata for privacy. Stripped or missing EXIF metadata produces `verdict = "NEUTRAL"` with an explicit reason and **0.0 credibility penalty**. It is never penalized. |
| **P2** | **Signals Weak, Status Invariant** | Image signals are weakly weighted and strictly capped at $\pm 0.05$ (configurable via `IMAGE_FORENSICS_CAP`). Image forensics **never** alters an incident's authoritative `verification_status` (`PENDING`, `UNDER_REVIEW`, `VERIFIED`, `REJECTED`, `DUPLICATE`). |
| **P3** | **Reuse Across Separate Incidents Only** | An image uploaded by multiple citizens reporting the *same* local incident within the spatio-temporal clustering window ($R \le 2.5\text{ km}$, $\Delta T \le 120\text{ min}$) is treated as a duplicate report cluster, **not** flagged as malicious image reuse. Reuse is only flagged across separate incidents far in time ($> 48\text{h}$) or distance ($> 50\text{km}$). |
| **P4** | **No Black-Box AI Detectors** | No black-box deep learning or unexplainable generative AI detectors are used in this round. All checks rely on deterministic signal processing and transparent rules. |
| **P5** | **Privacy Preservation** | Raw camera GPS coordinates and device hardware identifiers are **never** returned in public or operator REST APIs. Endpoints only expose derived, privacy-preserving values (`COORDINATES_PRESENT`, distance offset, time difference, and linked incident IDs). |
| **P6** | **Worker Safety & Resilience** | Images are processed asynchronously in worker pipelines with strict decompression-bomb protection (`MAX_IMAGE_PIXELS = 40,000,000`) and a 15 MB file size limit before decode. Corrupt, truncated, or oversized files fail safe to `NEUTRAL` with a recorded `error_reason` without crashing worker processes. |
| **P7** | **Feature Flagging & Simulated Labeling** | Gated under `IMAGE_FORENSICS_ENABLED` (default `False`). All demo and fixture test data are explicitly labeled with `is_simulated = True` across database rows, outbox events, and frontend badges. |

---

## 3. Mathematical & Algorithmic Foundation

### 3.1 Perceptual Hashing (pHash)
- **Algorithm**: Deterministic 2D Discrete Cosine Transform (DCT-II).
- **Process**:
  1. Convert image to 8-bit grayscale.
  2. Resize to $32 \times 32$ pixels using bilinear interpolation.
  3. Compute $32 \times 32$ 2D DCT using precomputed cosine basis matrix:
     $$D_{k, n} = \sqrt{\frac{2}{N}} \cos\left( \frac{\pi (2n+1)k}{2N} \right)$$
  4. Extract top-left $8 \times 8$ low-frequency coefficients (excluding DC component at $(0,0)$).
  5. Compute median of the 64 AC coefficients.
  6. Generate 64-bit binary hash where bit $i = 1$ if coefficient $\ge \text{median}$, else $0$.
  7. Format as 16-character hexadecimal string.

### 3.2 Difference Hashing (dHash)
- **Algorithm**: Horizontal gradient difference.
- **Process**:
  1. Grayscale conversion.
  2. Resize to $9 \times 8$ pixels ($9$ columns, $8$ rows).
  3. Compare adjacent pixels per row: bit $i = 1$ if $P[x, y] > P[x+1, y]$, else $0$.
  4. Yields 64-bit binary hash formatted as 16-character hexadecimal string.

### 3.3 Hamming Distance
The bitwise distance between two 64-bit hashes $H_1$ and $H_2$:
$$\text{dist}(H_1, H_2) = \text{popcount}(H_1 \oplus H_2)$$

### 3.4 Threshold Measurement (Item 3 Calibration)
Measured across 50 seed images, 400 transformed pairs (JPEG compression at quality 30/50, scaling, Gaussian noise, aspect changes, watermarking), and 1,225 unrelated image pairs:
- **pHash Threshold 10**: **77.00% detection rate** on synthetic transformations with **0.0000% false matches** on unrelated images.
- **dHash Threshold 8**: **72.75% detection rate** on synthetic transformations with **0.0000% false matches**.
- **Recommended Threshold**: pHash $\le 10$ or dHash $\le 8$.

---

## 4. Timezone & EXIF Normalization

Cameras in India frequently store naive local wall-clock timestamps in EXIF Tag `0x0132` (`DateTime`) without timezone offsets:
1. **Explicit Offset (Tag `0x9011` / `OffsetTimeOriginal`)**: Parsed directly to compute exact UTC timestamp (`timezone_assumed_ist = False`).
2. **Naive Timestamp**: Documented assumption: cameras operating in India without offset tags record Indian Standard Time (IST, UTC+05:30). Subtracted 5 hours 30 minutes to derive UTC (`timezone_assumed_ist = True`).
3. **Consistency Evaluation**:
   - $\Delta T \le 3.0\text{ hours} \implies \text{SUPPORTS}$ (Consistent)
   - $\Delta T > 24.0\text{ hours} \implies \text{CONTRADICTS}$ (Exceeds acceptable capture window)
   - $3.0 < \Delta T \le 24.0\text{ hours} \implies \text{NEUTRAL}$

---

## 5. Database Schema (Migration `0020_image_forensics`)

### `image_hashes` Table
Stores cryptographic and perceptual hashes for cross-incident indexing:
- `id` (UUID, Primary Key)
- `media_id` (UUID, Foreign Key to `report_media.id`, CASCADE, Unique)
- `sha256` (VARCHAR(64), Indexed)
- `phash` (VARCHAR(16), Indexed)
- `dhash` (VARCHAR(16), Indexed)
- `has_exif` (BOOLEAN)
- `exif_timestamp_utc` (TIMESTAMPTZ, Indexed)
- `exif_latitude` / `exif_longitude` (DOUBLE PRECISION, Bounded)
- `exif_geom` (GEOMETRY(Point, 4326), GiST Indexed)
- `camera_make` / `camera_model` (VARCHAR(100), Internal only)
- `is_simulated` (BOOLEAN, default False)

### `incident_image_findings` Table
Stores operational forensic findings per incident:
- `id` (UUID, Primary Key)
- `incident_id` (UUID, Foreign Key to `weather_reports.id`, CASCADE, Indexed)
- `media_id` (UUID, Foreign Key to `report_media.id`, CASCADE)
- `time_verdict` / `location_verdict` / `reuse_verdict` (VARCHAR(20))
- `overall_verdict` (VARCHAR(20))
- `credibility_adjustment` (FLOAT, Capped at $\pm 0.05$)
- `matched_incident_ids` (JSONB, Array of incident UUID strings)
- `checks` (JSONB, Structured check breakdown)
- `is_simulated` (BOOLEAN, default False)

---

## 6. Known Limitations & Scope Boundaries

1. **EXIF Metadata is Easily Forged or Stripped**:
   - Advanced adversaries can forge or edit EXIF timestamps and GPS tags using standard tools (`exiftool`).
   - Major consumer messaging apps (WhatsApp, Telegram) strip EXIF metadata entirely upon upload. Therefore, missing EXIF is treated as neutral (P1), and positive EXIF matches provide weak supporting evidence only.
2. **No Generative AI / Deepfake Detector**:
   - S2-lite intentionally excludes commercial or experimental AI-generated image detectors (P4). Deepfake detectors exhibit high false-positive rates on compressed or noisy disaster imagery and act as opaque black boxes.
3. **Synthetic Thresholds Only**:
   - The pHash threshold of 10 was empirically calibrated on synthetic transformations (compression, scaling, noise). Real-world disaster imagery with heavy cropping, extreme angle changes, or screen-recorded video captures may fall outside this threshold.
4. **Privacy Model**:
   - Citizens uploading photos from residential areas may unintentionally expose home coordinates via camera GPS. To protect privacy, raw GPS coordinates are never exposed in public or operator API responses (P5).
5. **Scale & Indexing Limits**:
   - Linear Hamming distance scanning across perceptual hashes is performed via PostgreSQL indexing. For production deployments exceeding $1,000,000$ images, perceptual hash indexing should be augmented with multi-index hashing (MIH) or vector indices (e.g. FAISS / Milvus).
