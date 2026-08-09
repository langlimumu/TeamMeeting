from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen
import argparse
import base64
from contextlib import contextmanager
import datetime as dt
import hashlib
import hmac
import ipaddress
import json
import mimetypes
import os
import re
import secrets
import sqlite3
import traceback
import uuid


def _env_int(name, default, minimum, maximum):
    try:
        value = int(os.environ.get(name) or default)
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = ROOT / "static"
DATA_DIR = Path(os.environ.get("TEAM_LOOP_DATA_DIR") or (ROOT / "data")).resolve()
DB_PATH = Path(os.environ.get("TEAM_LOOP_DB_PATH") or (DATA_DIR / "weekly_team.db")).resolve()
BACKUP_DIR = Path(os.environ.get("TEAM_LOOP_BACKUP_DIR") or (DATA_DIR / "backups")).resolve()
DEPLOY_ENV = (os.environ.get("TEAM_LOOP_ENV") or "development").strip().lower()
RELEASE_ID = (os.environ.get("TEAM_LOOP_RELEASE") or "local").strip()
TRUST_PROXY = (os.environ.get("TEAM_LOOP_TRUST_PROXY") or "").strip().lower() in {"1", "true", "yes", "on"}
REQUIRE_HTTPS = (os.environ.get("TEAM_LOOP_REQUIRE_HTTPS") or ("1" if DEPLOY_ENV == "production" else "0")).strip().lower() in {"1", "true", "yes", "on"}
SQLITE_BUSY_TIMEOUT_MS = _env_int("TEAM_LOOP_SQLITE_BUSY_TIMEOUT_MS", 15000, 1000, 120000)
HTTP_MAX_WORKERS = _env_int("TEAM_LOOP_HTTP_MAX_WORKERS", 64, 8, 256)
HTTP_REQUEST_QUEUE_SIZE = _env_int("TEAM_LOOP_HTTP_REQUEST_QUEUE_SIZE", 256, 32, 1024)
SSO_HTTP_POOL_SIZE = _env_int("TEAM_LOOP_SSO_HTTP_POOL_SIZE", 32, 2, 128)
SSO_HTTP_TIMEOUT_SECONDS = _env_int("TEAM_LOOP_SSO_HTTP_TIMEOUT_SECONDS", 12, 3, 60)
SSO_HTTP_IDLE_SECONDS = _env_int("TEAM_LOOP_SSO_HTTP_IDLE_SECONDS", 60, 10, 600)
SSO_DISCOVERY_CACHE_SECONDS = _env_int("TEAM_LOOP_SSO_DISCOVERY_CACHE_SECONDS", 300, 0, 3600)

