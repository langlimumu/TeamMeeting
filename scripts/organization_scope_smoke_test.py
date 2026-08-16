import http.cookiejar
import json
import os
import sys
import tempfile
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.request import HTTPCookieProcessor, Request, build_opener
from urllib.error import HTTPError


ROOT = Path(__file__).resolve().parents[1]


def request_json(opener, url, path, method="GET", payload=None, org_path=""):
    headers = {"Content-Type": "application/json"}
    if org_path:
        headers["X-Team-Org-Path"] = org_path
    request = Request(
        f"{url}{path}",
        data=json.dumps(payload).encode("utf-8") if payload is not None else None,
        headers=headers,
        method=method,
    )
    try:
        with opener.open(request, timeout=15) as response:
            return json.load(response)
    except HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {path} returned HTTP {error.code}: {detail}") from error


def expect_http_status(opener, url, path, expected_status, method="GET", payload=None, org_path=""):
    headers = {"Content-Type": "application/json"}
    if org_path:
        headers["X-Team-Org-Path"] = org_path
    request = Request(
        f"{url}{path}",
        data=json.dumps(payload).encode("utf-8") if payload is not None else None,
        headers=headers,
        method=method,
    )
    try:
        opener.open(request, timeout=15).close()
    except HTTPError as error:
        if error.code == expected_status:
            return
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {path} returned HTTP {error.code}, expected {expected_status}: {detail}") from error
    raise RuntimeError(f"{method} {path} returned success, expected HTTP {expected_status}")


