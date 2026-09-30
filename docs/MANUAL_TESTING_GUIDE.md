# Manual Testing & Visual Verification Guide

This guide provides simple, step-by-step instructions to test every feature of the **National Weather Big Data Analytics Platform** in your web browser.

---

## 🚀 Quick Setup Check

Make sure your servers are running:
- **Frontend URL**: [http://localhost:5173](http://localhost:5173)
- **Backend API URL**: [http://127.0.0.1:8001](http://127.0.0.1:8001) (or `:8000`)
- **API Health Check**: Open [http://127.0.0.1:8001/ready](http://127.0.0.1:8001/ready) — should show `"status": "ready"`.

---

## 🔑 Login Credentials

| Role | Email | Password | Allowed Areas |
|---|---|---|---|
| **Operator / Reviewer** | `operator@weather-platform.gov.in` | `EmergencyOps2026!` | Verification Queue, Audit Logs, Export, Dashboard, Maps |
| **System Administrator** | `admin@weather-platform.gov.in` | `EmergencyAdmin2026!` | All areas including admin management |
| **Citizen User** | `citizen@weather-platform.gov.in` | `CitizenPassword2026!` | Citizen Dashboard, Report Submission, Public Tracking |

---

## 🧪 Test Checklist

### 1. First Visit & Location Onboarding Gate
*Tests how the platform detects and personalizes the user's city.*

- **Where to go**: Open [http://localhost:5173/welcome](http://localhost:5173/welcome) (or open incognito).
- **What to do**:
  1. A **"Select Your Location"** modal will pop up.
  2. Click **"Use My Current Location"** (or type a city like `Bengaluru`, `Mumbai`, or `Delhi` in the search box).
  3. Click **"Confirm Location"**.
- **What to expect**:
  - The modal closes.
  - The top navbar now displays your selected city (e.g. `📍 Bengaluru, Karnataka`).
  - Your selection is remembered even if you refresh the page.

---

### 2. "My Area" Citizen Dashboard
*Tests hyper-local disaster awareness, emergency contacts, and proximity tools.*

- **Where to go**: Navigate to [http://localhost:5173/citizen-dashboard](http://localhost:5173/citizen-dashboard).
- **What to do & What to expect**:
  1. **Proximity Incident Map**: Look at the interactive Leaflet map. It is centered around your chosen city with colored disaster markers (Red = Severe, Amber = Moderate). Click any marker to see incident details and distance.
  2. **Emergency Contacts Card**: Scroll down to the Emergency Directory card. You should see one-tap clickable phone numbers:
     - NDRF: `1078`
     - State Disaster Management (SDRF): `1070`
     - District Emergency Operations Center (DEOC): `1077`
     - Central Water Commission Flood Hotline: `1800-11-2020`
  3. **Nearby Relief Shelters**: Look at the "Emergency Shelters & Relief Camps" section. It displays active government relief camps sorted by distance (with bed capacity and contact numbers).

---

### 3. Road Route Hazard & Corridor Blockage Checker
*Tests checking whether a driving route passes through active flood or landslide zones.*

- **Where to go**: In the Citizen Dashboard, scroll to the **"Route Hazard Checker"** widget.
- **What to do**:
  1. Set **Start Point** (e.g., `12.9716, 77.5946` for Bengaluru City Center).
  2. Set **Destination** (e.g., `13.0827, 80.2707` for Chennai).
  3. Click **"Check Route Safety"**.
- **What to expect**:
  - A real road routing path (OSRM) is drawn on the map.
  - A 2 km safety buffer corridor is calculated.
  - If hazards intersect the route, you see an amber or red warning listing the blocked road segments and hazard categories (e.g., `Flooding on NH48`).
  - If clear, a green badge displays: `"Route Clear — No Active Road Hazards Detected"`.

---

### 4. Citizen Incident Reporting (With Photo Upload)
*Tests submitting a fresh crowd-sourced incident into the big-data ingestion pipeline.*

- **Where to go**: Click **"Report Incident"** in the navbar, or go to [http://localhost:5173/report](http://localhost:5173/report).
- **What to do**:
  1. **Hazard Category**: Select a category (e.g., `Flooding & Waterlogging`, `Dense Fog`, or `Heavy Rainfall`).
  2. **Severity**: Choose `High` or `Severe`.
  3. **Title**: Enter `"Waterlogging near City Metro Station"`.
  4. **Description**: Enter `"Water level reached 2 feet, traffic halted near underpass."`.
  5. **Location**: Click **"Detect GPS Location"** or click on the mini-map to pin coordinates.
  6. **Attach Photo**: Attach any test JPG/PNG image.
  7. Click **"Submit Weather Report"**.
- **What to expect**:
  - A success screen pops up with a **unique Tracking ID** (e.g., `RPT-20261001-A1B2C3D4`).
  - The status is shown as **`PENDING`** verification.
  - **Copy this Tracking ID** for the next test.

---

### 5. Public Incident Tracking
*Tests public accountability lookup using a tracking ID.*

- **Where to go**: Click **"Track Report"** in the navbar, or go to [http://localhost:5173/track-report](http://localhost:5173/track-report).
- **What to do**:
  1. Paste the **Tracking ID** you copied from Step 4.
  2. Click **"Track Status"**.
- **What to expect**:
  - The status timeline card appears showing:
    - Current state badge (`PENDING`).
    - Submitted timestamp and category icon.
    - Assigned authority (e.g., `Pending Review by DEOC Operator`).
    - Mini map showing the exact reported coordinates.

---

### 6. Operator Login
*Tests role-based access control and JWT authentication.*

- **Where to go**: Click **"Operator Login"** (top right) or go to [http://localhost:5173/login](http://localhost:5173/login).
- **What to do**:
  1. Enter Email: `operator@weather-platform.gov.in`
  2. Enter Password: `EmergencyOps2026!`
  3. Click **"Sign In"**.
- **What to expect**:
  - Green success notification: `"Welcome back, Operator!"`.
  - Automatic redirect to the **Operator Verification Queue** (`/admin/queue`).
  - Top navbar updates to show the operator profile avatar and role badge (`OPERATOR`).

---

### 7. Priority Verification & Triage Queue
*Tests operator triage, side-by-side evidence inspection, and real-time verification.*

- **Where to go**: [http://localhost:5173/admin/queue](http://localhost:5173/admin/queue).
- **What to do & What to expect**:
  1. **Priority List**: You see incidents sorted by urgency and severity. Incidents you just submitted appear at the top.
  2. **Side-by-Side Inspection**: Click any incident row to open the review panel.
     - Check the **AI Credibility Breakdown**: shows score between `0.0000` and `0.9800` with transparent factors (Source prior, photo quality, cluster corroboration, station check).
     - Check the **Corroborating Evidence**: displays nearby news articles, satellite radar data, or social feeds.
  3. **Verify an Incident**:
     - Click the green **"Verify"** button.
     - Add an optional review note: `"Confirmed via local DEOC ground unit"`.
     - Click **"Confirm Verification"**.
     - **Expected**: Status badge changes to **`VERIFIED`** immediately. The queue removes it or moves it to verified.
  4. **Reject an Incident**:
     - Pick another incident and click the red **"Reject"** button.
     - Select rejection reason: `Misinformation / Spam` or `Unrelated`.
     - Click **"Confirm Rejection"**.
     - **Expected**: Status badge changes to **`REJECTED`**.

---

### 8. Bulk Verification & Data Export
*Tests operator bulk-action safety and CSV/GeoJSON streaming exports.*

- **Where to go**: In [http://localhost:5173/admin/queue](http://localhost:5173/admin/queue).
- **What to do & What to expect**:
  1. **Bulk Selection**:
     - Check the checkboxes next to 2 or 3 incidents in the table.
     - An action banner appears at the bottom: `"2 incidents selected"`.
     - Click **"Bulk Verify"**.
     - **Expected**: All selected incidents are verified simultaneously in one atomic transaction.
  2. **Export Dataset**:
     - Click the **"Export"** dropdown button (top right of the table).
     - Click **"Export as CSV"**: A `.csv` file downloads immediately containing incident metadata.
     - Click **"Export as GeoJSON"**: A `.geojson` file downloads containing PostGIS spatial feature collections.

---

### 9. Admin Audit Log Trail
*Tests immutable audit logging required for government operations.*

- **Where to go**: Click **"Audit Logs"** in the operator menu or go to [http://localhost:5173/admin/audit-logs](http://localhost:5173/admin/audit-logs).
- **What to do & What to expect**:
  - A chronological table appears showing every action taken:
    - `VERIFY` — with timestamp and operator ID.
    - `REJECT` — with the recorded reason.
    - `EXPORT` — records dataset export events.
  - Search or filter by action type (`VERIFY`, `REJECT`) to inspect the trail.

---

### 10. Executive Dashboard & Real-Time Analytics
*Tests macro situational awareness and live KPI monitoring.*

- **Where to go**: Click **"Dashboard"** in the navbar or go to [http://localhost:5173/dashboard](http://localhost:5173/dashboard).
- **What to do & What to expect**:
  1. **KPI Cards**:
     - **Total Incidents**: Displays live count (e.g. `2,041+`).
     - **Verified Incidents**: Shows count and verification percentage.
     - **Severe Hazards**: Shows active high/severe alerts.
  2. **Charts**:
     - **Category Breakdown**: Interactive bar/pie chart showing distribution across Flooding, Heavy Rain, Fog, Cyclone, etc.
     - **Diurnal Hourly Trends**: Graph showing 24-hour peak occurrence times.
  3. **Demo Data Toggle**:
     - Look for the toggle switch labeled **"Hide Demo Data"** at the top right of the dashboard.
     - Toggle it **ON**.
     - **Expected**: All incidents with the amber `[DEMO]` badge disappear, and KPI numbers recalculate to show only real operational data.
     - Toggle it **OFF**: Demo incidents return immediately.

---

### 11. National Map & Maritime EEZ Boundary
*Tests the All-India geospatial view, coastal boundary, and cyclone tracks.*

- **Where to go**: Click **"National Map"** or go to [http://localhost:5173/national-map](http://localhost:5173/national-map).
- **What to do & What to expect**:
  1. **All-India View**: Interactive map showing disaster clustering across the entire country.
  2. **EEZ Maritime Boundary**: Look at the coastline of India — a cyan/blue 200-nautical-mile maritime boundary polygon is overlaid.
  3. **Official Cyclone Tracks**: Severe storm tracks (e.g., Bay of Bengal / Arabian Sea cyclonic storm trajectories) appear as dashed paths with predicted landfall points.
  4. **Heatmap Toggle**:
     - In the map layer control, click the **"🔥 Heatmap"** button.
     - **Expected**: The markers convert into a smooth color density heatmap highlighting hazard hotspots.

---

### 12. Bilingual Language Switcher (English ↔ Hindi)
*Tests vernacular localization across the application.*

- **Where to go**: Any page (e.g., [http://localhost:5173/dashboard](http://localhost:5173/dashboard)).
- **What to do**:
  1. Look at the top right of the navbar for the language selector button (`EN / हिंदी`).
  2. Click **"हिंदी"**.
- **What to expect**:
  - The UI instantly switches to Hindi without reloading:
    - Navbar: `डैशबोर्ड`, `राष्ट्रीय मानचित्र`, `रिपोर्ट दर्ज करें`, `स्थिति ट्रैक करें`.
    - Incident categories translate (e.g., `बाढ़ और जलभराव`, `घना कोहरा`, `भारी बारिश`).
    - Emergency contact titles translate to Hindi.
  3. Click **"EN"** to return to English.

---

## 📋 Quick Test Summary Table

| Test # | Feature | URL | Expected Result |
|:---:|---|---|---|
| 1 | Location Modal | `/welcome` | Detects city, shows `📍 City` in navbar |
| 2 | Citizen "My Area" | `/citizen-dashboard` | Map centered on city, nearby shelters, emergency hotline cards |
| 3 | Road Corridor Check | `/citizen-dashboard` | Calculates 2km buffer along driving route, flags road blockages |
| 4 | Submit Report | `/report` | Submits form + photo, generates `RPT-...` tracking ID |
| 5 | Track Report | `/track-report` | Shows live status (`PENDING`), timeline, and pinned map |
| 6 | Operator Login | `/login` | Accepts `operator@weather-platform.gov.in`, opens `/admin/queue` |
| 7 | Triage Queue | `/admin/queue` | Inspects credibility score & evidence; Verify / Reject changes status |
| 8 | Bulk Actions & Export | `/admin/queue` | Multi-select verify; downloads clean CSV and GeoJSON |
| 9 | Audit Log Viewer | `/admin/audit-logs` | Immutable audit log of every operator verify/reject action |
| 10 | Executive Dashboard | `/dashboard` | 2,041+ incidents, category charts; "Hide Demo Data" toggle works |
| 11 | National Map | `/national-map` | India EEZ maritime border, cyclone tracks, density heatmap toggle |
| 12 | Vernacular Switcher | Top right navbar | Instant seamless translation between English & Hindi |
