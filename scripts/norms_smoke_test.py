"""团队规范模块的隔离冒烟测试：分类、条目、按分类分份成文与权限边界。

用法：python scripts/norms_smoke_test.py
"""

import argparse
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


def find_norm(norms, title):
    return next((norm for norm in norms if norm.get("title") == title), None)


def documents_by_category(document):
    return {item["category_id"]: item for item in document["documents"]}


def main():
    parser = argparse.ArgumentParser(description="Run an isolated team norm integration smoke test")
    parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="team-loop-norms-") as temporary_directory:
        os.environ["TEAM_LOOP_DB_PATH"] = str(Path(temporary_directory) / "norms-smoke.db")
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

            request_json(guest, f"{base_url}/api/norms", expected=403)

            categories = request_json(admin, f"{base_url}/api/norm-categories")["categories"]
            if len(categories) != 6:
                raise RuntimeError(f"Expected 6 seeded categories, got {len(categories)}")
            first_category, second_category = categories[0], categories[1]

            empty_document = request_json(admin, f"{base_url}/api/norms/document")["document"]
            empty_documents = empty_document["documents"]
            if len(empty_documents) != 6:
                raise RuntimeError(f"Every category must own a document, got {len(empty_documents)}")
            if any(item["article_count"] for item in empty_documents):
                raise RuntimeError(f"Fresh category documents must all be empty: {empty_documents}")
            for field in ("release", "draft", "pending_changes", "version"):
                if field in empty_document:
                    raise RuntimeError(f"The document payload must not carry the version field: {field}")

            request_json(admin, f"{base_url}/api/norms/versions", expected=404)

            request_json(admin, f"{base_url}/api/norms", "POST", {
                "category_id": first_category["id"],
                "title": "提交代码前必须通过静态检查",
                "content": "本地跑通 lint 与单测后再提交。",
                "scope": "全体研发",
                "source": "2026-09 周例会决议",
                "effective_from": "2026-09-01",
            })
            request_json(admin, f"{base_url}/api/norms", "POST", {
                "category_id": first_category["id"],
                "title": "每周例会前提交上周风险清单",
            })
            request_json(admin, f"{base_url}/api/norms", "POST", {
                "category_id": second_category["id"],
                "title": "进入现场必须佩戴防护用品",
            })
            request_json(admin, f"{base_url}/api/norms", "POST", {"title": "没有分类的规则"}, 400)

            document = request_json(admin, f"{base_url}/api/norms/document")["document"]
            numbering = [
                (item["name"], [article["no"] for article in item["chapters"][0]["articles"]])
                for item in document["documents"]
            ]
            if numbering[:2] != [
                (first_category["name"], ["1", "2"]),
                (second_category["name"], ["1"]),
            ]:
                raise RuntimeError(f"Document assembly mismatch: {numbering}")
            if any("no" in item for item in document["documents"]):
                raise RuntimeError(f"A standalone document must not carry a category number: {numbering}")
            if len(document["documents"]) != 6 or any(item["article_count"] for item in document["documents"][2:]):
                raise RuntimeError(f"Empty categories must keep their own empty document: {numbering}")

            by_category = documents_by_category(document)
            first_document = by_category[first_category["id"]]
            if "### 1 提交代码前必须通过静态检查" not in first_document["markdown"] or "### 2 每周例会前提交上周风险清单" not in first_document["markdown"]:
                raise RuntimeError("First category markdown must number its own articles from 1")
            if "进入现场必须佩戴防护用品" in first_document["markdown"]:
                raise RuntimeError("A category document must not embed another category's articles")
            if first_document["title"] != f"{first_category['name']}规范":
                raise RuntimeError(f"Unexpected document title: {first_document['title']}")
            if "# 目录" in first_document["markdown"]:
                raise RuntimeError("A single-category document must not grow a table of contents")
            if document["stats"]["total"] != 3 or document["stats"]["active"] != 3:
                raise RuntimeError(f"Stats mismatch right after recording: {document['stats']}")

            request_json(admin, f"{base_url}/api/norms", "POST", {
                "category_id": second_category["id"],
                "title": "值班交接必须记录遗留问题",
            })
            after_add = request_json(admin, f"{base_url}/api/norms/document")["document"]
            second_document = documents_by_category(after_add)[second_category["id"]]
            if [article["no"] for article in second_document["chapters"][0]["articles"]] != ["1", "2"]:
                raise RuntimeError(f"A new article must join its own category document: {second_document}")
            if after_add["stats"]["total"] != 4:
                raise RuntimeError(f"Stats mismatch after a new article: {after_add['stats']}")

            norms = request_json(admin, f"{base_url}/api/norms")["norms"]
            target = find_norm(norms, "提交代码前必须通过静态检查")
            if not target:
                raise RuntimeError(f"Norm listing failed: {norms}")

            request_json(admin, f"{base_url}/api/norms/{target['id']}", "PATCH", {
                "title": "提交代码前必须通过静态检查与单测",
                "category_id": first_category["id"],
                "status": "pending",
            })
            pending_document = request_json(admin, f"{base_url}/api/norms/document")["document"]
            if pending_document["stats"]["active"] != 3:
                raise RuntimeError(f"A pending norm must leave the documents: {pending_document['stats']}")
            pending_articles = [
                article["no"] for article in documents_by_category(pending_document)[first_category["id"]]["chapters"][0]["articles"]
            ]
            if pending_articles != ["1"]:
                raise RuntimeError(f"Pending norm must be renumbered out of the document: {pending_articles}")
            request_json(admin, f"{base_url}/api/norms/{target['id']}", "PATCH", {"status": "active"})

            created_category = next(
                item for item in request_json(admin, f"{base_url}/api/norm-categories", "POST", {"name": "测试分类"})["categories"]
                if item["name"] == "测试分类"
            )
            request_json(admin, f"{base_url}/api/norm-categories", "POST", {"name": "测试分类"}, 409)
            request_json(admin, f"{base_url}/api/norm-categories/{created_category['id']}", "PATCH", {"name": "测试分类改名"})
            request_json(admin, f"{base_url}/api/norm-categories/{created_category['id']}", "DELETE")
            request_json(admin, f"{base_url}/api/norm-categories/{first_category['id']}", "DELETE", expected=409)
            request_json(admin, f"{base_url}/api/norm-categories/{first_category['id']}", "PATCH", {"active": 0}, 409)

            request_json(admin, f"{base_url}/api/norms/{target['id']}", "DELETE")
            recycle = [
                item for item in request_json(admin, f"{base_url}/api/recycle-bin")["items"]
                if item["entity_type"] == "norm"
            ]
            if len(recycle) != 1 or recycle[0]["entity_label"] != "规范条目":
                raise RuntimeError(f"Deleted norm must enter the recycle bin: {recycle}")
            request_json(admin, f"{base_url}/api/recycle-bin/{recycle[0]['id']}/restore", "POST", {})

            member_norm = find_norm(
                request_json(member, f"{base_url}/api/norms", "POST", {
                    "category_id": second_category["id"],
                    "title": "成员随手记的规则",
                })["norms"],
                "成员随手记的规则",
            )
            if not member_norm:
                raise RuntimeError("Member could not record a norm")
            request_json(member, f"{base_url}/api/norms/{member_norm['id']}", "PATCH", {
                "title": "成员改自己的规则",
                "category_id": second_category["id"],
            })
            request_json(member, f"{base_url}/api/norms/{target['id']}", "PATCH", {"title": "改别人记的"}, 403)
            request_json(member, f"{base_url}/api/norms/{target['id']}", "DELETE", expected=403)
            request_json(member, f"{base_url}/api/norm-categories", "POST", {"name": "成员建分类"}, 403)
            request_json(member, f"{base_url}/api/norms/{member_norm['id']}", "PATCH", {"status": "pending"}, 403)

            member_document = request_json(member, f"{base_url}/api/norms/document")["document"]
            if len(member_document["documents"]) != 6:
                raise RuntimeError("Members must still read every category document")
            if not documents_by_category(member_document)[second_category["id"]]["markdown"]:
                raise RuntimeError("Member view must include rendered markdown per category")

            operations = request_json(member, f"{base_url}/api/me")["permissions"]["operations"]["norms"]
            if operations != {"view": True, "create": True, "edit": True, "delete": False}:
                raise RuntimeError(f"Unexpected default-type norm permissions: {operations}")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    print("团队规范冒烟测试通过：分类、随手记、按分类分份成文、份内编号、回收站与权限边界均符合预期。")


if __name__ == "__main__":
    main()
