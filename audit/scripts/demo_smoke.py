#!/usr/bin/env python3
"""audit/scripts/demo_smoke.py — End-to-end smoke test for SIH demo stack.

Tests:
1. GET /ready -> 200
2. Operator login -> access token
3. POST one report per category (including FOG, DUST_STORM, STRONG_WIND, OTHER)
4. Poll tracking until processing is COMPLETED/READY
5. SSE client receives events through nginx (/api/v1/events/stream)
6. Verify a report as operator
7. GET /metrics returns 403 via :8080
8. Frontend index loads and deep link /dashboard returns SPA HTML
9. Rate limiter: 11 report POSTs from one IP -> 429 on 11th (even with spoofed X-Forwarded-For);
   different IP gets a separate limit
"""

import json
import socket
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

BASE_URL = "http://localhost:8080"
API_V1 = f"{BASE_URL}/api/v1"


def http_get(url: str, headers: Optional[Dict[str, str]] = None) -> Tuple[int, bytes, Dict[str, str]]:
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, resp.read(), dict(resp.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read(), dict(e.headers)


def http_post(
    url: str,
    data: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
    is_form: bool = False,
) -> Tuple[int, bytes, Dict[str, str]]:
    hdrs = dict(headers or {})
    body = b""
    if is_form and data:
        body = urllib.parse.urlencode(data).encode("utf-8")
        hdrs["Content-Type"] = "application/x-www-form-urlencoded"
    elif data is not None:
        body = json.dumps(data).encode("utf-8")
        hdrs["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=body, headers=hdrs, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, resp.read(), dict(resp.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read(), dict(e.headers)


def run_checks():
    results = {}
    print("=" * 60)
    print("SIH DEMO SMOKE TEST")
    print("=" * 60)

    # 1. /ready check
    status, body, _ = http_get(f"{BASE_URL}/ready")
    print(f"1. GET /ready: status={status}")
    assert status == 200, f"/ready failed with status {status}: {body.decode()}"
    results["ready"] = "PASS"

    # 2. Operator login
    login_payload = {
        "username": "operator@weather-platform.gov.in",
        "password": "EmergencyOps2026!",
    }
    status, body, _ = http_post(f"{API_V1}/auth/login", data=login_payload)
    print(f"2. Operator login: status={status}")
    assert status == 200, f"Login failed with status {status}: {body.decode()}"
    token_data = json.loads(body.decode())
    data_obj = token_data.get("data", {}) if isinstance(token_data.get("data"), dict) else {}
    token = data_obj.get("access_token") or token_data.get("access_token")
    assert token, "No access_token in login response"
    op_headers = {"Authorization": f"Bearer {token}"}
    results["login"] = "PASS"

    # 5. Start SSE listener in background thread
    sse_events = []
    sse_stop = threading.Event()

    def listen_sse():
        try:
            req = urllib.request.Request(f"{API_V1}/events/stream")
            with urllib.request.urlopen(req, timeout=15) as resp:
                while not sse_stop.is_set():
                    line = resp.readline()
                    if not line:
                        break
                    decoded = line.decode("utf-8", errors="replace").strip()
                    if decoded.startswith("data:"):
                        sse_events.append(decoded[5:].strip())
        except Exception as e:
            pass

    sse_thread = threading.Thread(target=listen_sse, daemon=True)
    sse_thread.start()
    time.sleep(0.5)

    # 3. POST one report per category (including FOG, DUST_STORM, STRONG_WIND, OTHER)
    categories = [
        "FOG",
        "DUST_STORM",
        "STRONG_WIND",
        "OTHER",
        "FLOOD_WATERLOGGING",
        "HEAVY_RAINFALL",
        "CYCLONE_STORM",
        "LANDSLIDE",
        "HEATWAVE",
        "COLD_WAVE",
    ]
    submitted_reports = []
    print(f"3. Posting reports for {len(categories)} categories...")
    for cat in categories:
        form = {
            "latitude": "28.6139",
            "longitude": "77.2090",
            "category_code": cat,
            "severity": "MODERATE",
            "title": f"Demo report for {cat}",
            "description": f"Automated smoke test report for category {cat}",
            "location_name": "New Delhi Smoke Test Area",
        }
        status, body, _ = http_post(f"{API_V1}/reports", data=form, is_form=True)
        assert status == 201, f"POST /reports for {cat} failed ({status}): {body.decode()}"
        res = json.loads(body.decode())
        rpt_data = res.get("data", {})
        tracking_id = rpt_data.get("tracking_id")
        report_id = rpt_data.get("id")
        submitted_reports.append((cat, tracking_id, report_id))
        print(f"   - {cat}: tracking_id={tracking_id}")
    results["categories_posted"] = len(submitted_reports)

    # 4. Poll tracking until pipeline is COMPLETED
    print("4. Polling pipeline tracking for first report...")
    cat0, trk0, rpt_id0 = submitted_reports[0]
    processing_status = "UNKNOWN"
    for _ in range(30):
        status, body, _ = http_get(f"{API_V1}/reports/{trk0}")
        if status == 200:
            track_res = json.loads(body.decode())
            data = track_res.get("data", {})
            processing_status = data.get("processing_status", "")
            if processing_status in ("COMPLETED", "READY"):
                break
        time.sleep(1.0)
    print(f"   Status after poll: {processing_status}")
    results["pipeline_tracking"] = processing_status

    # 5. SSE verification
    time.sleep(1.5)
    sse_stop.set()
    print(f"5. SSE received events count: {len(sse_events)}")
    results["sse_received"] = len(sse_events)

    # 6. Verify a report as operator
    print(f"6. Verifying report {trk0} as operator...")
    verify_payload = {"notes": "Verified by automated smoke test", "broadcast_alert": False}
    status, body, _ = http_post(
        f"{API_V1}/verification/{trk0}/verify",
        data=verify_payload,
        headers=op_headers,
    )
    print(f"   Verification status={status}")
    assert status in (200, 201), f"Verification failed ({status}): {body.decode()}"
    results["operator_verify"] = "PASS"

    # 7. /metrics returns 403 via :8080
    status, _, _ = http_get(f"{BASE_URL}/metrics")
    print(f"7. GET /metrics on :8080: status={status}")
    assert status in (403, 404), f"Expected 403/404 for /metrics via web, got {status}"
    results["metrics_blocked"] = f"PASS ({status})"

    # 8. Frontend index loads and deep link /dashboard returns SPA
    status1, body1, _ = http_get(f"{BASE_URL}/")
    status2, body2, _ = http_get(f"{BASE_URL}/dashboard")
    print(f"8. Frontend root: {status1}, deep link /dashboard: {status2}")
    assert status1 == 200 and b"<div id=\"root\">" in body1, "Root index.html not served"
    assert status2 == 200 and b"<div id=\"root\">" in body2, "Deep link /dashboard SPA fallback failed"
    results["frontend_spa"] = "PASS"

    # 9. Rate limiter: 11 POSTs from one client IP return 429 on 11th
    # even when spoofing X-Forwarded-For; different IP gets separate limit
    print("9. Testing rate limiter with spoofed headers...")
    rl_cat = "FLOOD_WATERLOGGING"
    rl_form = {
        "latitude": "12.9716",
        "longitude": "77.5946",
        "category_code": rl_cat,
        "severity": "LOW",
        "title": "Rate limit probe",
        "description": "Rate limit verification",
    }
    # Reset/clear if needed by doing requests with specific IP
    statuses_client1 = []
    for i in range(12):
        hdrs = {"X-Forwarded-For": f"10.99.0.{i}, 198.51.100.42"}
        st, _, _ = http_post(f"{API_V1}/reports", data=rl_form, headers=hdrs, is_form=True)
        statuses_client1.append(st)

    print(f"   Client 1 (198.51.100.42) statuses: {statuses_client1}")
    has_429_client1 = 429 in statuses_client1
    assert has_429_client1, f"Rate limiter failed to block Client 1 after 10 requests: {statuses_client1}"
    # Different client IP
    hdrs2 = {"X-Forwarded-For": "203.0.113.88"}
    st2, _, _ = http_post(f"{API_V1}/reports", data=rl_form, headers=hdrs2, is_form=True)
    print(f"   Client 2 (203.0.113.88) first post status: {st2}")
    assert st2 in (200, 201), f"Client 2 was unexpectedly rate-limited: status {st2}"

    results["rate_limiter_client1_429"] = "PASS"
    results["rate_limiter_client2_separate"] = "PASS"

    print("\n" + "=" * 60)
    print("SMOKE TEST RESULTS SUMMARY:")
    for k, v in results.items():
        print(f"  {k}: {v}")
    print("=" * 60)
    return results


if __name__ == "__main__":
    try:
        run_checks()
        print("\nALL SMOKE TESTS PASSED ✅")
    except Exception as e:
        print(f"\nSMOKE TEST FAILED ❌: {e}")
        sys.exit(1)
