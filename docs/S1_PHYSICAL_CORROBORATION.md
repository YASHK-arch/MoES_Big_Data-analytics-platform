# S1: Physical Weather Corroboration Architecture & Design Document

**Status**: Active Engineering Baseline (Round 10 / S1)  
**System**: National Weather Big Data Analytics Platform (SIH26069)  
**Author**: Antigravity Autonomous Agent  
**Last Updated**: 2026-10-01  

---

## 1. Executive Summary & Purpose

Today, the incident intelligence pipeline determines credibility primarily through semantic text matching, social crowd density clustering, digital evidence linking (GDELT, RSS, Mastodon), and river telemetry (CWC). While digital evidence answers *"does external text describe a similar event?"*, physical corroboration answers:

> **"Did measured meteorological instruments or verified numerical weather models actually record atmospheric conditions consistent with the reported event at that location and time?"**

Each incident is evaluated against ground truth physical data and produces an explainable verdict:
- **`SUPPORTS`**: Observed atmospheric metrics exceed rigorous meteorological hazard thresholds.
- **`CONTRADICTS`**: Measured meteorological observations definitively disprove the reported event (subject to strict safety rules).
- **`NEUTRAL`**: No reliable observation is available within the spatiotemporal window, the provider failed, or the hazard type is non-diagnostic.

### Non-Negotiable Operational Guardrails (P1–P9)
1. **P1 (No Request-Path Calls)**: Zero external API calls on HTTP request paths. All external fetches occur in asynchronous worker jobs and are cached by `~0.25° grid + hour`.
2. **P2 (Graceful Neutral Fallback)**: Provider timeouts, HTTP errors, 429 rate limits, or empty payloads always result in `NEUTRAL` with a recorded `provider_status`. An external outage **never** degrades or rejects an incident.
3. **P3 (Flood Never Contradicts)**: `FLOOD_WATERLOGGING` and `URBAN_FLOOD` can **only** receive `SUPPORTS`. Low local rainfall never contradicts flooding, because flooding frequently stems from upstream river discharge, dam releases, or storm water drainage failure.
4. **P4 (Model vs Station Asymmetry)**: Numerical model data (Open-Meteo) receives lower weight (0.60) than physical station data (1.00). Model-based `CONTRADICTS` is disabled by default (`PHYSICAL_ALLOW_MODEL_CONTRADICTS=False`) because numerical models often miss hyper-local convective showers.
5. **P5 (Unified Physical Cap)**: Total physical credibility contribution (including existing CWC gauge corroboration) is capped (`PHYSICAL_CORROBORATION_TOTAL_CAP = 0.10`) to prevent double-counting.
6. **P6 (Status Non-Mutation)**: Physical corroboration influences credibility score only. It is strictly forbidden from changing `verification_status` (`PENDING`, `VERIFIED`, `REJECTED`). Human operational sign-off remains mandatory.
7. **P7 (Full Explainability)**: Every verdict is published with observed metric value, unit, source name, source type (`STATION` vs `MODEL`), distance (km), time gap (h), weight, and net score contribution.
8. **P8 (Feature Flag & Demo Label)**: Feature is controlled by `PHYSICAL_CORROBORATION_ENABLED` (default `False`). Demo/simulated observations are unambiguously stamped `SIMULATED`.
9. **P9 (Mock IMD Slot)**: Official IMD AWS credentials remain gated. IMD station adapter is provided as a pluggable mock slot.

---

## 2. Canonical Category to Physical Variable Mapping

The system evaluates all 13 canonical database hazard categories (`EventCategory` enum):

