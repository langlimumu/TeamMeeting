"""环境管理模块的隔离冒烟测试：卡片台账、占用、交接、释放、占用记录与权限边界。

用法：python scripts/environments_smoke_test.py
"""

import argparse
import datetime as dt
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


def start_server(handler):
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def request_json(opener, url, method="GET", payload=None, expected=200):
    body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = Request(
        url,
        data=body,
        headers={"Connection": "close", **({"Content-Type": "application/json"} if body is not None else {})},
        method=method,
    )
    try:
        with opener.open(request, timeout=20) as response:
            status = response.status
            data = json.load(response)
    except HTTPError as exc:
        status = exc.code
        data = json.loads(exc.read().decode("utf-8"))
    if status != expected:
        raise RuntimeError(f"{method} {url} returned {status}, expected {expected}: {data}")
    return data


def login(base_url, username, password):
    opener = build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()))
    request_json(opener, f"{base_url}/api/login", "POST", {"username": username, "password": password})
    return opener


def find_environment(environments, name):
    return next((item for item in environments if item.get("name") == name), None)


def main():
    parser = argparse.ArgumentParser(description="Run an isolated environment ledger integration smoke test")
    parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="team-loop-envs-") as temporary_directory:
        os.environ["TEAM_LOOP_DB_PATH"] = str(Path(temporary_directory) / "environments-smoke.db")
        os.environ["TEAM_LOOP_DATA_DIR"] = temporary_directory
        os.environ["TEAM_LOOP_BACKUP_DIR"] = str(Path(temporary_directory) / "backups")
        os.environ["TEAM_LOOP_ENV"] = "gray"
        sys.path.insert(0, str(ROOT))
        import server as app

        app.init_db()
        server, thread = start_server(app.Handler)
        base_url = f"http://127.0.0.1:{server.server_port}"
        try:
            admin = login(base_url, "admin", "admin123")
            member = login(base_url, "user", "user123")
            guest = build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()))

            # ---- 访客连看都看不到：这一列是服务器密码，不给未登录的人 ----
            request_json(guest, f"{base_url}/api/environments", expected=403)

            # ---- 台账为空 ----
            empty = request_json(admin, f"{base_url}/api/environments")
            if empty["environments"] or empty["summary"]["total"]:
                raise RuntimeError(f"A fresh ledger must be empty: {empty}")

            # ---- 新增：管理员可以，普通成员不行 ----
            created = request_json(admin, f"{base_url}/api/environments", "POST", {
                "name": "dev-01",
                "host": "192.168.10.21",
                "username": "team",
                "password": "P@ssw0rd-01",
                "vnc_port": 5901,
                "purpose": "日常联调，需先连 VPN",
            })
            environments = created["environments"]
            if len(environments) != 1 or created["summary"]["free"] != 1:
                raise RuntimeError(f"A new environment must show as free: {created}")
            dev = environments[0]
            if dev["occupied"] or dev["is_mine"]:
                raise RuntimeError(f"A fresh environment must be free and unowned: {dev}")
            # 密码按团队要求明文下发（内部台账，卡片上直接读凭据是常态）。
            if dev["password"] != "P@ssw0rd-01" or dev["vnc_port"] != 5901:
                raise RuntimeError(f"Credentials must round-trip: {dev}")

            request_json(member, f"{base_url}/api/environments", "POST", {
                "name": "成员想加的环境", "host": "192.168.10.99", "username": "team",
            }, 403)

            # 重名与非法值都要挡在库里之外。
            request_json(admin, f"{base_url}/api/environments", "POST", {
                "name": "dev-01", "host": "192.168.10.22", "username": "team",
            }, 409)
            request_json(admin, f"{base_url}/api/environments", "POST", {"name": "", "host": "1.1.1.1", "username": "t"}, 400)
            request_json(admin, f"{base_url}/api/environments", "POST", {"name": "无主机名", "host": "  ", "username": "t"}, 400)
            request_json(admin, f"{base_url}/api/environments", "POST", {"name": "带空格的IP", "host": "192.168.1 1", "username": "t"}, 400)
            request_json(admin, f"{base_url}/api/environments", "POST", {"name": "端口越界", "host": "1.1.1.1", "username": "t", "vnc_port": 70000}, 400)
            request_json(admin, f"{base_url}/api/environments", "POST", {"name": "端口非数字", "host": "1.1.1.1", "username": "t", "vnc_port": "abc"}, 400)

            request_json(admin, f"{base_url}/api/environments", "POST", {
                "name": "test-02", "host": "192.168.10.22", "username": "qa", "vnc_port": 5902,
            })

            # **台账的增 / 改 / 删只有管理员**：普通成员三条路全 403，且默认用户类型在
            # environments 上只有 view（create/edit/delete 都是 0），前端因此也不画按钮。
            request_json(member, f"{base_url}/api/environments", "POST", {
                "name": "成员建的环境", "host": "192.168.10.98", "username": "team",
            }, 403)
            request_json(member, f"{base_url}/api/environments/{dev['id']}", "PATCH", {
                "host": "10.0.0.1",
            }, 403)
            request_json(member, f"{base_url}/api/environments/{dev['id']}", "DELETE", expected=403)
            # 默认用户类型在 environments 上只留 view —— 占用/释放靠的就是这个 view。
            member_operations = request_json(member, f"{base_url}/api/me")["permissions"]["operations"]["environments"]
            if member_operations != {"view": True, "create": False, "edit": False, "delete": False}:
                raise RuntimeError(f"The default user type must only view environments: {member_operations}")
            # 但 view 归他，所以卡片和占用记录读得到（这一条同时守住 #1 与 #2 的前提）。
            if not any(item["name"] == "dev-01" for item in request_json(member, f"{base_url}/api/environments")["environments"]):
                raise RuntimeError("A member must still be able to read the ledger")

            # ---- 占用：一键占自己，可填预计归还（精确到秒）与备注 ----
            occupied = request_json(member, f"{base_url}/api/environments/{dev['id']}/occupy", "POST", {
                "expected_return_at": "2099-12-31T18:30:45", "note": "跑联调脚本",
            })
            dev = find_environment(occupied["environments"], "dev-01")
            if not dev["occupied"] or not dev["is_mine"] or not dev["holder_name"]:
                raise RuntimeError(f"Occupying must record the caller as the holder: {dev}")
            if dev["occupancy_note"] != "跑联调脚本":
                raise RuntimeError(f"Occupying must keep the note: {dev}")
            # 时刻必须原样存住（时分秒不能被截成日期）。
            if dev["expected_return_at"] != "2099-12-31T18:30:45":
                raise RuntimeError(f"The expected return must keep hour, minute and second: {dev}")
            if occupied["summary"]["occupied"] != 1 or occupied["summary"]["mine"] != 1:
                raise RuntimeError(f"The summary must count the occupancy: {occupied['summary']}")

            # 裸日期仍然接受，按「当天 23:59:59」解释（与前端的 environmentExpectedMoment 同口径）。
            request_json(admin, f"{base_url}/api/environments", "POST", {
                "name": "date-only", "host": "192.168.10.30", "username": "qa",
            })
            date_only = find_environment(
                request_json(member, f"{base_url}/api/environments")["environments"], "date-only"
            )
            request_json(member, f"{base_url}/api/environments/{date_only['id']}/occupy", "POST", {
                "expected_return_at": "2099-06-01",
            })
            date_only = find_environment(
                request_json(member, f"{base_url}/api/environments")["environments"], "date-only"
            )
            if date_only["expected_return_at"] != "2099-06-01T23:59:59":
                raise RuntimeError(f"A bare date must mean the end of that day: {date_only}")

            # 真的过了归还时刻 → summary.overdue 必须算进去（按时刻比，不是按日期比）。
            past = (dt.datetime.now() - dt.timedelta(hours=2)).replace(microsecond=0).isoformat()
            request_json(member, f"{base_url}/api/environments/{date_only['id']}/occupy", "POST", {
                "expected_return_at": past,
            }, 409)
            future = (dt.datetime.now() + dt.timedelta(days=365)).replace(microsecond=0).isoformat()
            request_json(member, f"{base_url}/api/environments/{date_only['id']}/release", "POST")
            reoccupied = request_json(member, f"{base_url}/api/environments/{date_only['id']}/occupy", "POST", {
                "expected_return_at": past,
            })
            if reoccupied["summary"]["overdue"] != 1:
                raise RuntimeError(f"A past timestamp must count as overdue: {reoccupied['summary']}")
            request_json(member, f"{base_url}/api/environments/{date_only['id']}/occupy", "POST", {
                "expected_return_at": future,
            }, 409)
            request_json(member, f"{base_url}/api/environments/{date_only['id']}/release", "POST")
            request_json(admin, f"{base_url}/api/environments/{date_only['id']}", "DELETE")

            # 格式非法的时刻 → 400。
            request_json(member, f"{base_url}/api/environments/{dev['id']}/occupy", "POST", {
                "expected_return_at": "not-a-date",
            }, 400)

            # 重复占自己这台 → 409（否则会写出一段自相矛盾的记录）。
            request_json(member, f"{base_url}/api/environments/{dev['id']}/occupy", "POST", {}, 409)
            request_json(member, f"{base_url}/api/environments/{dev['id']}/occupy", "POST", {
                "expected_return_at": "not-a-date",
            }, 400)

            # ---- 释放：占用人能释放自己的；释放别人的只有管理员可以 ----
            # 此刻 member 正占着这台（上面那一步占的），所以先由他本人释放。
            released = request_json(member, f"{base_url}/api/environments/{dev['id']}/release", "POST")
            dev = find_environment(released["environments"], "dev-01")
            if dev["occupied"] or dev["holder_name"] or dev["expected_return_at"]:
                raise RuntimeError(f"Releasing must clear the holder: {dev}")
            # 已经空闲了还点释放 → 409，不要静默成功。
            request_json(member, f"{base_url}/api/environments/{dev['id']}/release", "POST", {}, 409)

            # 现在空了：管理员占上，然后让普通成员去释放**别人的**占用 → 403。
            request_json(admin, f"{base_url}/api/environments/{dev['id']}/occupy", "POST", {})
            request_json(member, f"{base_url}/api/environments/{dev['id']}/release", "POST", expected=403)
            released = request_json(admin, f"{base_url}/api/environments/{dev['id']}/release", "POST")
            dev = find_environment(released["environments"], "dev-01")
            if dev["occupied"]:
                raise RuntimeError(f"An admin must be able to release someone else's hold: {dev}")

            # ---- 不能强行接管：别人占着就占不上，必须先由占用人释放 ----
            request_json(member, f"{base_url}/api/environments/{dev['id']}/occupy", "POST", {"note": "第一段"})
            usages_before_takeover = request_json(member, f"{base_url}/api/environments/{dev['id']}")["usages"]
            # 管理员也一样：强行接管是 409，不是「谁都能覆盖」。
            try:
                request_json(admin, f"{base_url}/api/environments/{dev['id']}/occupy", "POST", {"note": "第二段"})
                raise RuntimeError("Occupying an occupied environment must be refused, even for an admin")
            except RuntimeError as exc:
                if "must be refused" in str(exc):
                    raise
                if "占用" not in str(exc):
                    raise RuntimeError(f"The refusal must name the holder: {exc}")
            # 被拒之后状态一点没动：还是 member 占用，管理员没抢到，也没多出记录。
            member_view = find_environment(
                request_json(member, f"{base_url}/api/environments")["environments"], "dev-01"
            )
            if not member_view["is_mine"] or member_view["occupancy_note"] != "第一段":
                raise RuntimeError(f"A refused takeover must leave the state untouched: {member_view}")
            if len(request_json(admin, f"{base_url}/api/environments/{dev['id']}")["usages"]) != len(usages_before_takeover):
                raise RuntimeError("A refused takeover must not write a usage row")

            # 正常路径：占用人自己释放 → 机器回到空闲 → 别人才能占。
            released = request_json(member, f"{base_url}/api/environments/{dev['id']}/release", "POST")
            dev = find_environment(released["environments"], "dev-01")
            if dev["occupied"]:
                raise RuntimeError(f"The holder must be able to release: {dev}")
            handover = request_json(admin, f"{base_url}/api/environments/{dev['id']}/occupy", "POST", {"note": "第二段"})
            dev = find_environment(handover["environments"], "dev-01")
            if not dev["is_mine"] or dev["occupancy_note"] != "第二段" or dev["expected_return_at"]:
                raise RuntimeError(f"A freed environment must be claimable: {dev}")
            if handover["summary"]["occupied"] != 1 or handover["summary"]["free"] != 1:
                raise RuntimeError(f"The summary must follow the new holder: {handover['summary']}")
            # is_mine 是相对调用者的：从原占用人（member）视角看，这台机器已经交出去了。
            member_view = find_environment(
                request_json(member, f"{base_url}/api/environments")["environments"], "dev-01"
            )
            if member_view["is_mine"] or not member_view["occupied"]:
                raise RuntimeError(f"The previous holder must see it released: {member_view}")

            # 这一对记录：第一段（释放）当场收口，第二段仍进行中。
            # 前面几步也已经留下记录，所以按 notes 定位这一对，不按条数。
            detail = request_json(member, f"{base_url}/api/environments/{dev['id']}")
            handover_rows = {row["note"]: row for row in detail["usages"] if row["note"] in ("第一段", "第二段")}
            if set(handover_rows) != {"第一段", "第二段"}:
                raise RuntimeError(f"Both occupancy segments must be recorded: {detail['usages']}")
            if not handover_rows["第一段"]["released_at"]:
                raise RuntimeError(f"The released segment must be closed: {handover_rows['第一段']}")
            if handover_rows["第二段"]["released_at"]:
                raise RuntimeError(f"The current segment must stay open: {handover_rows['第二段']}")
            open_rows = [row for row in detail["usages"] if not row["released_at"]]
            if len(open_rows) != 1 or open_rows[0]["note"] != "第二段":
                raise RuntimeError(f"Exactly one segment may stay open: {detail['usages']}")
            if handover_rows["第一段"]["user_name"] == handover_rows["第二段"]["user_name"]:
                raise RuntimeError(f"The two segments must belong to different people: {detail['usages']}")

            # 管理员可以代为释放别人的占用；普通成员不行。
            request_json(member, f"{base_url}/api/environments/{dev['id']}/release", "POST", expected=403)
            released = request_json(admin, f"{base_url}/api/environments/{dev['id']}/release", "POST")
            dev = find_environment(released["environments"], "dev-01")
            if dev["occupied"]:
                raise RuntimeError(f"An admin must be able to free someone else's hold: {dev}")
            after_release = request_json(admin, f"{base_url}/api/environments/{dev['id']}")["usages"]
            if any(row["released_at"] is None for row in after_release):
                raise RuntimeError(f"Releasing must close the open segment, not leave it dangling: {after_release}")
            if len(after_release) != len(detail["usages"]):
                raise RuntimeError("Releasing must not add a usage row")

            # ---- 编辑：改密码留空表示不动 ----
            request_json(admin, f"{base_url}/api/environments/{dev['id']}", "PATCH", {
                "name": "dev-01（改造）", "purpose": "已扩容到 64G",
            })
            dev = find_environment(request_json(admin, f"{base_url}/api/environments")["environments"], "dev-01（改造）")
            if dev["password"] != "P@ssw0rd-01" or dev["host"] != "192.168.10.21" or dev["purpose"] != "已扩容到 64G":
                raise RuntimeError(f"A partial PATCH must keep the fields it did not carry: {dev}")
            request_json(admin, f"{base_url}/api/environments/{dev['id']}", "PATCH", {"password": "New-P@ss-02"})
            dev = find_environment(request_json(admin, f"{base_url}/api/environments")["environments"], "dev-01（改造）")
            if dev["password"] != "New-P@ss-02":
                raise RuntimeError(f"An explicit password must overwrite the old one: {dev}")
            # 改名撞上另一台 → 409。
            request_json(admin, f"{base_url}/api/environments/{dev['id']}", "PATCH", {"name": "test-02"}, 409)
            # 成员改不动台账。
            request_json(member, f"{base_url}/api/environments/{dev['id']}", "PATCH", {"host": "10.0.0.1"}, 403)

            # ---- 删除：成员无权删除；有人占用时管理员也必须先交接/释放 ----
            # 占用中：管理员直接删 → 409（不是静默删掉一台别人正用着的机器）。
            request_json(member, f"{base_url}/api/environments/{dev['id']}/occupy", "POST", {})
            request_json(admin, f"{base_url}/api/environments/{dev['id']}", "DELETE", expected=409)
            # 成员即使是自己占的，也删不了台账（只有管理员能增删改）。
            request_json(member, f"{base_url}/api/environments/{dev['id']}", "DELETE", expected=403)
            request_json(member, f"{base_url}/api/environments/{dev['id']}/release", "POST")

            # 软删除 → 回收站可恢复；恢复时占用状态一并清空（占用人可能早换了）。
            # 删掉之后这台机器就查不到了（404），所以历史条数必须在删之前记下来。
            history_before_delete = len(
                request_json(admin, f"{base_url}/api/environments/{dev['id']}")["usages"]
            )
            deleted = request_json(admin, f"{base_url}/api/environments/{dev['id']}", "DELETE")
            if find_environment(deleted["environments"], "dev-01（改造）"):
                raise RuntimeError(f"A deleted environment must leave the wall: {deleted}")
            if deleted["summary"]["total"] != 1:
                raise RuntimeError(f"The summary must drop the deleted row: {deleted['summary']}")
            request_json(admin, f"{base_url}/api/environments/{dev['id']}", expected=404)

            recycle = request_json(admin, f"{base_url}/api/recycle-bin")["items"]
            env_row = next((item for item in recycle if item["entity_type"] == "environment"), None)
            if not env_row or env_row["entity_label"] != "环境":
                raise RuntimeError(f"A deleted environment must reach the recycle bin: {recycle}")
            request_json(admin, f"{base_url}/api/recycle-bin/{env_row['id']}/restore", "POST")
            restored = find_environment(request_json(admin, f"{base_url}/api/environments")["environments"], "dev-01（改造）")
            if not restored:
                raise RuntimeError("Restoring must bring the environment back")
            if restored["occupied"] or restored["holder_name"]:
                raise RuntimeError(f"Restoring must not resurrect a stale occupancy: {restored}")
            # 占用历史一段都不能少（恢复只清当前占用，不碰历史）。
            if len(request_json(admin, f"{base_url}/api/environments/{dev['id']}")["usages"]) != history_before_delete:
                raise RuntimeError("Restoring must keep the occupancy history")

            # 跨团队不可见：不存在的 id 一律 404，而不是把别的团队的数据漏出去。
            request_json(admin, f"{base_url}/api/environments/999999", expected=404)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    print(
        "环境管理冒烟测试通过：台账增删改仅管理员（成员一律 403）、重名与非法 host/端口 400、"
        "密码明文下发与「留空不改」、一键占用空闲机器、**预计归还精确到秒且裸日期按当天 23:59:59、"
        "过了时刻计入 overdue**、只能释放自己的占用（管理员可代释）、"
        "**别人在用时强行占用被拒（管理员也不例外）且状态零改动**、占用中有占用不许删除、"
        "软删除进回收站并恢复（清占用但保历史）、访客完全不可见均符合预期。"
    )


if __name__ == "__main__":
    main()