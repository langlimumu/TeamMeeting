import http.cookiejar
import json
import os
import sys
import tempfile
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor, Request, build_opener


ROOT = Path(__file__).resolve().parents[1]


def request_json(opener, base_url, path, method="GET", payload=None, org_path=""):
    headers = {"Content-Type": "application/json", "Connection": "close"}
    if org_path:
        headers["X-Team-Org-Path"] = org_path
    request = Request(
        f"{base_url}{path}",
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


def expect_status(opener, base_url, path, status, method="GET", payload=None, org_path=""):
    headers = {"Content-Type": "application/json", "Connection": "close"}
    if org_path:
        headers["X-Team-Org-Path"] = org_path
    request = Request(
        f"{base_url}{path}",
        data=json.dumps(payload).encode("utf-8") if payload is not None else None,
        headers=headers,
        method=method,
    )
    try:
        opener.open(request, timeout=15).close()
    except ConnectionResetError:
        # Python 3.14 on Windows can surface the server's deliberate close on
        # rejected requests as WSAECONNRESET; later state assertions still
        # verify that the rejected mutation was not applied.
        if status in (403, 409):
            return
        raise
    except HTTPError as error:
        if error.code == status:
            return
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {path} returned {error.code}, expected {status}: {detail}") from error
    raise RuntimeError(f"{method} {path} returned success, expected {status}")


def main():
    with tempfile.TemporaryDirectory(prefix="team-loop-process-") as temporary_directory:
        os.environ["TEAM_LOOP_DB_PATH"] = str(Path(temporary_directory) / "process-smoke.db")
        os.environ["TEAM_LOOP_DATA_DIR"] = temporary_directory
        os.environ["TEAM_LOOP_BACKUP_DIR"] = str(Path(temporary_directory) / "backups")
        os.environ["TEAM_LOOP_ENV"] = "gray"
        sys.path.insert(0, str(ROOT))
        import server as app

        app.init_db()
        with app.connect() as conn:
            mo_id = conn.execute("SELECT id FROM org_units WHERE name='MO'").fetchone()[0]
            conn.execute("UPDATE users SET org_unit_id=? WHERE username='user'", (mo_id,))

        server = ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base_url = f"http://127.0.0.1:{server.server_port}"
        try:
            admin = build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()))
            request_json(admin, base_url, "/api/login", "POST", {"username": "admin", "password": "admin123"})
            created = request_json(
                admin,
                base_url,
                "/api/process-templates",
                "POST",
                {
                    "name": "夜班交接流程",
                    "description": "确保信息、现场和异常完成交接",
                    "items": [
                        {
                            "key": "check",
                            "parent_key": "",
                            "title": "确认点检记录",
                            "description": "点检表已填写完整",
                            "required": True,
                        },
                        {
                            "key": "sync",
                            "parent_key": "check",
                            "title": "同步未闭环异常",
                            "description": "说明责任人与下一步",
                            "required": True,
                        },
                    ],
                },
                "ess",
            )
            template = created["templates"][0]

            user = build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()))
            request_json(user, base_url, "/api/login", "POST", {"username": "user", "password": "user123"})
            templates = request_json(user, base_url, "/api/process-templates", org_path="ess/mo")["templates"]
            inherited = next((item for item in templates if item["id"] == template["id"]), None)
            if not inherited or not inherited["inherited"]:
                raise RuntimeError(f"Upper-level process template did not propagate: {templates}")
            member_created = request_json(
                user,
                base_url,
                "/api/process-templates",
                "POST",
                {
                    "name": "成员自建复盘流程",
                    "description": "验证所有登录成员都能沉淀当前团队流程模板",
                    "items": [{"key": "review", "title": "完成复盘记录", "required": True}],
                },
                "ess/mo",
            )
            member_template = next(
                item for item in member_created["templates"] if item["name"] == "成员自建复盘流程"
            )
            if not member_template.get("can_manage") or member_template.get("inherited"):
                raise RuntimeError(f"Member-created template ownership is invalid: {member_template}")

            generated = request_json(
                user,
                base_url,
                "/api/process-instances",
                "POST",
                {"template_id": template["id"], "title": "7 月夜班交接", "due_date": app.today_iso()},
                "ess/mo",
            )
            instance = generated["instances"][0]
            if len(instance["items"]) != 2 or instance["progress"] != 0:
                raise RuntimeError(f"Process instance snapshot is invalid: {instance}")

            first_item, second_item = instance["items"]
            if second_item["parent_item_id"] != first_item["id"]:
                raise RuntimeError(f"Process snapshot did not preserve the tree relation: {instance}")
            expect_status(
                user,
                base_url,
                f"/api/process-instance-items/{second_item['id']}",
                409,
                "PATCH",
                {"completed": True, "expected_version": second_item["version"]},
                "ess/mo",
            )
            request_json(
                user,
                base_url,
                f"/api/process-instance-items/{first_item['id']}",
                "PATCH",
                {"completed": True, "expected_version": first_item["version"]},
                "ess/mo",
            )
            active = request_json(
                user,
                base_url,
                "/api/process-instances?scope=mine&status=active",
                org_path="ess/mo",
            )["instances"][0]
            if active["progress"] != 50 or active["status"] != "active":
                raise RuntimeError(f"Partial progress did not remain active: {active}")

            request_json(
                user,
                base_url,
                f"/api/process-instance-items/{second_item['id']}",
                "PATCH",
                {"completed": True, "expected_version": second_item["version"]},
                "ess/mo",
            )
            completed = request_json(
                user,
                base_url,
                "/api/process-instances?scope=mine&status=completed",
                org_path="ess/mo",
            )["instances"][0]
            if completed["progress"] != 100 or completed["status"] != "completed":
                raise RuntimeError(f"Completed process did not close automatically: {completed}")

            cascade_result = request_json(
                user,
                base_url,
                f"/api/process-instance-items/{first_item['id']}",
                "PATCH",
                {"completed": False, "expected_version": first_item["version"] + 1},
                "ess/mo",
            )
            if cascade_result.get("reset_descendants") != 1:
                raise RuntimeError(f"Unchecking a parent did not reset its descendants: {cascade_result}")
            reset_instance = request_json(
                user,
                base_url,
                "/api/process-instances?scope=mine&status=active",
                org_path="ess/mo",
            )["instances"][0]
            if reset_instance["progress"] != 0 or any(item["completed"] for item in reset_instance["items"]):
                raise RuntimeError(f"Process branch was not reset consistently: {reset_instance}")
            for reset_item in reset_instance["items"]:
                request_json(
                    user,
                    base_url,
                    f"/api/process-instance-items/{reset_item['id']}",
                    "PATCH",
                    {"completed": True, "expected_version": reset_item["version"]},
                    "ess/mo",
                )

            request_json(
                admin,
                base_url,
                f"/api/process-templates/{template['id']}",
                "PATCH",
                {
                    "name": template["name"],
                    "description": template["description"],
                    "expected_version": template["version"],
                    "items": [
                        {"key": "check", "parent_key": "", "title": "确认点检记录", "required": True},
                        {
                            "key": "sync",
                            "parent_key": "check",
                            "title": "同步未闭环异常",
                            "required": True,
                        },
                        {
                            "key": "photo",
                            "parent_key": "check",
                            "title": "上传交接照片",
                            "required": False,
                        },
                    ],
                },
                "ess",
            )
            preserved = request_json(
                user,
                base_url,
                "/api/process-instances?scope=mine&status=completed",
                org_path="ess/mo",
            )["instances"][0]
            if len(preserved["items"]) != 2:
                raise RuntimeError(f"Existing process changed after template update: {preserved}")
            if preserved["items"][1]["parent_item_id"] != preserved["items"][0]["id"]:
                raise RuntimeError(f"Existing process tree relation changed after template update: {preserved}")

            updated_template = next(
                item
                for item in request_json(
                    user,
                    base_url,
                    "/api/process-templates",
                    org_path="ess/mo",
                )["templates"]
                if item["id"] == template["id"]
            )
            optional_instance = next(
                item
                for item in request_json(
                    user,
                    base_url,
                    "/api/process-instances",
                    "POST",
                    {"template_id": updated_template["id"], "title": "含可选步骤的交接"},
                    "ess/mo",
                )["instances"]
                if item["title"] == "含可选步骤的交接"
            )
            for required_item in (item for item in optional_instance["items"] if item["required"]):
                request_json(
                    user,
                    base_url,
                    f"/api/process-instance-items/{required_item['id']}",
                    "PATCH",
                    {"completed": True, "expected_version": required_item["version"]},
                    "ess/mo",
                )
            optional_completed = next(
                item
                for item in request_json(
                    user,
                    base_url,
                    "/api/process-instances?scope=mine&status=completed",
                    org_path="ess/mo",
                )["instances"]
                if item["id"] == optional_instance["id"]
            )
            if optional_completed["progress"] != 100 or optional_completed["items"][-1]["completed"]:
                raise RuntimeError(f"Optional checklist semantics are invalid: {optional_completed}")

            team_instances = request_json(
                admin,
                base_url,
                "/api/process-instances?scope=team&status=completed",
                org_path="ess/mo",
            )["instances"]
            if instance["id"] not in {item["id"] for item in team_instances}:
                raise RuntimeError(f"Admin team process view did not include the member process: {team_instances}")

            print(json.dumps({
                "status": "ok",
                "template_inherited": inherited["inherited"],
                "snapshot_items": len(preserved["items"]),
                "progress": preserved["progress"],
                "tree_relation_preserved": True,
                "child_requires_parent": True,
                "parent_reset_cascades": True,
                "optional_item_blocks_completion": False,
                "member_template_creation": True,
                "team_visible": True,
            }, ensure_ascii=False))
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


if __name__ == "__main__":
    main()