| # | Canonical Category Code | Primary Physical Variables | Support Rule | Contradict Rule | Status / Source |
|---|---|---|---|---|---|
| 1 | `HEAVY_RAINFALL` | `precipitation` (mm/24h, mm/1h) | 24h Rain $\ge 64.5\text{ mm}$ OR 1h Rain $\ge 15.0\text{ mm}$ | 24h Rain $\le 0.1\text{ mm}$ (STATION only) | **CITED** (IMD SOP Ch. 3) |
| 2 | `FLOOD_WATERLOGGING` | `precipitation` (mm/24h), `water_level_m` | 24h Rain $\ge 64.5\text{ mm}$ OR River level $\ge$ warning level | **NEVER CONTRADICTS** (P3) | **CITED** (IMD / CWC) |
| 3 | `URBAN_FLOOD` | `precipitation` (mm/1h, mm/3h) | 1h Rain $\ge 20.0\text{ mm}$ OR 3h Rain $\ge 40.0\text{ mm}$ | **NEVER CONTRADICTS** (P3) | **CITED** (IMD Urban Inundation) |
| 4 | `THUNDERSTORM_LIGHTNING` | `weather_code` (WMO), `precipitation` (mm/1h) | WMO Code $\in \{91, 92, 95, 96, 99\}$ OR 1h Rain $\ge 15\text{ mm}$ | **NEUTRAL** (lightning is hyper-local) | **CITED** (WMO-No. 8) |
| 5 | `CYCLONE_STORM` | `wind_speed_10m`, `wind_gusts_10m`, `surface_pressure` | Sustained $\ge 62\text{ km/h}$ (Gale) OR Gust $\ge 80\text{ km/h}$ OR Pressure $\le 990\text{ hPa}$ | Sustained $\le 15\text{ km/h}$ & Gust $\le 25\text{ km/h}$ (STATION only) | **CITED** (IMD Cyclone Criteria) |
| 6 | `STRONG_WIND` | `wind_speed_10m`, `wind_gusts_10m` | Sustained $\ge 50\text{ km/h}$ OR Gust $\ge 60\text{ km/h}$ | Gust $\le 15\text{ km/h}$ & Sustained $\le 10\text{ km/h}$ (STATION only) | **CITED** (Beaufort Force 7 / IMD) |
| 7 | `DUST_STORM` | `visibility` (m), `wind_gusts_10m` | Visibility $< 1000\text{ m}$ AND Gust $\ge 40\text{ km/h}$ | Visibility $> 6000\text{ m}$ AND Gust $\le 15\text{ km/h}$ (STATION only) | **CITED** (WMO-No. 8 / IMD) |
| 8 | `FOG` | `visibility` (m), `relative_humidity_2m` | Visibility $\le 500\text{ m}$ (Moderate/Dense Fog) | Visibility $> 3000\text{ m}$ AND Humidity $< 70\%$ (STATION only) | **CITED** (IMD Fog Glossary) |
| 9 | `HEATWAVE` | `temperature_2m` (Max Daily °C) | Max Temp $\ge 40.0^\circ\text{C}$ (Plains) OR $\ge 45.0^\circ\text{C}$ Absolute | Max Temp $< 32.0^\circ\text{C}$ (STATION only) | **CITED** (IMD Heatwave Criteria) |
| 10 | `HAILSTORM` | `weather_code` (WMO), `precipitation` (mm/1h) | WMO Code $\in \{89, 90, 96, 99\}$ (Hail / Pellets) | **NEUTRAL** (Hail footprints $< 2\text{ km}$) | **CITED** (WMO-No. 8) |
| 11 | `LANDSLIDE` | `precipitation` (mm/72h cumulative) | 72h Rain $\ge 100.0\text{ mm}$ (Trigger support) | **NEVER CONTRADICTS** (May be seismic/dry) | **ASSUMPTION - unverified** |
| 12 | `DROUGHT` | Monthly Precipitation Anomaly | Not applicable to hourly pipeline | **NEUTRAL** | **NOT APPLICABLE** |
| 13 | `OTHER` | Generic | Unspecified hazard | **NEUTRAL** | **NOT APPLICABLE** |

---

## 3. Thresholds & Meteorological Justification

