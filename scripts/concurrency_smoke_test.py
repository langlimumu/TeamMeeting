import concurrent.futures
import json
import os
import statistics
import sys
import tempfile
import threading
import time
from pathlib import Path
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]


def request(base_url, path, cookie, method="GET", payload=None):
    body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {"Connection": "close", "Cookie": cookie, "X-Team-Org-Path": "ess"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    started = time.perf_counter()
    with urlopen(Request(f"{base_url}{path}", data=body, headers=headers, method=method), timeout=30) as response:
        result = json.load(response)
        if response.status != 200:
            raise RuntimeError(f"{method} {path} returned {response.status}: {result}")
    return time.perf_counter() - started


def login(base_url):
    payload = json.dumps({"username": "admin", "password": "admin123"}).encode("utf-8")
    req = Request(
        f"{base_url}/api/login",
        data=payload,
        headers={"Content-Type": "application/json", "Connection": "close"},
        method="POST",
    )
    with urlopen(req, timeout=30) as response:
        json.load(response)
        cookie = response.headers.get("Set-Cookie", "").split(";", 1)[0]
    if not cookie.startswith("weekly_session="):
        raise RuntimeError("Login did not return a session cookie")
    return cookie


def main():
    with tempfile.TemporaryDirectory(prefix="team-loop-concurrency-") as temporary_directory:
        os.environ["TEAM_LOOP_DB_PATH"] = str(Path(temporary_directory) / "concurrency-smoke.db")
        os.environ["TEAM_LOOP_DATA_DIR"] = temporary_directory
        os.environ["TEAM_LOOP_BACKUP_DIR"] = str(Path(temporary_directory) / "backups")
        os.environ["TEAM_LOOP_ENV"] = "gray"
        os.environ["TEAM_LOOP_HTTP_MAX_WORKERS"] = "64"
        sys.path.insert(0, str(ROOT))
        import server as app

        app.init_db()
        server = app.BoundedThreadingHTTPServer(("127.0.0.1", 0), app.Handler, max_workers=64)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base_url = f"http://127.0.0.1:{server.server_port}"
        try:
            cookie = login(base_url)
            jobs = []
            read_paths = ["/api/me", "/api/members", "/api/team-moments"]
            for index in range(80):
                jobs.append((read_paths[index % len(read_paths)], "GET", None))
            for index in range(20):
                jobs.append((
                    "/api/team-posts",
                    "POST",
                    {"category": "general", "title": f"并发验证 {index + 1}", "content": "验证并发写入不会产生数据库锁错误。"},
                ))

            with concurrent.futures.ThreadPoolExecutor(max_workers=100) as executor:
                futures = [executor.submit(request, base_url, path, cookie, method, payload) for path, method, payload in jobs]
                latencies = [future.result(timeout=40) for future in futures]

            with app.connect() as conn:
                journal_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
                integrity = conn.execute("PRAGMA quick_check").fetchone()[0]
                created = conn.execute("SELECT COUNT(*) FROM team_posts WHERE title LIKE '并发验证 %'").fetchone()[0]
            if journal_mode.lower() != "wal" or integrity != "ok" or created != 20:
                raise RuntimeError({"journal_mode": journal_mode, "integrity": integrity, "created": created})

            ordered = sorted(latencies)
            p95 = ordered[max(0, int(len(ordered) * 0.95) - 1)]
            print(json.dumps({
                "status": "ok",
                "requests": len(latencies),
                "writes": created,
                "journal_mode": journal_mode,
                "median_ms": round(statistics.median(latencies) * 1000, 1),
                "p95_ms": round(p95 * 1000, 1),
                "max_ms": round(max(latencies) * 1000, 1),
                "max_workers": server.max_workers,
            }, ensure_ascii=False))
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


if __name__ == "__main__":
    main()
