import argparse
import json
import socket
import sys
from urllib.parse import urlsplit


# 未登录可读的模块 → 各模块一个有代表性的只读接口。
#
# 这份映射是**代码**：它只回答「这个模块的读接口长什么样」。
# 访客究竟能看哪些模块是**数据**：管理员在「用户类型 → 访客 / 待分类」里随时可改。
# 两者必须分开。早先这里写死过一份模块清单（members/rules/links/shifts/thank-you），
# 于是管理员把「机台排班」从访客视图去掉、换成「问题定位排班」之后，
# 本测试开始对 /api/shifts 报 403 并中断发布 —— 那是权限数据变更，不是回归。
# 现在改成：先问实例「访客能看什么」（GET /api/me），再只探它报出来的模块。
#
# 只收「未登录也能读到 200」的接口。processes 与 dashboard 在 handler 层就要求登录
# （401 请先登录后使用流程中心 / 登录状态已失效），匿名探不到，故故意不在此列。
ANONYMOUS_READ_ENDPOINTS = {
    "members": "/api/members",
    "moments": "/api/team-moments",
    "archive": "/api/archive/years",
    "morning": "/api/morning-items",
    "meetings": "/api/meetings",
    "shifts": "/api/shifts",
    "oncall": "/api/duty-rosters",
    "norms": "/api/norms/document",
    "rules": "/api/rules",
    "thanks": "/api/thank-you",
    "links": "/api/links",
}


def request(base_url: str, path: str, expect_json: bool = True):
    parsed = urlsplit(base_url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 80
    request_bytes = (
        f"GET {path} HTTP/1.1\r\n"
        f"Host: {host}:{port}\r\n"
        "Connection: close\r\n"
        "Accept: application/json,text/html\r\n\r\n"
    ).encode("ascii")
    try:
        with socket.create_connection((host, port), timeout=10) as connection:
            connection.sendall(request_bytes)
            chunks = []
            while True:
                chunk = connection.recv(65536)
                if not chunk:
                    break
                chunks.append(chunk)
    except OSError as exc:
        raise RuntimeError(f"{path} is unavailable: {exc}") from exc

    response = b"".join(chunks)
    headers, separator, body = response.partition(b"\r\n\r\n")
    if not separator:
        raise RuntimeError(f"{path} returned an invalid HTTP response")
    status_line = headers.split(b"\r\n", 1)[0].decode("ascii", errors="replace")
    try:
        status = int(status_line.split()[1])
    except (IndexError, ValueError) as exc:
        raise RuntimeError(f"{path} returned an invalid status line: {status_line}") from exc
    if status != 200:
        raise RuntimeError(f"{path} returned HTTP {status}")
    if expect_json:
        return json.loads(body.decode("utf-8"))
    return body.decode("utf-8", errors="replace")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run read-only Team Loop deployment smoke tests")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--environment")
    parser.add_argument("--release")
    args = parser.parse_args()

    health = request(args.base_url, "/api/health")
    if health.get("status") != "ok" or health.get("database") != "ok":
        raise RuntimeError(f"Health check failed: {health}")
    if args.environment and health.get("environment") != args.environment:
        raise RuntimeError(f"Expected environment {args.environment}, got {health.get('environment')}")
    if args.release and health.get("release") != args.release:
        raise RuntimeError(f"Expected release {args.release}, got {health.get('release')}")

    page = request(args.base_url, "/", expect_json=False)
    if "Team Loop" not in page:
        raise RuntimeError("Home page marker was not found")

    # 访客可见模块由权限模板决定（数据），所以先问实例要这份名单，再逐个探它的读接口。
    # 访客模板被服务端强制要求「至少保留一个可查看模块」，所以这里是硬性断言：
    # 一份都拿不到，说明 module_permissions 表或访客模板坏了，而不是「碰巧没配」。
    permissions = request(args.base_url, "/api/me").get("permissions") or {}
    guest_modules = permissions.get("modules") or []
    if not guest_modules:
        raise RuntimeError(
            "The guest permission template grants no viewable module: /api/me returned an empty module list"
        )
    probed = []
    for module in sorted(guest_modules):
        path = ANONYMOUS_READ_ENDPOINTS.get(module)
        if not path:
            continue
        try:
            request(args.base_url, path)
        except RuntimeError as exc:
            raise RuntimeError(
                f"{exc} — /api/me reports module '{module}' as guest-visible, "
                "so its read endpoint must answer without a login"
            ) from exc
        probed.append({"module": module, "path": path})

    print(json.dumps({"status": "ok", "health": health, "guest_modules": probed}, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Smoke test failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