### 3.1 Heavy Rainfall Thresholds
- **Heavy Rainfall**: $64.5\text{ mm}$ to $115.5\text{ mm}$ in 24 hours. (*IMD Standard Operating Procedure for Weather Forecasting and Warning Services, Glossary Section 3.2*).
- **Very Heavy Rainfall**: $115.6\text{ mm}$ to $204.4\text{ mm}$ in 24 hours. (*IMD SOP Section 3.2*).
- **Extremely Heavy Rainfall**: $\ge 204.5\text{ mm}$ in 24 hours. (*IMD SOP Section 3.2*).
- **Urban Short-Duration Cloudburst / Torrential Shower**: $\ge 20\text{ mm}$ in 1 hour. (*IMD Urban Flash Flood Guidance System*).

### 3.2 Heatwave Criteria
- **Normal Plains Heatwave**: Maximum temperature $\ge 40.0^\circ\text{C}$ with departure $\ge 4.5^\circ\text{C}$ from normal, OR absolute maximum $\ge 45.0^\circ\text{C}$. (*IMD National Weather Forecasting Centre, Criteria for Declaring Heat Wave*).
- **Severe Heatwave**: Maximum temperature $\ge 40.0^\circ\text{C}$ with departure $\ge 6.5^\circ\text{C}$ from normal, OR absolute maximum $\ge 47.0^\circ\text{C}$. (*IMD Criteria*).

### 3.3 Visibility & Fog Classification
- **Dense Fog**: Visibility between $50\text{ m}$ and $200\text{ m}$. (*IMD Aviation Weather Services / Fog Advisory Standards*).
- **Very Dense Fog**: Visibility $< 50\text{ m}$. (*IMD Standards*).
- **Moderate Fog**: Visibility between $200\text{ m}$ and $500\text{ m}$. (*IMD Standards*).

### 3.4 Wind & Gale Thresholds
- **Squall / Strong Wind**: Sudden increase of wind speed by at least $29\text{ km/h}$ with speed reaching $\ge 50\text{ km/h}$ and lasting for at least one minute. (*IMD Meteorological Terminology*).
- **Gale Force**: Sustained speed $\ge 62\text{ km/h}$ ($34\text{ knots}$, Beaufort Force 8). (*WMO Manual on Marine Meteorological Services, WMO-No. 558*).

---

## 4. Spatiotemporal Windows & Accumulation Rationale

| Hazard Group | Spatial Search Radius | Temporal Accumulation Window | Scientific Rationale |
|---|---|---|---|
| **Rainfall / Floods** | $\le 25\text{ km}$ (Station) / $\le 0.25^\circ$ (Model) | $[-24\text{h}, +2\text{h}]$ | Water accumulates and persists on surface for hours after rainfall ceases; upstream basin rain drives downstream flooding. |
| **Urban Inundation** | $\le 15\text{ km}$ (Station) / $\le 0.25^\circ$ (Model) | $[-3\text{h}, +1\text{h}]$ | Urban waterlogging is driven by high-intensity short-duration bursts overcoming drainage. |
| **Wind & Gale** | $\le 35\text{ km}$ (Station) / $\le 0.25^\circ$ (Model) | $[-3\text{h}, +3\text{h}]$ | Storm squalls and frontal boundaries propagate across $20\text{--}50\text{ km}$ in 1 to 2 hours. |
| **Fog** | $\le 20\text{ km}$ (Station) / $\le 0.25^\circ$ (Model) | $[-6\text{h}, +2\text{h}]$ | Radiation and advection fog occur during nocturnal cooling through early morning hours. |
| **Heatwave** | $\le 50\text{ km}$ (Station) / $\le 0.25^\circ$ (Model) | Same Calendar Day ($00:00\text{--}23:59\text{ IST}$) | Heatwaves are regional synoptic air-mass phenomena with low spatial variance. |

---

## 5. Weights, Scoring & Credibility Contribution