DEFAULT_SETTINGS = [
    ("app_brand_name", "系统名称", "Team Loop", "text", "左侧顶部显示的系统名称"),
    ("app_team_name", "团队名称", "技术项目团队", "text", "左侧顶部显示的团队名称"),
    ("meeting_default_title", "默认会议标题", "周例会", "text", "创建会议和批量生成时使用的默认标题"),
    ("meeting_bulk_default_weeks", "批量生成周数", "4", "number", "会议沙盘批量生成默认覆盖的周数"),
    ("shift_default_hours", "默认班次小时", "12", "number", "新增排班时默认计入的工时"),
    ("shift_max_daily_hours", "单人每日最大工时", "24", "number", "新增排班时用于阻止同一成员当天工时超限"),
    ("thank_you_weekly_limit", "每周 Thank You 上限", "3", "number", "每位成员每周最多感谢的人数"),
    ("red_score_default_points", "红榜默认分值", "1", "number", "记录红榜积分时的默认分值"),
    ("black_score_default_points", "黑榜默认分值", "1", "number", "记录黑榜积分时的默认分值"),
    ("red_black_show_black_points", "显示黑榜积分", "1", "boolean", "是否向普通用户展示黑榜汇总积分"),
    ("red_black_show_black_details", "显示黑榜明细", "1", "boolean", "是否向普通用户展示黑榜积分明细"),
    ("late_donation_label", "迟到乐捐说明", "迟到要乐捐", "text", "参会签到中迟到乐捐的口径说明"),
    ("backup_auto_enabled", "每日自动备份", "1", "boolean", "启用后系统每天自动生成一次数据库备份"),
    ("backup_retention_days", "备份保留天数", "30", "number", "自动清理超过该天数的备份，0 表示不清理"),
    ("session_timeout_minutes", "登录有效时长（分钟）", "480", "number", "无操作超过该时长后需要重新登录"),
    ("login_max_attempts", "登录失败次数上限", "5", "number", "同一账号和地址连续失败达到上限后临时锁定"),
    ("login_lock_minutes", "登录锁定时长（分钟）", "15", "number", "触发失败次数上限后的临时锁定时间"),
    ("sso_enabled", "启用企业 SSO", "0", "boolean", "启用后登录页显示企业 SSO 入口"),
    ("sso_auto_login", "首页自动 SSO 登录", "1", "boolean", "未登录访问首页时自动跳转企业登录；失败后回退系统账号登录"),
    ("sso_mode", "OAuth2 配置方式", "discovery", "choice", "推荐使用 OIDC 自动发现；不支持 Discovery 时选择手动 OAuth2 端点"),
    ("sso_button_label", "SSO 按钮名称", "企业 SSO 登录", "text", "登录页统一身份入口的显示名称"),
    ("sso_issuer_url", "OIDC Issuer 地址", "", "text", "企业身份平台的 Issuer，不含 /.well-known/openid-configuration"),
    ("sso_authorization_url", "OAuth2 认证地址", "", "text", "用户登录时跳转的认证地址，例如 https://sso.example.com/oauth2/authorize"),
    ("sso_token_url", "Access Token 地址", "", "text", "用授权码换取 Access Token 的地址，例如 https://sso.example.com/oauth2/token"),
    ("sso_userinfo_url", "UserInfo 地址", "", "text", "用 Access Token 获取用户信息的地址，需返回工号与姓名字段"),
    ("sso_client_id", "OAuth2 Client ID", "", "text", "身份平台为 Team Loop 分配的 Client ID"),
    ("sso_client_secret", "OAuth2 Client Secret", "", "password", "建议通过 TEAM_LOOP_SSO_CLIENT_SECRET 环境变量提供；留空表示不修改"),
    ("sso_redirect_uri", "OAuth2 回调地址", "", "text", "正式部署必须填写，例如 https://team.example.com/api/sso/callback；本机可自动生成"),
    ("sso_scopes", "OAuth2 Scopes", "openid profile email", "text", "OIDC 通常使用 openid profile email；普通 OAuth2 按企业平台要求填写"),
    ("sso_username_claim", "SSO 工号字段", "preferred_username", "text", "用于关联用户管理工号的 UserInfo 字段，如 employee_id、employeeNumber 或 preferred_username"),
    ("sso_display_name_claim", "SSO 姓名字段", "name", "text", "用于显示姓名的 UserInfo 字段"),
    ("sso_group_claim", "SSO 群组字段", "groups", "text", "用于匹配团队层级的群组字段，支持 groups、roles 等点分路径"),
    ("sso_default_user_type", "SSO 新用户初始权限", "guest", "text", "自动创建的 SSO 用户先使用访客只读权限，等待管理员分类"),
    ("sso_auto_provision", "自动创建 SSO 用户", "1", "boolean", "关闭后，仅已存在且账号字段匹配的用户可通过 SSO 登录"),
]

