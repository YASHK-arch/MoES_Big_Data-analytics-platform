import asyncio, subprocess, time, uuid, json, os, signal
from datetime import datetime, timezone
import asyncpg
from app.core.redis import AsyncRedisClient
from app.orchestration.events import OrchestrationEvent, OrchestrationEventType, AggregateType

DB_URL = "postgresql://postgres:postgres@localhost:5432/weather_platform_audit"
REDIS_URL = "redis://localhost:6379/5"
STREAM_NAME = "stream:weather:orchestration"
GROUP_NAME = "group:weather:orchestrators"

def run_redis_cmd(cmd_str: str) -> str:
    full_cmd = f"docker exec weather_redis redis-cli -n 5 {cmd_str}"
    try:
        return subprocess.check_output(full_cmd, shell=True).decode().strip()
    except Exception as e:
        return f"Error running '{cmd_str}': {e}"

def get_redis_stats():
    xinfo_groups = run_redis_cmd(f"XINFO GROUPS {STREAM_NAME}")
    xinfo_consumers = run_redis_cmd(f"XINFO CONSUMERS {STREAM_NAME} {GROUP_NAME}")
    xpending_summary = run_redis_cmd(f"XPENDING {STREAM_NAME} {GROUP_NAME}")
    xpending_detail = run_redis_cmd(f"XPENDING {STREAM_NAME} {GROUP_NAME} - + 20")
    return {
        "groups": xinfo_groups,
        "consumers": xinfo_consumers,
        "pending_summary": xpending_summary,
        "pending_detail": xpending_detail,
    }

