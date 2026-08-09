import argparse
import os
import subprocess
import sys
import time
from pathlib import Path


WATCH_SUFFIXES = {".py", ".html", ".css", ".js", ".json"}


def file_snapshot(root: Path) -> dict[str, tuple[int, int]]:
    paths = [root / "server.py", root / "team_loop", root / "static", root / "previews"]
    snapshot = {}
    for path in paths:
        candidates = [path] if path.is_file() else path.rglob("*") if path.exists() else []
        for candidate in candidates:
            if not candidate.is_file() or candidate.suffix.lower() not in WATCH_SUFFIXES:
                continue
            try:
                stat = candidate.stat()
            except OSError:
                continue
            snapshot[str(candidate)] = (stat.st_mtime_ns, stat.st_size)
    return snapshot


def start_child(root: Path, host: str, port: int) -> subprocess.Popen:
    environment = os.environ.copy()
    environment["TEAM_LOOP_ENV"] = "development"
    environment["TEAM_LOOP_RELEASE"] = f"dev-{int(time.time() * 1000)}"
    command = [sys.executable, "-u", "server.py", "--host", host, "--port", str(port)]
    return subprocess.Popen(command, cwd=root, env=environment)


def stop_child(process: subprocess.Popen | None) -> None:
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Team Loop with development hot reload")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--interval", type=float, default=0.8)
    args = parser.parse_args()

    root = Path(__file__).resolve().parent.parent
    previous = file_snapshot(root)
    process = start_child(root, args.host, args.port)
    print(f"Hot reload enabled: http://{args.host}:{args.port}", flush=True)

    try:
        while True:
            time.sleep(max(0.25, args.interval))
            current = file_snapshot(root)
            changed = current != previous
            child_exited = process.poll() is not None
            if not changed and not child_exited:
                continue
            if changed:
                print("Files changed, restarting Team Loop...", flush=True)
            else:
                print(f"Team Loop exited with code {process.returncode}, restarting...", flush=True)
            stop_child(process)
            time.sleep(0.35)
            previous = current
            process = start_child(root, args.host, args.port)
    except KeyboardInterrupt:
        print("\nStopping hot reload server...", flush=True)
    finally:
        stop_child(process)


if __name__ == "__main__":
    main()