MONTHLY_RECURRENCE_VALUES = {"first", "second", "third", "fourth", "penultimate", "last"}
TEAM_REACTIONS = ["+1", "👍", "👏", "😊", "🎉", "收到", "辛苦了", "已跟进"]
TEAM_POST_CATEGORIES = {"general", "field", "retrospective", "roast", "announcement"}
TEAM_POST_STATUSES = {"open", "resolved"}
TEAM_MOMENT_CATEGORIES = {"milestone", "delivery", "honor", "growth", "team"}
TEAM_MOMENT_IMAGE_TYPES = {
    "image/jpeg": (b"\xff\xd8\xff", ".jpg"),
    "image/png": (b"\x89PNG\r\n\x1a\n", ".png"),
    "image/webp": (b"RIFF", ".webp"),
}
TEAM_MOMENT_MAX_IMAGES = 6
TEAM_MOMENT_MAX_IMAGE_BYTES = 5 * 1024 * 1024

MODULE_CATALOG = [
    {"key": "members", "name": "团队成员", "description": "成员档案、职责画像和团队对话"},
    {"key": "moments", "name": "团队时刻", "description": "用图片和事迹沉淀团队关键事件"},
    {"key": "dashboard", "name": "工作台", "description": "团队关键指标概览"},
    {"key": "archive", "name": "搜索归档", "description": "跨年度检索会议、对话和早例会事项"},
    {"key": "morning", "name": "早例会", "description": "按人追踪当日事项、风险和下一步"},
    {"key": "processes", "name": "流程中心", "description": "维护流程模板并按 Checklist 推进个人流程"},
    {"key": "meetings", "name": "会议沙盘", "description": "周例会议题、纪要和签到"},
    {"key": "shifts", "name": "机台排班", "description": "白夜班排班和工时统计"},
    {"key": "rules", "name": "红黑榜", "description": "红黑榜细则和积分看板"},
    {"key": "thanks", "name": "Thank You", "description": "团队感谢墙和 Thank You 之星"},
    {"key": "links", "name": "常用链接", "description": "系统、文档和工具入口"},
]
MODULE_KEYS = {item["key"] for item in MODULE_CATALOG}
PERMISSION_ACTIONS = ("view", "create", "edit", "delete")
PARTICIPATION_SCOPES = {
    "members": ("include_in_members", "团队成员"),
    "morning": ("include_in_morning", "早例会跟踪"),
    "rules": ("include_in_rules", "红黑榜名单"),
    "thanks": ("include_in_thanks", "Thank You 名单"),
}
DEFAULT_USER_TYPE_KEY = "default"
GUEST_USER_TYPE_KEY = "guest"
LEGACY_GUEST_MODULES = {"members", "shifts", "rules", "thanks", "links"}
SYSTEM_USER_TYPES = [
    (DEFAULT_USER_TYPE_KEY, "默认用户类型", "管理员可修改名称和权限，也可以在迁移用户后删除。", 10, 0),
    (GUEST_USER_TYPE_KEY, "访客 / 待分类", "未登录访问与待管理员分类的 SSO 账号共用的只读权限模板。", 9999, 1),
]
INITIAL_TYPE_OPERATIONS = {
    DEFAULT_USER_TYPE_KEY: {
        "members": (1, 1, 1, 1),
        "moments": (1, 1, 1, 1),
        "dashboard": (1, 0, 0, 0),
        "archive": (1, 0, 0, 0),
        "morning": (1, 1, 1, 1),
        "processes": (1, 1, 1, 1),
        "meetings": (1, 1, 1, 0),
        "shifts": (1, 0, 0, 0),
        "rules": (1, 0, 0, 0),
        "thanks": (1, 1, 1, 1),
        "links": (1, 1, 1, 1),
    },
    GUEST_USER_TYPE_KEY: {
        module: (1, 0, 0, 0) for module in LEGACY_GUEST_MODULES
    },
}
MORNING_STATUSES = {"todo", "doing", "risk", "done"}
MORNING_PRIORITIES = {"low", "normal", "high"}
ORG_VISIBILITY_MODES = {"all", "subtree", "unit"}