def main():
    with tempfile.TemporaryDirectory(prefix="team-loop-org-") as temporary_directory:
        os.environ["TEAM_LOOP_DB_PATH"] = str(Path(temporary_directory) / "org-smoke.db")
        os.environ["TEAM_LOOP_DATA_DIR"] = temporary_directory
        os.environ["TEAM_LOOP_BACKUP_DIR"] = str(Path(temporary_directory) / "backups")
        os.environ["TEAM_LOOP_ENV"] = "gray"
        sys.path.insert(0, str(ROOT))
        import server as app

        app.init_db()
        with app.connect() as conn:
            units = {row["name"]: row for row in app.organization_rows(conn)}
            mo = units["MO"]
            ws = units["WS"]
            rs = units["RS"]
            conn.execute("UPDATE org_units SET sso_groups=? WHERE id=?", (json.dumps(["ORG-MO"]), mo["id"]))
            conn.execute("UPDATE org_units SET sso_groups=? WHERE id=?", (json.dumps(["ORG-WS"]), ws["id"]))
            conn.execute("UPDATE users SET org_unit_id=? WHERE username='user'", (mo["id"],))
            salt, password_hash = app.make_hash("ws123456")
            ws_cursor = conn.execute(
                """
                INSERT INTO users(username, employee_id, salt, password_hash, display_name, role, user_type, org_unit_id, active, created_at)
                VALUES('ws-user','WS001',?,?, 'WS成员','user',?,?,1,?)
                """,
                (salt, password_hash, app.DEFAULT_USER_TYPE_KEY, ws["id"], app.now_iso()),
            )
            ws_user_id = ws_cursor.lastrowid
            app.sync_member_for_user(conn, ws_user_id)
            rs_salt, rs_password_hash = app.make_hash("rs123456")
            rs_cursor = conn.execute(
                """
                INSERT INTO users(username, employee_id, salt, password_hash, display_name, role, user_type, org_unit_id, active, created_at)
                VALUES('rs-user','RS001',?,?, 'RS成员','user',?,?,1,?)
                """,
                (rs_salt, rs_password_hash, app.DEFAULT_USER_TYPE_KEY, rs["id"], app.now_iso()),
            )
            rs_user_id = rs_cursor.lastrowid
            app.sync_member_for_user(conn, rs_user_id)
            user_id = conn.execute("SELECT id FROM users WHERE username='user'").fetchone()[0]
            conn.execute(
                "INSERT INTO thank_you_votes(voter_id, receiver_id, week_start, evidence, created_at) VALUES(?,?,?,?,?)",
                (user_id, ws_user_id, app.week_start(app.today_iso()), "跨层级协作支持", app.now_iso()),
            )
            cross_vote_id = conn.execute(
                "INSERT INTO thank_you_votes(voter_id, receiver_id, week_start, evidence, created_at) VALUES(?,?,?,?,?)",
                (ws_user_id, rs_user_id, app.week_start(app.today_iso()), "跨团队协作支持", app.now_iso()),
            ).lastrowid
            admin_id = conn.execute("SELECT id FROM users WHERE username='admin'").fetchone()[0]
            root_id = units["ESS"]["id"]
            root_post_id = conn.execute(
                """
                INSERT INTO team_posts(user_id, kind, title, category, status, pinned, view_count, content, org_unit_id, updated_at, created_at)
                VALUES(?, 'comment', 'ESS 内部主题', 'general', 'open', 0, 0, '仅 ESS 范围可见', ?, ?, ?)
                """,
                (admin_id, root_id, app.now_iso(), app.now_iso()),
            ).lastrowid
            root_announcement_id = conn.execute(
                """
                INSERT INTO team_posts(user_id, kind, title, category, status, pinned, view_count, content, org_unit_id, updated_at, created_at)
                VALUES(?, 'comment', 'ESS 上级公告', 'announcement', 'open', 1, 0, '需要向下级团队透传', ?, ?, ?)
                """,
                (admin_id, root_id, app.now_iso(), app.now_iso()),
            ).lastrowid
            root_morning_id = conn.execute(
                """
                INSERT INTO morning_items(owner_id, item_date, title, detail, status, priority, blocker, due_date, updated_by, created_at, updated_at, active)
                VALUES(?, ?, 'ESS 内部事项', '', 'doing', 'normal', '', ?, ?, ?, ?, 1)
                """,
                (admin_id, app.today_iso(), app.today_iso(), admin_id, app.now_iso(), app.now_iso()),
            ).lastrowid
            conn.execute("UPDATE morning_items SET root_id=? WHERE id=?", (root_morning_id, root_morning_id))
            root_meeting_id = conn.execute(
                """
                INSERT INTO meetings(meeting_date, title, summary, status, created_by, org_unit_id, created_at)
                VALUES(?, 'ESS 内部会议', '', 'draft', ?, ?, ?)
                """,
                (app.today_iso(), admin_id, root_id, app.now_iso()),
            ).lastrowid
            matched = app.match_sso_org_unit(conn, ["ORG-WS"])
            if not matched or matched["id"] != ws["id"]:
                raise RuntimeError("SSO group did not resolve to the deepest organization")

        server = ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base_url = f"http://127.0.0.1:{server.server_port}"
        try:
            opener = build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()))
            login = request_json(opener, base_url, "/api/login", "POST", {"username": "user", "password": "user123"})
            if login.get("organization", {}).get("selected", {}).get("name") != "MO":
                raise RuntimeError(f"MO login route was not selected: {login}")
            members = request_json(opener, base_url, "/api/members", org_path="ess/mo").get("members") or []
            member_names = {item["name"] for item in members}
            if "示例成员" not in member_names or "WS成员" not in member_names or "管理员" in member_names:
                raise RuntimeError(f"MO subtree visibility failed: {member_names}")
            ws_members = request_json(opener, base_url, "/api/members", org_path="ess/mo/ws").get("members") or []
            if {item["name"] for item in ws_members} != {"WS成员"}:
                raise RuntimeError(f"WS unit visibility failed: {ws_members}")
            dashboard = request_json(
                opener,
                base_url,
                f"/api/dashboards/thank-you?from={app.week_start(app.today_iso())}&to={app.week_start(app.today_iso())}",
                org_path="ess/mo/ws",
            )
            if dashboard.get("stars") or dashboard.get("weekly"):
                raise RuntimeError(f"Cross-level Thank You leaked into current-level ranking: {dashboard}")
            mo_posts = request_json(opener, base_url, "/api/team-posts", org_path="ess/mo").get("posts") or []
            inherited_announcement = next((item for item in mo_posts if item["id"] == root_announcement_id), None)
            if not inherited_announcement or not inherited_announcement.get("inherited"):
                raise RuntimeError(f"Upper announcement did not propagate to MO: {mo_posts}")
            mo_meetings = request_json(
                opener,
                base_url,
                f"/api/meetings?from={app.today_iso()}&to={app.today_iso()}",
                org_path="ess/mo",
            ).get("meetings") or []
            inherited_meeting = next((item for item in mo_meetings if item["id"] == root_meeting_id), None)
            if not inherited_meeting or not inherited_meeting.get("inherited"):
                raise RuntimeError(f"Upper meeting did not propagate to MO: {mo_meetings}")
            mo_morning = request_json(
                opener,
                base_url,
                f"/api/morning-items?date={app.today_iso()}",
                org_path="ess/mo",
            )
            if {item["id"] for item in mo_morning.get("users") or []} != {user_id}:
                raise RuntimeError(f"MO morning list leaked another organization level: {mo_morning.get('users')}")
            mo_shifts = request_json(
                opener,
                base_url,
                f"/api/shifts?from={app.today_iso()}&to={app.today_iso()}",
                org_path="ess/mo",
            )
            if {item["id"] for item in mo_shifts.get("users") or []} != {user_id}:
                raise RuntimeError(f"MO shift picker leaked another organization level: {mo_shifts.get('users')}")
            mo_meeting_payload = request_json(
                opener,
                base_url,
                f"/api/meetings?from={app.today_iso()}&to={app.today_iso()}",
                org_path="ess/mo",
            )
            if {item["id"] for item in mo_meeting_payload.get("attendance_users") or []} != {user_id}:
                raise RuntimeError(
                    f"MO attendance list leaked another organization level: {mo_meeting_payload.get('attendance_users')}"
                )
            mo_rule_dashboard = request_json(
                opener,
                base_url,
                f"/api/dashboards/red-black?from={app.today_iso()}&to={app.today_iso()}",
                org_path="ess/mo",
            )
            if {item["id"] for item in mo_rule_dashboard.get("annual") or []} != {user_id}:
                raise RuntimeError(f"MO red-black list leaked another organization level: {mo_rule_dashboard.get('annual')}")
            for path in (
                f"/api/scores?from={app.today_iso()}&to={app.today_iso()}",
                f"/api/dashboards/shifts?from={app.today_iso()}&to={app.today_iso()}",
                "/api/team-posts",
            ):
                request_json(opener, base_url, path, org_path="ess/mo")
            expect_http_status(opener, base_url, f"/api/team-posts/{root_post_id}", 404, org_path="ess/mo")
            request_json(opener, base_url, f"/api/team-posts/{root_announcement_id}", org_path="ess/mo")
            expect_http_status(opener, base_url, f"/api/morning-items/{root_morning_id}/history", 404, org_path="ess/mo")
            expect_http_status(
                opener,
                base_url,
                f"/api/meetings/{root_meeting_id}/items",
                404,
                "POST",
                {"title": "越权议题"},
                "ess/mo",
            )
            ws_opener = build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()))
            request_json(ws_opener, base_url, "/api/login", "POST", {"username": "ws-user", "password": "ws123456"})
            ws_thanks = request_json(
                ws_opener,
                base_url,
                f"/api/thank-you?from={app.week_start(app.today_iso())}&to={app.week_start(app.today_iso())}",
                org_path="ess/mo/ws",
            )
            if cross_vote_id in {item["id"] for item in ws_thanks.get("votes") or []}:
                raise RuntimeError(f"Cross-team Thank You leaked into sender team: {ws_thanks}")
            if rs_user_id in {item["id"] for item in ws_thanks.get("users") or []}:
                raise RuntimeError(f"Cross-team recipient leaked into current-level picker: {ws_thanks.get('users')}")
            morning_before = request_json(
                ws_opener,
                base_url,
                f"/api/morning-items?date={app.today_iso()}",
                org_path="ess/mo/ws",
            )
            if {item["id"] for item in morning_before.get("users") or []} != {ws_user_id}:
                raise RuntimeError(f"Morning participants were not limited to the current level: {morning_before.get('users')}")
            version_before = morning_before.get("version_token")
            request_json(
                ws_opener,
                base_url,
                "/api/morning-items",
                "POST",
                {"title": "WS 当日事项", "item_date": app.today_iso(), "status": "doing"},
                "ess/mo/ws",
            )
            version_after = request_json(
                ws_opener,
                base_url,
                f"/api/morning-items/version?date={app.today_iso()}",
                org_path="ess/mo/ws",
            ).get("version_token")
            if not version_before or version_before == version_after:
                raise RuntimeError("Morning lightweight version did not change after an update")
            request_json(
                ws_opener,
                base_url,
                f"/api/team-posts/{root_announcement_id}/replies",
                "POST",
                {"content": "下级团队已收到上级公告"},
                "ess/mo/ws",
            )
            ws_dashboard = request_json(
                ws_opener,
                base_url,
                f"/api/dashboards/thank-you?from={app.week_start(app.today_iso())}&to={app.week_start(app.today_iso())}",
                org_path="ess/mo/ws",
            )
            if "RS成员" in {item["display_name"] for item in ws_dashboard.get("stars") or []}:
                raise RuntimeError(f"Cross-team recipient leaked into sender team ranking: {ws_dashboard}")
            rs_opener = build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()))
            request_json(rs_opener, base_url, "/api/login", "POST", {"username": "rs-user", "password": "rs123456"})
            rs_thanks = request_json(
                rs_opener,
                base_url,
                f"/api/thank-you?from={app.week_start(app.today_iso())}&to={app.week_start(app.today_iso())}",
                org_path="ess/mo/rs",
            )
            if cross_vote_id in {item["id"] for item in rs_thanks.get("votes") or []}:
                raise RuntimeError(f"Cross-team Thank You leaked into receiver team: {rs_thanks}")
            with opener.open(f"{base_url}/org/ess/mo/ws", timeout=15) as response:
                if b'id="appView"' not in response.read():
                    raise RuntimeError("Organization route did not serve the SPA")
            admin_opener = build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()))
            request_json(admin_opener, base_url, "/api/login", "POST", {"username": "admin", "password": "admin123"})
            sortable_members = request_json(
                admin_opener,
                base_url,
                "/api/members",
                org_path="ess/mo",
            ).get("members") or []
            reversed_member_ids = [item["id"] for item in reversed(sortable_members)]
            reordered_members = request_json(
                admin_opener,
                base_url,
                "/api/members/order",
                "PATCH",
                {"member_ids": reversed_member_ids},
                "ess/mo",
            ).get("members") or []
            if [item["id"] for item in reordered_members] != reversed_member_ids:
                raise RuntimeError(f"Organization-scoped member sorting failed: {reordered_members}")
            reordered_morning = request_json(
                admin_opener,
                base_url,
                "/api/morning-items/order",
                "PATCH",
                {"user_ids": [user_id], "date": app.today_iso()},
                "ess/mo",
            )
            if [item["id"] for item in reordered_morning.get("users") or []] != [user_id]:
                raise RuntimeError(f"Organization-scoped morning sorting failed: {reordered_morning.get('users')}")
            topic_types = request_json(
                admin_opener,
                base_url,
                "/api/meeting-topics",
                org_path="ess/mo",
            ).get("types") or []
            if topic_types:
                option_result = request_json(
                    admin_opener,
                    base_url,
                    "/api/meeting-topic-options",
                    "POST",
                    {
                        "type_id": topic_types[0]["id"],
                        "title": "上层会议协调下级责任人",
                        "owner_id": ws_user_id,
                    },
                    "ess/mo",
                )
                created_option = next(
                    option
                    for topic in option_result.get("types") or []
                    for option in topic.get("options") or []
                    if option.get("title") == "上层会议协调下级责任人"
                )
                if created_option.get("owner_id") != ws_user_id:
                    raise RuntimeError(f"Descendant meeting owner was not retained: {created_option}")
            coordination_users = request_json(
                admin_opener,
                base_url,
                "/api/users/coordination",
                org_path="ess/mo",
            ).get("users") or []
            coordination_ids = {item["id"] for item in coordination_users}
            if not {user_id, ws_user_id, rs_user_id}.issubset(coordination_ids):
                raise RuntimeError(f"Parent coordination list missed descendants: {coordination_users}")
            ws_topic_ids = {
                item["id"]
                for item in request_json(
                    admin_opener, base_url, "/api/meeting-topics", org_path="ess/mo/ws"
                ).get("types") or []
            }
            if ws_topic_ids.intersection({item["id"] for item in topic_types}):
                raise RuntimeError("Meeting topic libraries leaked across teams")
            mo_machines = request_json(
                admin_opener,
                base_url,
                "/api/machines",
                "POST",
                {"name": "MO 专属机台"},
                "ess/mo",
            )["machines"]
            mo_machine = next(item for item in mo_machines if item["name"] == "MO 专属机台")
            ws_machine_ids = {
                item["id"]
                for item in request_json(
                    admin_opener, base_url, "/api/machines", org_path="ess/mo/ws"
                ).get("machines") or []
            }
            if mo_machine["id"] in ws_machine_ids:
                raise RuntimeError("Machine configuration leaked into a child team")
            root_moment = request_json(
                admin_opener,
                base_url,
                "/api/team-moments",
                "POST",
                {
                    "title": "ESS 上层关键时刻",
                    "story": "仅在上层团队展示，不向下透传。",
                    "category": "milestone",
                    "event_date": app.today_iso(),
                    "images": [],
                },
                "ess",
            )
            root_moment_id = next(
                item["id"] for item in root_moment.get("moments") or [] if item["title"] == "ESS 上层关键时刻"
            )
            mo_moments = request_json(
                admin_opener, base_url, "/api/team-moments", org_path="ess/mo"
            ).get("moments") or []
            if root_moment_id in {item["id"] for item in mo_moments}:
                raise RuntimeError("Upper-level team moment propagated into a child team")
            unrelated_thanks = request_json(
                admin_opener,
                base_url,
                f"/api/thank-you?from={app.week_start(app.today_iso())}&to={app.week_start(app.today_iso())}",
                org_path="ess/mo/wh",
            )
            if cross_vote_id in {item["id"] for item in unrelated_thanks.get("votes") or []}:
                raise RuntimeError(f"Cross-team Thank You leaked into unrelated sibling team: {unrelated_thanks}")
            created = request_json(
                admin_opener,
                base_url,
                "/api/org-units",
                "POST",
                {"name": "TMP", "slug": "tmp", "parent_id": units["ESS"]["id"], "visibility_mode": "unit", "default_user_type": app.DEFAULT_USER_TYPE_KEY, "sso_groups": ["TMP-GROUP"]},
                "ess",
            )
            temporary = next(item for item in created.get("units") or [] if item["name"] == "TMP")
            request_json(admin_opener, base_url, f"/api/org-units/{temporary['id']}", "PATCH", {"name": "TMP2", "slug": "tmp2"}, "ess")
            request_json(admin_opener, base_url, f"/api/org-units/{temporary['id']}", "DELETE", org_path="ess")
            print(json.dumps({"status": "ok", "mo_members": sorted(member_names), "member_drag_order": True, "current_level_scope": True, "team_owned_configuration_isolated": True, "descendant_coordination": True, "cross_team_vote_hidden": cross_vote_id, "morning_version_refresh": True, "inherited_announcement": root_announcement_id, "route": "/org/ess/mo/ws"}, ensure_ascii=False))
        finally:
            server.shutdown()
            thread.join(timeout=5)
            server.server_close()


if __name__ == "__main__":
    main()
