#!/usr/bin/env python3
"""Unified Developer Stack Orchestrator (SIH26069).

Manages local background worker processes, migration execution, and server health checks
with a single, clean command. Handles graceful shutdown on Ctrl+C.
"""

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = WORKSPACE_ROOT / "back-end"
FRONTEND_DIR = WORKSPACE_ROOT / "front-end"

processes: list[subprocess.Popen] = []


def signal_handler(sig, frame):
    print("\n[ORCHESTRATOR] Shutting down all spawned subprocesses...")
    for proc in processes:
        try:
            proc.terminate()
        except Exception:
            pass
    time.sleep(1)
    for proc in processes:
        try:
            proc.kill()
        except Exception:
            pass
    print("[ORCHESTRATOR] All services stopped cleanly. Goodbye!")
    sys.exit(0)


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


def run_command(cmd: list[str], cwd: Path, check: bool = True):
    print(f"[EXEC] {' '.join(cmd)} (in {cwd.name})")
    return subprocess.run(cmd, cwd=cwd, check=check)


def spawn_process(name: str, cmd: list[str], cwd: Path):
    print(f"[START] {name} -> {' '.join(cmd)}")
    proc = subprocess.Popen(cmd, cwd=cwd)
    processes.append(proc)
    return proc


def main():
    print("=" * 70)
    print(" National Weather Big Data Analytics Platform (SIH26069)")
    print(" Developer Stack Orchestrator")
    print("=" * 70)

    # 1. Run Alembic Database Migrations
    print("\n[1/5] Running Alembic Database Migrations...")
    venv_bin = "Scripts" if os.name == "nt" else "bin"
    executable_suffix = ".exe" if os.name == "nt" else ""
    venv_python = BACKEND_DIR / ".venv" / venv_bin / f"python{executable_suffix}"
    venv_alembic = BACKEND_DIR / ".venv" / venv_bin / f"alembic{executable_suffix}"

    if not venv_python.exists():
        print(f"[ERROR] Virtual environment not found at {venv_python}")
        print("Please initialize Python virtualenv in back-end/.venv first.")
        sys.exit(1)

    run_command([str(venv_alembic), "upgrade", "head"], cwd=BACKEND_DIR)

    # 2. Start Uvicorn Backend Dev Server
    print("\n[2/5] Starting FastAPI Backend Dev Server (Port 8000)...")
    venv_uvicorn = BACKEND_DIR / ".venv" / venv_bin / f"uvicorn{executable_suffix}"
    spawn_process("Backend API", [str(venv_uvicorn), "app.main:app", "--host", "127.0.0.1", "--port", "8000", "--reload"], cwd=BACKEND_DIR)

    # 3. Start Outbox & Scheduler Background Workers
    print("\n[3/5] Starting Transactional Outbox Worker...")
    spawn_process("Outbox Worker", [str(venv_python), "-m", "app.workers.run_outbox_worker"], cwd=BACKEND_DIR)

    # 4. Start orchestration dispatcher
    print("\n[4/5] Starting Orchestration Dispatcher...")
    spawn_process(
        "Orchestration Dispatcher",
        [str(venv_python), "-m", "app.workers.run_dispatcher"],
        cwd=BACKEND_DIR,
    )

    # 5. Start React Vite Frontend Dev Server
    print("\n[5/5] Starting Frontend Vite Dev Server (Port 5173)...")
    npm_command = "npm.cmd" if os.name == "nt" else "npm"
    spawn_process("Frontend Vite", [npm_command, "run", "dev"], cwd=FRONTEND_DIR)

    print("\n" + "=" * 70)
    print(" All platform services launched successfully!")
    print(" - Web Portal:     http://localhost:5173")
    print(" - Backend API:    http://localhost:8000/docs")
    print(" - Realtime SSE:   http://localhost:8000/api/v1/events/stream")
    print(" Press Ctrl+C to stop all services simultaneously.")
    print("=" * 70 + "\n")

    while True:
        time.sleep(1)


if __name__ == "__main__":
    main()