async def main():
    print("=== S1 B7: Worker Crash & Stream Recovery on Redis DB 5 ===")
    redis = AsyncRedisClient(redis_url=REDIS_URL)
    await redis.connect()

    # Flush DB 5 and initialize stream & consumer group
    print("Flushing Redis DB 5 and initializing stream & consumer group...")
    await redis._execute_raw("FLUSHDB")
    await redis.xgroup_create(STREAM_NAME, GROUP_NAME, id_str="0", mkstream=True)

    # Create 200 reports in PostgreSQL directly with QUEUED status
    conn = await asyncpg.connect(DB_URL)
    cat_id = await conn.fetchval("SELECT id FROM event_categories LIMIT 1;")
    src_id = await conn.fetchval("SELECT id FROM sources LIMIT 1;")

    report_ids = []
    print("Creating 200 QUEUED reports in DB...")
    now = datetime.now(timezone.utc)
    for i in range(200):
        rep_id = uuid.uuid4()
        report_ids.append(rep_id)
        point_wkt = f"SRID=4326;POINT({72.8777 + i*0.0005} {19.0760 + i*0.0005})"
        trk_id = f"RPT-CRASH-{uuid.uuid4().hex[:6]}-{i:04d}"
        await conn.execute("""
            INSERT INTO weather_reports (id, tracking_id, source_id, category_id, reported_category, severity, title, geom, latitude, longitude, occurred_at, processing_status, verification_status, credibility_score, created_at, updated_at)
            VALUES ($1, $2, $3, $4, 'FLOOD_WATERLOGGING', 'HIGH', $5, $6, 19.0760, 72.8777, $7, 'QUEUED', 'PENDING', 0.0, $7, $7)
        """, rep_id, trk_id, src_id, cat_id, f"Crash test report {i}", point_wkt, now)
    await conn.close()

    # Push 200 events to stream
    print("Pushing 200 orchestration events to stream:weather:orchestration...")
    for i, rep_id in enumerate(report_ids):
        ev = OrchestrationEvent(
            event_id=uuid.uuid4(),
            event_type=OrchestrationEventType.INCIDENT_INGESTED,
            aggregate_type=AggregateType.WEATHER_REPORT,
            aggregate_id=rep_id,
            producer="audit_test",
            correlation_id=str(rep_id),
            idempotency_key=str(uuid.uuid4()),
            attempt=1,
            created_at=now,
        )
        fields = {
            "event_id": str(ev.event_id),
            "event_type": ev.event_type.value,
            "aggregate_type": ev.aggregate_type.value,
            "aggregate_id": str(ev.aggregate_id),
            "correlation_id": ev.correlation_id,
            "attempt": str(ev.attempt),
            "data": json.dumps(ev.model_dump(mode="json")),
        }
        await redis.xadd(STREAM_NAME, fields)

    print("Starting worker process 1 (orchestrator-worker-1)...")
    env = os.environ.copy()
    env["PYTHONPATH"] = "back-end"
    env["DATABASE_URL"] = "postgresql+asyncpg://postgres:postgres@localhost:5432/weather_platform_audit"
    env["REDIS_URL"] = REDIS_URL
    env["S3_BUCKET_NAME"] = "weather-media-audit"
    env["ORCHESTRATOR_CONSUMER_NAME"] = "orchestrator-worker-1"
    env["STREAM_CLAIM_IDLE_MS"] = "15000"  # 15s idle threshold for auto-reclaim

    proc1 = subprocess.Popen(
        ["back-end/.venv/bin/python", "-m", "app.workers.run_dispatcher"],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    # Let worker 1 process ~100 events (~6 seconds at ~16 events/s)
    print("Worker 1 processing events; waiting ~6.0s until ~100 are processed...")
    await asyncio.sleep(6.0)

    # 1. Before kill
    stats_before_kill = get_redis_stats()
    print("=== [B7] Before Kill ===")
    print("XINFO GROUPS:\n", stats_before_kill["groups"])
    print("XINFO CONSUMERS:\n", stats_before_kill["consumers"])
    print("XPENDING SUMMARY:\n", stats_before_kill["pending_summary"])
    print("XPENDING DETAIL (with idle times):\n", stats_before_kill["pending_detail"])

    print(f"Killing worker 1 (PID {proc1.pid}) with SIGKILL (kill -9)...")
    proc1.kill()
    proc1.wait()

    # 2. Right after kill
    stats_after_kill = get_redis_stats()
    print("=== [B7] Right After Kill ===")
    print("XINFO GROUPS:\n", stats_after_kill["groups"])
    print("XINFO CONSUMERS:\n", stats_after_kill["consumers"])
    print("XPENDING SUMMARY:\n", stats_after_kill["pending_summary"])
    print("XPENDING DETAIL (with idle times):\n", stats_after_kill["pending_detail"])

    # Restart worker process 2
    print("Starting worker process 2 (orchestrator-worker-2)...")
    env["ORCHESTRATOR_CONSUMER_NAME"] = "orchestrator-worker-2"
    proc2 = subprocess.Popen(
        ["back-end/.venv/bin/python", "-m", "app.workers.run_dispatcher"],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    periodic_snapshots = []
    # Monitor every 30s for up to 3 minutes (180s)
    start_restart_time = time.time()
    for elapsed in [30, 60, 90, 120, 150, 180]:
        time_to_wait = (start_restart_time + elapsed) - time.time()
        if time_to_wait > 0:
            await asyncio.sleep(time_to_wait)

        snap = get_redis_stats()
        periodic_snapshots.append((elapsed, snap))
        print(f"=== [B7] {elapsed}s After Restart ===")
        print("XINFO GROUPS:\n", snap["groups"])
        print("XINFO CONSUMERS:\n", snap["consumers"])
        print("XPENDING SUMMARY:\n", snap["pending_summary"])
        print("XPENDING DETAIL (with idle times):\n", snap["pending_detail"])

        # Check DB status
        conn = await asyncpg.connect(DB_URL)
        cur_final = await conn.fetchval("""
            SELECT count(*) FROM weather_reports 
            WHERE id = ANY($1::uuid[]) AND processing_status IN ('COMPLETED', 'FAILED');
        """, report_ids)
        await conn.close()
        print(f"Progress at {elapsed}s: {cur_final}/200 reached final state.")
        if cur_final == 200 and elapsed >= 60:
            # Reached full completion and at least 60s snapshot recorded
            print(f"All 200 events processed! Concluding test at {elapsed}s.")
            break

    # Terminate worker 2
    proc2.send_signal(signal.SIGTERM)
    try:
        proc2.wait(timeout=5)
    except Exception:
        proc2.kill()

    # Final DB counts
    conn = await asyncpg.connect(DB_URL)
    final_count = await conn.fetchval("""
        SELECT count(*) FROM weather_reports 
        WHERE id = ANY($1::uuid[]) AND processing_status IN ('COMPLETED', 'FAILED');
    """, report_ids)
    queued_count = await conn.fetchval("""
        SELECT count(*) FROM weather_reports 
        WHERE id = ANY($1::uuid[]) AND processing_status = 'QUEUED';
    """, report_ids)
    await conn.close()

    print(f"\n==========================================")
    print(f"Final reached count: {final_count} / 200")
    print(f"Still QUEUED count: {queued_count} / 200")
    print(f"B7 Verdict: {'PASS' if final_count == 200 else 'FAIL'}")
    print(f"==========================================")

    # Write raw output to audit/logs/B7.txt
    os.makedirs("audit/logs", exist_ok=True)
    with open("audit/logs/B7.txt", "w") as f:
        f.write("=== Before Kill ===\n")
        f.write(f"XINFO GROUPS:\n{stats_before_kill['groups']}\n")
        f.write(f"XINFO CONSUMERS:\n{stats_before_kill['consumers']}\n")
        f.write(f"XPENDING SUMMARY:\n{stats_before_kill['pending_summary']}\n")
        f.write(f"XPENDING DETAIL:\n{stats_before_kill['pending_detail']}\n\n")

        f.write("=== Right After Kill ===\n")
        f.write(f"XINFO GROUPS:\n{stats_after_kill['groups']}\n")
        f.write(f"XINFO CONSUMERS:\n{stats_after_kill['consumers']}\n")
        f.write(f"XPENDING SUMMARY:\n{stats_after_kill['pending_summary']}\n")
        f.write(f"XPENDING DETAIL:\n{stats_after_kill['pending_detail']}\n\n")

        for sec, snap in periodic_snapshots:
            f.write(f"=== {sec}s After Restart ===\n")
            f.write(f"XINFO GROUPS:\n{snap['groups']}\n")
            f.write(f"XINFO CONSUMERS:\n{snap['consumers']}\n")
            f.write(f"XPENDING SUMMARY:\n{snap['pending_summary']}\n")
            f.write(f"XPENDING DETAIL:\n{snap['pending_detail']}\n\n")

        f.write(f"Reached final state: {final_count}/200\nStill QUEUED: {queued_count}/200\n")

    await redis.close()

if __name__ == "__main__":
    asyncio.run(main())
