"""Backward-compatible Team Loop entry point.

Backend implementation is split across the ``team_loop`` package so existing
deployment commands and ``import server`` integrations keep working.
"""

from team_loop import *


def main():
    parser = argparse.ArgumentParser(description="周例会团队协作 Web 项目")
    parser.add_argument("--host", default="127.0.0.1", help="监听地址，局域网访问可用 0.0.0.0")
    parser.add_argument("--port", default=8000, type=int, help="监听端口")
    parser.add_argument("--migrate-only", action="store_true", help="Only initialize and migrate the database")
    args = parser.parse_args()
    init_db()
    if args.migrate_only:
        print(f"Database migration completed: {DB_PATH}")
        return
    if DEPLOY_ENV != "gray":
        ensure_daily_backup()
    os.chdir(ROOT)
    server = BoundedThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Team Loop 已启动：http://{args.host}:{args.port}")
    print(f"运行环境：{DEPLOY_ENV}；发布版本：{RELEASE_ID}；数据库：{DB_PATH}；最大并发请求：{HTTP_MAX_WORKERS}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")


if __name__ == "__main__":
    main()
