"""团队规范模块的隔离冒烟测试：分类、条目、按分类分份成文与权限边界。

用法：python scripts/norms_smoke_test.py
"""

import argparse
import base64
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

# 1×1 的最小合法 PNG。服务端只校验文件签名（前 8 字节），但用真图更贴近实际。
PNG_1PX = bytes.fromhex(
    "89504e470d0a1a0a"
    "0000000d49484452000000010000000108060000001f15c489"
    "0000000a49444154789c63000100000500010d0a2db4"
    "0000000049454e44ae426082"
)
PNG_DATA_URL = "data:image/png;base64," + base64.b64encode(PNG_1PX).decode("ascii")


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


def request_raw(opener, url, expected=200):
    """Fetch bytes rather than JSON — an illustration is served as its own content type."""
    request = Request(url, headers={"Connection": "close"}, method="GET")
    try:
        with opener.open(request, timeout=20) as response:
            status = response.status
            headers = dict(response.headers)
            body = response.read()
    except HTTPError as exc:
        status = exc.code
        headers = dict(exc.headers)
        body = exc.read()
    if status != expected:
        raise RuntimeError(f"GET {url} returned {status}, expected {expected}")
    return status, headers, body


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

            # 访客（含未登录）只读：文档能看，目录与条目不能碰。
            guest_document = request_json(guest, f"{base_url}/api/norms/document")["document"]
            if len(guest_document["documents"]) != 6:
                raise RuntimeError(f"A guest must read every category document: {guest_document}")
            request_json(guest, f"{base_url}/api/norm-categories", "POST", {"name": "访客建的目录"}, 401)

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

            # ---- 两级目录 ----
            parent_category = next(
                item for item in request_json(admin, f"{base_url}/api/norm-categories", "POST", {
                    "name": "两级父目录",
                    "description": "用来验证两级目录",
                })["categories"]
                if item["name"] == "两级父目录"
            )
            sub_category = next(
                item for item in request_json(admin, f"{base_url}/api/norm-categories", "POST", {
                    "name": "python研发流程",
                    "parent_id": parent_category["id"],
                })["categories"]
                if item["name"] == "python研发流程"
            )
            if sub_category["parent_id"] != parent_category["id"]:
                raise RuntimeError(f"Sub-category must remember its parent: {sub_category}")

            # 重名只在同一上级目录内成立：同父 409，换一个父目录可以同名。
            request_json(admin, f"{base_url}/api/norm-categories", "POST", {
                "name": "python研发流程", "parent_id": parent_category["id"],
            }, 409)
            sibling_category = next(
                item for item in request_json(admin, f"{base_url}/api/norm-categories", "POST", {
                    "name": "python研发流程", "parent_id": second_category["id"],
                })["categories"]
                if item["name"] == "python研发流程" and item["parent_id"] == second_category["id"]
            )

            # 只允许两级：不能往二级目录下面再挂目录，也不能把一级目录挂到二级目录下。
            request_json(admin, f"{base_url}/api/norm-categories", "POST", {
                "name": "三级目录", "parent_id": sub_category["id"],
            }, 400)
            request_json(admin, f"{base_url}/api/norm-categories/{parent_category['id']}", "PATCH", {
                "parent_id": first_category["id"],
            }, 409)

            # 还有子目录的父目录：既不能删，也不能停用（此时父目录一条规范都没有，
            # 所以 409 只可能来自子目录这一条约束）。
            request_json(admin, f"{base_url}/api/norm-categories/{parent_category['id']}", "DELETE", expected=409)
            request_json(admin, f"{base_url}/api/norm-categories/{parent_category['id']}", "PATCH", {"active": 0}, 409)

            # 两级都能放条款，且各自成文、互不混入。
            request_json(admin, f"{base_url}/api/norms", "POST", {
                "category_id": sub_category["id"],
                "title": "提交代码必须通过 python 编译",
                "content": "构建口径见 [构建说明](https://example.com/build)，命令以文档为准。",
            })
            request_json(admin, f"{base_url}/api/norms", "POST", {
                "category_id": parent_category["id"],
                "title": "提交代码必须通过审核",
            })
            two_level = request_json(admin, f"{base_url}/api/norms/document")["document"]
            two_level_documents = documents_by_category(two_level)
            parent_document = two_level_documents[parent_category["id"]]
            child_document = two_level_documents[sub_category["id"]]
            parent_titles = [article["title"] for article in parent_document["chapters"][0]["articles"]]
            if "提交代码必须通过 python 编译" in parent_titles:
                raise RuntimeError(f"A parent document must not embed its sub-category clauses: {parent_titles}")
            if [article["no"] for article in child_document["chapters"][0]["articles"]] != ["1"]:
                raise RuntimeError(f"A sub-category numbers its own document from 1: {child_document}")
            if child_document["parent_name"] != parent_category["name"] or child_document["level"] != 2:
                raise RuntimeError(f"A sub-category document must carry its parent: {child_document}")
            if parent_document["level"] != 1 or parent_document["child_count"] != 1:
                raise RuntimeError(f"A parent document must report its children: {parent_document}")
            if "### 1 提交代码必须通过 python 编译" not in child_document["markdown"]:
                raise RuntimeError("A sub-category markdown must number its own clauses from 1")
            if "[构建说明](https://example.com/build)" not in child_document["markdown"]:
                raise RuntimeError("Markdown links in the body must survive into the export")
            if parent_document["markdown"].find("提交代码必须通过审核") < 0:
                raise RuntimeError("A parent document must keep its own clauses")

            # 二级目录可以提到一级，也可以再挂回去。
            request_json(admin, f"{base_url}/api/norm-categories/{sub_category['id']}", "PATCH", {"parent_id": 0})
            moved = next(
                item for item in request_json(admin, f"{base_url}/api/norm-categories")["categories"]
                if item["id"] == sub_category["id"]
            )
            if moved["parent_id"] is not None:
                raise RuntimeError(f"Moving a sub-category to the top level failed: {moved}")
            request_json(admin, f"{base_url}/api/norm-categories/{sub_category['id']}", "PATCH", {
                "parent_id": parent_category["id"],
            })

            # 空子目录可以直接删除；父目录因为有子目录仍然删不掉。
            request_json(admin, f"{base_url}/api/norm-categories/{sibling_category['id']}", "DELETE")
            request_json(admin, f"{base_url}/api/norm-categories/{parent_category['id']}", "DELETE", expected=409)
            request_json(admin, f"{base_url}/api/norm-categories/{sub_category['id']}", "DELETE", expected=409)

            expected_document_count = len(
                request_json(admin, f"{base_url}/api/norms/document")["document"]["documents"]
            )

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
            request_json(member, f"{base_url}/api/norms/{member_norm['id']}", "PATCH", {"status": "pending"}, 403)

            # ---- 目录权限：登录用户都能建一二级目录，但只能删自己建的 ----
            member_name = request_json(member, f"{base_url}/api/me")["user"]["display_name"]
            member_category = next(
                item for item in request_json(member, f"{base_url}/api/norm-categories", "POST", {
                    "name": "成员建的一级目录",
                })["categories"]
                if item["name"] == "成员建的一级目录"
            )
            if member_category["created_by_name"] != member_name:
                raise RuntimeError(f"A category must remember its creator: {member_category}")
            if not member_category["can_delete"]:
                raise RuntimeError("The creator must be allowed to delete their own category")
            member_sub_category = next(
                item for item in request_json(member, f"{base_url}/api/norm-categories", "POST", {
                    "name": "成员建的子目录",
                    "parent_id": member_category["id"],
                })["categories"]
                if item["name"] == "成员建的子目录"
            )

            # can_delete 随文档一起下发：左侧目录就是靠它决定画不画「删除」。
            member_categories = {
                item["id"]: item
                for item in request_json(member, f"{base_url}/api/norm-categories")["categories"]
            }
            if not member_categories[member_category["id"]]["can_delete"]:
                raise RuntimeError("A member must see can_delete on the category they created")
            if member_categories[first_category["id"]]["can_delete"]:
                raise RuntimeError("A member must not see can_delete on a seeded category")
            member_document_flag = documents_by_category(
                request_json(member, f"{base_url}/api/norms/document")["document"]
            )
            if not member_document_flag[member_category["id"]]["can_delete"]:
                raise RuntimeError("The document payload must carry can_delete as well")
            if not member_categories[member_category["id"]]["can_rename"]:
                raise RuntimeError("A member must see can_rename on the category they created")
            if member_categories[first_category["id"]]["can_rename"]:
                raise RuntimeError("A member must not see can_rename on a seeded category")
            if not member_document_flag[member_category["id"]]["can_rename"]:
                raise RuntimeError("The document payload must carry can_rename as well")

            # ---- 改名：与删除同源（创建人 + 管理员），层级/停用仍归管理员 ----
            request_json(member, f"{base_url}/api/norm-categories/{member_sub_category['id']}", "PATCH", {
                "name": "成员改的子目录",
            })
            renamed_sub = next(
                item for item in request_json(member, f"{base_url}/api/norm-categories")["categories"]
                if item["id"] == member_sub_category["id"]
            )
            if renamed_sub["name"] != "成员改的子目录" or renamed_sub["parent_id"] != member_category["id"]:
                raise RuntimeError(f"Renaming must keep the shelf where it is: {renamed_sub}")

            # 只发 name 的 PATCH 不能把说明清空（表单没带 description 时后端要保留原值）。
            with_description = request_json(member, f"{base_url}/api/norm-categories/{member_category['id']}", "PATCH", {
                "name": "成员改的一级目录",
                "description": "成员写的说明",
            })["categories"]
            with_description = next(item for item in with_description if item["id"] == member_category["id"])
            if with_description["description"] != "成员写的说明":
                raise RuntimeError(f"A rename must store the description it was given: {with_description}")
            name_only = request_json(member, f"{base_url}/api/norm-categories/{member_category['id']}", "PATCH", {
                "name": "成员改的一级目录二",
            })["categories"]
            name_only = next(item for item in name_only if item["id"] == member_category["id"])
            if name_only["description"] != "成员写的说明":
                raise RuntimeError(f"A name-only PATCH must keep the existing description: {name_only}")

            # 同一上级下重名仍然 409。
            sibling_root = next(
                item for item in request_json(member, f"{base_url}/api/norm-categories", "POST", {
                    "name": "成员建的另一个一级目录",
                })["categories"]
                if item["name"] == "成员建的另一个一级目录"
            )
            request_json(member, f"{base_url}/api/norm-categories/{member_category['id']}", "PATCH", {
                "name": "成员建的另一个一级目录",
            }, 409)

            # 非管理员带上 parent_id / active 一律 403——不静默忽略，否则会让人以为改生效了。
            request_json(member, f"{base_url}/api/norm-categories/{member_category['id']}", "PATCH", {
                "name": "成员改的一级目录二", "parent_id": 0,
            }, 403)
            request_json(member, f"{base_url}/api/norm-categories/{member_category['id']}", "PATCH", {
                "name": "成员改的一级目录二", "active": 0,
            }, 403)
            # 系统预置的、别人建的，连名字都改不动。
            request_json(member, f"{base_url}/api/norm-categories/{first_category['id']}", "PATCH", {
                "name": "成员改预置目录",
            }, 403)
            request_json(member, f"{base_url}/api/norm-categories/{parent_category['id']}", "PATCH", {
                "name": "成员改别人的目录",
            }, 403)
            # 管理员不受归属限制：别人建的也能改名。
            request_json(admin, f"{base_url}/api/norm-categories/{member_category['id']}", "PATCH", {
                "name": "管理员改成员建的目录",
            })

            # ---- 删除：仍然只能删自己建的；管理员不受归属限制 ----
            request_json(member, f"{base_url}/api/norm-categories/{member_category['id']}", "DELETE", expected=409)
            request_json(member, f"{base_url}/api/norm-categories/{member_sub_category['id']}", "DELETE")
            request_json(member, f"{base_url}/api/norm-categories/{sibling_root['id']}", "DELETE")
            request_json(member, f"{base_url}/api/norm-categories/{first_category['id']}", "DELETE", expected=403)
            # 管理员不受归属限制：别人建的也能删。
            request_json(admin, f"{base_url}/api/norm-categories/{member_category['id']}", "DELETE")


            member_document = request_json(member, f"{base_url}/api/norms/document")["document"]
            if len(member_document["documents"]) != expected_document_count:
                raise RuntimeError("Members must still read every category document")
            if not documents_by_category(member_document)[second_category["id"]]["markdown"]:
                raise RuntimeError("Member view must include rendered markdown per category")

            operations = request_json(member, f"{base_url}/api/me")["permissions"]["operations"]["norms"]
            if operations != {"view": True, "create": True, "edit": True, "delete": False}:
                raise RuntimeError(f"Unexpected default-type norm permissions: {operations}")

            # ---- 规范插图：上传只暂存，保存条款时才绑定 ----
            upload_result = request_json(member, f"{base_url}/api/norm-images", "POST", {
                "data_url": PNG_DATA_URL, "name": "登录流程图.png",
            })
            image_id = upload_result["image"]["id"]
            if upload_result["image"]["marker"] != f"[[img:{image_id}]]":
                raise RuntimeError(f"Upload must return the marker the client inserts: {upload_result}")

            illustrated = request_json(member, f"{base_url}/api/norms", "POST", {
                "category_id": first_category["id"],
                "title": "变更上线要走两段式发布",
                "content": f"先灰度再正式。\n[[img:{image_id}]]\n图 1 发布流程",
            })
            illustrated_norm = find_norm(illustrated["norms"], "变更上线要走两段式发布")
            if not illustrated_norm:
                raise RuntimeError("A clause carrying an illustration must be listed")

            def article_by_id(target_id):
                document = request_json(admin, f"{base_url}/api/norms/document")["document"]
                return next(
                    article
                    for item in document["documents"]
                    for chapter in item["chapters"]
                    for article in chapter["articles"]
                    if article["id"] == target_id
                )

            illustrated_article = article_by_id(illustrated_norm["id"])
            if [image["id"] for image in illustrated_article["images"]] != [image_id]:
                raise RuntimeError(f"A clause must expose its bound illustrations: {illustrated_article}")

            image_url = illustrated_article["images"][0]["url"]
            _, headers, body = request_raw(admin, f"{base_url}{image_url}")
            if headers.get("Content-Type") != "image/png" or body != PNG_1PX:
                raise RuntimeError(f"Illustrations must be served as their own bytes: {headers}")
            if headers.get("X-Content-Type-Options") != "nosniff":
                raise RuntimeError(f"Illustrations must not be sniffable: {headers}")

            # 访客对规范是只读可见，插图跟着可见。
            request_raw(guest, f"{base_url}{image_url}")

            # 上传要登录；类型白名单、魔数、大小都挡在入口，且校验失败时不落盘。
            request_json(guest, f"{base_url}/api/norm-images", "POST", {"data_url": PNG_DATA_URL}, 401)
            request_json(member, f"{base_url}/api/norm-images", "POST", {
                "data_url": "data:image/gif;base64,R0lGODlhAQABAAAAACw=",
            }, 400)
            request_json(member, f"{base_url}/api/norm-images", "POST", {
                "data_url": "data:image/png;base64," + base64.b64encode(b"\xff\xd8\xff" + b"\x00" * 64).decode("ascii"),
            }, 400)
            request_json(member, f"{base_url}/api/norm-images", "POST", {
                "data_url": "data:image/png;base64," + base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"\x00" * (5 * 1024 * 1024)).decode("ascii"),
            }, 400)

            # 引用不存在的图片：拒绝保存，而不是存下一条注定裂图的条款。
            request_json(member, f"{base_url}/api/norms", "POST", {
                "category_id": first_category["id"],
                "title": "引用了不存在的图片",
                "content": "[[img:999999]]",
            }, 400)
            # 上限按「不同图片」算，所以这里要用 21 个不同的 id 才会撞线。
            request_json(member, f"{base_url}/api/norms", "POST", {
                "category_id": first_category["id"],
                "title": "图片数量超限",
                "content": " ".join(f"[[img:{100000 + index}]]" for index in range(21)),
            }, 400)

            # 图片落在 data/uploads 下（部署只排除 data），不进 static。
            stored_files = list((Path(temporary_directory) / "uploads" / "norms").rglob("*.png"))
            if len(stored_files) != 1:
                raise RuntimeError(f"Uploaded illustrations must land under data/uploads: {stored_files}")

            # 去掉标记再保存 → 图片解绑、不再随条款下发；文件保留，撤销应当是免费的。
            request_json(member, f"{base_url}/api/norms/{illustrated_norm['id']}", "PATCH", {
                "content": "先灰度再正式。",
            })
            if article_by_id(illustrated_norm["id"])["images"]:
                raise RuntimeError("Removing the marker must release the illustration")
            if not stored_files[0].is_file():
                raise RuntimeError("Releasing an illustration must not delete the file")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    print("团队规范冒烟测试通过：分类、随手记、按分类分份成文、份内编号、回收站、目录建/改名/删除的归属权限、正文插图的上传/绑定/解绑均符合预期。")


if __name__ == "__main__":
    main()
