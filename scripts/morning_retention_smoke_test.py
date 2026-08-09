import http.cookiejar
import json
import os
import sys
import tempfile
import threading
from datetime import date, timedelta
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import HTTPCookieProcessor, Request, build_opener


ROOT = Path(__file__).resolve().parents[1]


def next_workday(value, include_current=False):
    current = value if include_current else value + timedelta(days=1)
    while current.weekday() >= 5:
        current += timedelta(days=1)
    return current


def request_json(opener, url, method="GET", payload=None):
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Connection": "close", "X-Team-Org-Path": "ess"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    with opener.open(Request(url, data=body, headers=headers, method=method), timeout=15) as response:
        return json.load(response)


def main():
    with tempfile.TemporaryDirectory(prefix="team-loop-morning-retention-") as temporary_directory:
        os.environ["TEAM_LOOP_DB_PATH"] = str(Path(temporary_directory) / "morning-retention.db")
        os.environ["TEAM_LOOP_DATA_DIR"] = temporary_directory
        os.environ["TEAM_LOOP_BACKUP_DIR"] = str(Path(temporary_directory) / "backups")
        os.environ["TEAM_LOOP_ENV"] = "gray"
        sys.path.insert(0, str(ROOT))
        import server as app

        app.init_db()
        target = next_workday(date.today(), include_current=True)
        retained_from = date.fromisoformat(app.previous_workday(target))
        too_old = date.fromisoformat(app.previous_workday(retained_from))
        following_workday = next_workday(target)

        with app.connect() as conn:
            owner = conn.execute("SELECT id FROM users WHERE username='admin'").fetchone()
            owner_id = owner["id"]

            def add_item(item_date, title, status):
                cursor = conn.execute(
                    """
                    INSERT INTO morning_items(
                        owner_id, item_date, title, detail, status, priority, blocker, due_date,
                        updated_by, created_at, updated_at, active
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,1)
                    """,
                    (
                        owner_id,
                        item_date.isoformat(),
                        title,
                        f"{title} progress",
                        status,
                        "normal",
                        "",
                        item_date.isoformat(),
                        owner_id,
                        f"{item_date.isoformat()}T08:30:00",
                        f"{item_date.isoformat()}T09:00:00",
                    ),
                )
                conn.execute("UPDATE morning_items SET root_id=? WHERE id=?", (cursor.lastrowid, cursor.lastrowid))
                return cursor.lastrowid

            retained_id = add_item(retained_from, "previous-workday-done", "done")
            add_item(too_old, "two-workdays-old-done", "done")
            add_item(retained_from, "unfinished-carryover", "doing")

        server = ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base_url = f"http://127.0.0.1:{server.server_port}"
        try:
            opener = build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()))
            request_json(opener, f"{base_url}/api/login", "POST", {"username": "admin", "password": "admin123"})
            first = request_json(opener, f"{base_url}/api/morning-items?{urlencode({'date': target.isoformat()})}")
            by_title = {item["title"]: item for item in first["items"]}
            retained = by_title.get("previous-workday-done")
            if not retained or retained["id"] != retained_id or not retained.get("retained_from_previous_workday"):
                raise RuntimeError(f"Previous workday completion was not retained: {retained}")
            if "two-workdays-old-done" in by_title:
                raise RuntimeError("Completion remained visible for more than one workday")
            if by_title.get("unfinished-carryover", {}).get("item_date") != target.isoformat():
                raise RuntimeError("Unfinished item did not carry into the target workday")
            if first.get("retained_completed_count") != 1 or first.get("retained_from_date") != retained_from.isoformat():
                raise RuntimeError("Retention metadata is incorrect")

            following = request_json(
                opener,
                f"{base_url}/api/morning-items?{urlencode({'date': following_workday.isoformat()})}",
            )
            if any(item["title"] == "previous-workday-done" for item in following["items"]):
                raise RuntimeError("Retained completion leaked into the second workday")

            print(json.dumps({
                "status": "ok",
                "retained_from": retained_from.isoformat(),
                "visible_on": target.isoformat(),
                "hidden_on": following_workday.isoformat(),
                "weekend_skipped": (target - retained_from).days > 1,
            }, ensure_ascii=False))
        finally:
            server.shutdown()
            thread.join(timeout=5)
            server.server_close()


if __name__ == "__main__":
    main()
