import json

with open("audit/logs/e3_baseline_runs.json") as f:
    base = json.load(f)

with open("audit/logs/e3_optimized_runs.json") as f:
    opt = json.load(f)

lines = []
lines.append("=== E3 Honest B4 Load Test & Geo Payload Optimization ===")
lines.append("")
b_raw = base["payload"]["raw"]
b_gz = base["payload"]["gzip"]
o_raw = opt["payload"]["raw"]
o_gz = opt["payload"]["gzip"]
d_raw = b_raw - o_raw
d_gz = b_gz - o_gz
lines.append("Payload Size (GET /api/v1/geo/incidents default 500 records):")
lines.append(f"  - BEFORE: Raw {b_raw} bytes ({b_raw/1024:.1f} KB) | Gzip {b_gz} bytes ({b_gz/1024:.1f} KB)")
lines.append(f"  - AFTER : Raw {o_raw} bytes ({o_raw/1024:.1f} KB) | Gzip {o_gz} bytes ({o_gz/1024:.1f} KB)")
lines.append(f"  - SAVINGS: -{d_raw} bytes raw (-{d_raw/b_raw*100:.1f}%), -{d_gz} bytes gzip (-{d_gz/b_gz*100:.1f}%)")
lines.append("")

for label, data in [("BASELINE", base), ("OPTIMIZED", opt)]:
    lines.append(f"=== {label} LOAD TEST RESULTS (50 users, 20s, 3 runs) ===")
    for w in [1, 4]:
        runs = data[f"workers_{w}"]
        lines.append(f"\n--- uvicorn --workers {w} ---")
        avg_tot_rps = sum(r["total_rps"] for r in runs) / len(runs)
        avg_cpu = sum(r["cpu_pct"] for r in runs) / len(runs)
        lines.append(f"Overall Average: Total RPS = {avg_tot_rps:.1f} req/s | Generator CPU = {avg_cpu:.1f}%")
        
        for ep in runs[0]["endpoints"]:
            ep_rps = sum(r["endpoints"][ep]["rps"] for r in runs) / len(runs)
            ep_p50 = sum(r["endpoints"][ep]["p50"] for r in runs) / len(runs)
            ep_p95 = sum(r["endpoints"][ep]["p95"] for r in runs) / len(runs)
            lines.append(f"  Endpoint: {ep}")
            lines.append(f"    RPS = {ep_rps:.1f} req/s | p50 = {ep_p50:.1f} ms | p95 = {ep_p95:.1f} ms")
    lines.append("")

out = "\n".join(lines)
print(out)
with open("audit/logs/E3.txt", "w") as f:
    f.write(out + "\n")