### 5.1 Source Reliability Weight
- **Station Source (`STATION`)**: $W_{\text{source}} = 1.00$ (Direct calibrated telemetry, e.g. IMD AWS, CWC NWDP river sensors).
- **Numerical Model Source (`MODEL`)**: $W_{\text{source}} = 0.60$ (Numerical reanalysis, e.g. Open-Meteo GFS/ECMWF $0.25^\circ$ grid).

### 5.2 Distance & Time Decay
For distance $d\text{ (km)}$ and time difference $\Delta t\text{ (hours)}$:
$$D_{\text{decay}} = \max\left(0.20, 1.0 - \frac{d}{d_{\max}}\right)$$
$$T_{\text{decay}} = \max\left(0.30, 1.0 - \frac{\Delta t}{\Delta t_{\max}}\right)$$
$$\text{Weight} = W_{\text{source}} \times D_{\text{decay}} \times T_{\text{decay}}$$

### 5.3 Contribution Calculation
- For `SUPPORTS`:
  $$\text{Contribution} = +\min(\text{PHYSICAL\_CORROBORATION\_TOTAL\_CAP}, \text{Weight} \times 0.10)$$
- For `CONTRADICTS` (STATION only, or MODEL if explicitly enabled):
  $$\text{Contribution} = -\min(\text{PHYSICAL\_CORROBORATION\_TOTAL\_CAP}, \text{Weight} \times 0.12)$$
- For `NEUTRAL`:
  $$\text{Contribution} = 0.0000$$

### 5.4 Bounded Integration with Existing Pipeline (P5)
The existing credibility engine synthesizes support from crowd clusters, digital news evidence, and physical observations:
$$\text{Total Physical Support} = \min\left(\text{CAP}_{\text{physical}}, S_{\text{CWC}} + S_{\text{meteorological}}\right)$$
This ensures that an incident with both CWC river alerts and Open-Meteo heavy rainfall does not double-count physical evidence.

---

## 6. Cache Architecture & Rate-Limit Budget

### 6.1 Cache Key Design
Observations are cached using spatial grid quantization and temporal hourly discretization:
$$\text{lat\_grid} = \text{round}\left(\frac{\text{lat}}{0.25}\right) \times 0.25$$
$$\text{lon\_grid} = \text{round}\left(\frac{\text{lon}}{0.25}\right) \times 0.25$$
$$\text{Cache Key} = \text{"cache:weather:physical:"} + \text{lat\_grid} + \text{":"} + \text{lon\_grid} + \text{":"} + \text{date\_hour\_str}$$

- **TTL**: 24 hours ($86,400\text{ seconds}$).
- **Single-Flight Lock**: Redis distributed mutex (`lock:weather:fetch:{grid}:{hour}`) prevents concurrent redundant fetches for the same grid-hour.

### 6.2 Rate-Limit Budget Formula
- Open-Meteo Free Tier: $10,000\text{ requests/day}$ ($5,000\text{ requests/hour}$).
- Under peak load of $500\text{ incidents/hour}$ across India:
  - Average unique $0.25^\circ$ grid cells $\approx 40$ active clusters.
  - Hourly cache deduplication ratio $\approx 92\%$.
  - Actual external API calls $\approx 40\text{ requests/hour} \ll 5,000\text{ allowed/hour}$.
  - Daily consumption $\approx 960\text{ requests/day} \approx 9.6\%$ of the free daily budget.

---

## 7. Failure Semantics & Circuit Breaker (P2)

When an external provider fails:
1. **Timeout ($> 5.0\text{s}$)**: Log warning, record `provider_status = "TIMEOUT"`, return verdict `NEUTRAL`.
2. **HTTP 429 / 5xx**: Increment exponential backoff circuit breaker ($10\text{s}, 30\text{s}, 60\text{s}, 300\text{s}$). Return verdict `NEUTRAL` with `provider_status = "PROVIDER_RATE_LIMITED"`.
3. **Empty / Corrupt Response**: Log error, return verdict `NEUTRAL` with `provider_status = "MALFORMED_DATA"`.
4. **Zero Incident Rejection**: An outage **never** assigns a negative penalty or modifies verification status.
