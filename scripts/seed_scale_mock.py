#!/usr/bin/env python3
"""Create a repeatable 100-person Team Loop data set in the gray database."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import random
import secrets
import sqlite3
import struct
import sys
import zlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "deploy" / "gray" / "weekly_team_gray.db"
MOCK_PREFIX = "[MOCK]"
USERNAME_PREFIX = "mock"
DEFAULT_PASSWORD = "Mock123!"
RANDOM_SEED = 20260811


SURNAMES = [
    "赵", "钱", "孙", "周", "吴", "郑", "冯", "陈", "褚", "卫", "蒋", "沈", "韩", "杨", "朱", "秦",
    "尤", "许", "何", "吕", "施", "张", "孔", "曹", "严", "华", "金", "魏", "陶", "姜", "戚", "谢",
]
GIVEN_NAMES = [
    "明远", "思齐", "嘉宁", "子墨", "雨晨", "俊杰", "若溪", "天佑", "一凡", "文博", "欣怡", "浩然",
    "诗涵", "宇航", "可欣", "泽宇", "梓萱", "承泽", "静怡", "凯文", "佳琪", "睿哲", "梦瑶", "博文",
]
TITLES = ["系统工程师", "现场支持", "质量工程师", "自动化工程师", "测试工程师", "项目协调", "数据分析", "技术负责人"]
SKILL_GROUPS = [
    ["故障定位", "日志分析", "复盘"],
    ["PLC", "自动化", "脚本"],
    ["质量分析", "SOP", "风险识别"],
    ["现场支持", "交接", "设备点检"],
    ["数据看板", "SQL", "趋势分析"],
    ["项目推进", "会议组织", "跨团队协同"],
]
MORNING_TITLES = [
    "TOPTB 温控波动闭环", "机台报警截图补齐", "夜班交接问题跟踪", "质量复盘模板更新", "自动化脚本验证",
    "设备点检标准优化", "供应商备件到货确认", "生产数据看板校验", "现场异常复盘", "测试环境稳定性检查",
    "SOP 评审意见闭环", "跨团队权限申请", "链路告警阈值优化", "周例会材料准备", "机台节拍偏差分析",
]
PROGRESS_TEXT = [
    "已完成数据核对，今天继续验证异常样本并同步结论。",
    "现场信息已收齐，下一步确认责任边界和完成时间。",
    "第一轮验证通过，今天补充边界场景并更新记录。",
    "已与相关人员对齐，等待最后一项输入后形成闭环。",
    "问题已定位，正在验证修复方案对现网的影响。",
]
RISKS = ["等待供应商回复", "跨团队权限尚未开通", "夜班样本不足", "变更窗口待确认", "暂无风险"]
POST_CATEGORIES = ["general", "onsite", "retrospective", "roast", "announcement"]
POST_TITLES = [
    "夜班交接信息怎么写更清楚", "TOPTB 报警复盘记录", "本周现场问题集中讨论", "质量模板使用反馈",
    "自动化工具经验分享", "新成员交接注意事项", "设备点检容易遗漏的步骤", "跨团队协作事项同步",
    "周例会前需要确认的材料", "链路库入口和权限问题", "值班期间的效率优化建议", "本月团队协作亮点",
]
REPLY_TEXTS = [
    "我这边已经复现，补充截图后一起看。", "收到，今天下班前同步处理结果。", "这个建议很好，可以先在灰度环境验证。",
    "现场还有一个相似案例，我整理后补充。", "已跟进，责任人和时间点都确认了。", "建议把结论沉淀到常用链接里的 SOP。",
    "夜班会重点关注，有变化及时在这里更新。", "数据口径已确认，后续按这个标准执行。",
]
THANKS_EVIDENCE = [
    "协助定位夜班告警根因，并补齐了复盘所需的关键截图。",
    "主动协调跨团队权限，让现场问题按计划完成验证。",
    "在交接前复核数据口径，避免了错误结论进入周报。",
    "临时支援机台异常处理，整理出可复用的排查步骤。",
    "帮助优化自动化脚本，显著减少了重复操作时间。",
    "及时指出质量风险并推动责任人完成闭环。",
]
MOMENT_TITLES = [
    "关键里程碑按期达成", "夜班异常快速闭环", "跨团队协作完成联调", "质量改进获得认可", "自动化效率提升",
    "现场攻坚顺利完成", "新人独立完成首个任务", "月度复盘沉淀最佳实践", "连续稳定运行达成",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="为灰度环境生成可重复的 100 人规模 Mock 数据")
    parser.add_argument("--database", type=Path, default=DEFAULT_DB, help="灰度 SQLite 数据库路径")
    parser.add_argument("--target-users", type=int, default=100, help="目标活跃用户总数，默认 100")
    parser.add_argument("--seed", type=int, default=RANDOM_SEED, help="固定随机种子")
    parser.add_argument("--password", default=DEFAULT_PASSWORD, help="Mock 账号统一登录密码")
    parser.add_argument("--dry-run", action="store_true", help="只输出计划，不修改数据库")
    return parser.parse_args()


def assert_gray_database(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    if not resolved.exists():
        raise SystemExit(f"数据库不存在：{resolved}")
    normalized = str(resolved).replace("\\", "/").lower()
    if "/gray/" not in normalized and not resolved.name.lower().endswith("_gray.db"):
        raise SystemExit("安全保护：本脚本只允许写入 gray 目录或 *_gray.db，拒绝正式数据库。")
    return resolved


def now_iso() -> str:
    return dt.datetime.now().replace(microsecond=0).isoformat()


def date_iso(value: dt.date) -> str:
    return value.isoformat()


def previous_workday(value: dt.date) -> dt.date:
    current = value - dt.timedelta(days=1)
    while current.weekday() >= 5:
        current -= dt.timedelta(days=1)
    return current


def workdays_ending(end: dt.date, count: int) -> list[dt.date]:
    days: list[dt.date] = []
    current = end
    while len(days) < count:
        if current.weekday() < 5:
            days.append(current)
        current -= dt.timedelta(days=1)
    return list(reversed(days))


def week_start(value: dt.date) -> dt.date:
    return value - dt.timedelta(days=value.weekday())


def make_hash(password: str) -> tuple[str, str]:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 120000)
    return salt, digest.hex()


def backup_database(source: sqlite3.Connection, database: Path) -> Path:
    backup_dir = database.parent / "mock_backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    target = backup_dir / f"{database.stem}-before-mock-{dt.datetime.now():%Y%m%d-%H%M%S}.db"
    with sqlite3.connect(target) as destination:
        source.backup(destination)
    return target


def png_chunk(chunk_type: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + chunk_type + data + struct.pack(">I", zlib.crc32(chunk_type + data) & 0xFFFFFFFF)


def make_mock_png(index: int, width: int = 640, height: int = 360) -> bytes:
    palettes = [
        ((48, 98, 255), (99, 212, 188)),
        ((230, 73, 95), (255, 185, 90)),
        ((54, 161, 105), (104, 210, 240)),
        ((117, 76, 200), (244, 135, 190)),
        ((22, 31, 48), (74, 144, 226)),
    ]
    start, end = palettes[index % len(palettes)]
    rows = []
    for y in range(height):
        ratio = y / max(1, height - 1)
        color = tuple(int(start[i] * (1 - ratio) + end[i] * ratio) for i in range(3))
        row = bytearray(color * width)
        band_start = (index * 47 + y // 3) % width
        for x in range(max(0, band_start - 18), min(width, band_start + 18)):
            offset = x * 3
            row[offset:offset + 3] = bytes((min(255, color[0] + 30), min(255, color[1] + 30), min(255, color[2] + 30)))
        rows.append(b"\x00" + bytes(row))
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + png_chunk(b"IHDR", header) + png_chunk(b"IDAT", zlib.compress(b"".join(rows), 9)) + png_chunk(b"IEND", b"")


def placeholders(values: list[int]) -> str:
    return ",".join("?" for _ in values)


def cleanup_mock_content(conn: sqlite3.Connection, mock_user_ids: list[int]) -> None:
    user_sql = placeholders(mock_user_ids) if mock_user_ids else "NULL"
    params = mock_user_ids

    post_ids = [row[0] for row in conn.execute("SELECT id FROM team_posts WHERE title LIKE ?", (f"{MOCK_PREFIX}%",))]
    if post_ids:
        reply_ids = [row[0] for row in conn.execute(f"SELECT id FROM team_post_replies WHERE post_id IN ({placeholders(post_ids)})", post_ids)]
        if reply_ids:
            conn.execute(f"DELETE FROM team_reply_reactions WHERE reply_id IN ({placeholders(reply_ids)})", reply_ids)
        conn.execute(f"DELETE FROM team_post_reactions WHERE post_id IN ({placeholders(post_ids)})", post_ids)
        conn.execute(f"DELETE FROM team_post_replies WHERE post_id IN ({placeholders(post_ids)})", post_ids)
        conn.execute(f"DELETE FROM team_posts WHERE id IN ({placeholders(post_ids)})", post_ids)

    moment_ids = [row[0] for row in conn.execute("SELECT id FROM team_moments WHERE title LIKE ?", (f"{MOCK_PREFIX}%",))]
    if moment_ids:
        conn.execute(f"DELETE FROM team_moment_images WHERE moment_id IN ({placeholders(moment_ids)})", moment_ids)
        conn.execute(f"DELETE FROM team_moments WHERE id IN ({placeholders(moment_ids)})", moment_ids)

    meeting_ids = [row[0] for row in conn.execute("SELECT id FROM meetings WHERE title LIKE ?", (f"{MOCK_PREFIX}%",))]
    if meeting_ids:
        conn.execute(f"DELETE FROM meeting_attendance WHERE meeting_id IN ({placeholders(meeting_ids)})", meeting_ids)
        conn.execute(f"DELETE FROM meeting_topic_links WHERE meeting_id IN ({placeholders(meeting_ids)})", meeting_ids)
        conn.execute(f"DELETE FROM meeting_items WHERE meeting_id IN ({placeholders(meeting_ids)})", meeting_ids)
        conn.execute(f"DELETE FROM meetings WHERE id IN ({placeholders(meeting_ids)})", meeting_ids)

    template_ids = [row[0] for row in conn.execute("SELECT id FROM process_templates WHERE name LIKE ?", (f"{MOCK_PREFIX}%",))]
    instance_ids = [row[0] for row in conn.execute("SELECT id FROM process_instances WHERE title LIKE ?", (f"{MOCK_PREFIX}%",))]
    if instance_ids:
        conn.execute(f"DELETE FROM process_instance_items WHERE instance_id IN ({placeholders(instance_ids)})", instance_ids)
        conn.execute(f"DELETE FROM process_instances WHERE id IN ({placeholders(instance_ids)})", instance_ids)
    if template_ids:
        conn.execute(f"DELETE FROM process_template_items WHERE template_id IN ({placeholders(template_ids)})", template_ids)
        conn.execute(f"DELETE FROM process_templates WHERE id IN ({placeholders(template_ids)})", template_ids)

    rule_ids = [row[0] for row in conn.execute("SELECT id FROM red_black_rules WHERE title LIKE ?", (f"{MOCK_PREFIX}%",))]
    if rule_ids:
        conn.execute(f"DELETE FROM red_black_scores WHERE rule_id IN ({placeholders(rule_ids)})", rule_ids)
        conn.execute(f"DELETE FROM red_black_rules WHERE id IN ({placeholders(rule_ids)})", rule_ids)

    machine_ids = [row[0] for row in conn.execute("SELECT id FROM machines WHERE name LIKE 'MOCK-%'")]
    if machine_ids:
        conn.execute(f"DELETE FROM shifts WHERE machine_id IN ({placeholders(machine_ids)})", machine_ids)
        conn.execute(f"DELETE FROM machines WHERE id IN ({placeholders(machine_ids)})", machine_ids)

    conn.execute("DELETE FROM links WHERE title LIKE ?", (f"{MOCK_PREFIX}%",))
    if mock_user_ids:
        conn.execute(f"DELETE FROM morning_items WHERE owner_id IN ({user_sql})", params)
        conn.execute(f"DELETE FROM thank_you_votes WHERE voter_id IN ({user_sql}) OR receiver_id IN ({user_sql})", [*params, *params])
        conn.execute(f"DELETE FROM red_black_scores WHERE user_id IN ({user_sql})", params)


def ensure_users(conn: sqlite3.Connection, target_users: int, password: str, rng: random.Random) -> list[sqlite3.Row]:
    existing_mock = conn.execute("SELECT id, username FROM users WHERE username GLOB 'mock[0-9][0-9][0-9]' ORDER BY username").fetchall()
    mock_ids = [row["id"] for row in existing_mock]
    cleanup_mock_content(conn, mock_ids)

    real_active = conn.execute("SELECT COUNT(*) FROM users WHERE active=1 AND username NOT GLOB 'mock[0-9][0-9][0-9]'").fetchone()[0]
    needed = target_users - real_active
    if needed < 0:
        raise RuntimeError(f"现有非 Mock 活跃用户已达 {real_active} 人，超过目标 {target_users} 人。")
    if needed == 0 and not existing_mock:
        raise RuntimeError("现有真实活跃用户已达到目标人数；为避免向真实账号写入 Mock 业务数据，脚本已停止。")

    orgs = conn.execute("SELECT id, name FROM org_units WHERE active=1 ORDER BY CASE WHEN parent_id IS NULL THEN 1 ELSE 0 END, sort_order, id").fetchall()
    if not orgs:
        raise RuntimeError("没有可用组织，无法分配 Mock 用户。")
    user_types = conn.execute("SELECT key FROM user_types WHERE active=1 AND key!='guest' ORDER BY sort_order, key").fetchall()
    if not user_types:
        raise RuntimeError("没有可用的非访客用户类型。")

    for index in range(1, max(needed, len(existing_mock)) + 1):
        username = f"mock{index:03d}"
        active = 1 if index <= needed else 0
        surname = SURNAMES[(index - 1) % len(SURNAMES)]
        given = GIVEN_NAMES[((index - 1) // len(SURNAMES) + index * 3) % len(GIVEN_NAMES)]
        display_name = f"{surname}{given}"
        org = orgs[(index - 1) % len(orgs)]
        type_key = user_types[0]["key"] if index % 5 else user_types[min(1, len(user_types) - 1)]["key"]
        row = conn.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()
        if row:
            conn.execute(
                """
                UPDATE users SET display_name=?, role='user', active=?, user_type=?, auth_source='local',
                    employee_id=?, org_unit_id=?, classification_pending=0
                WHERE id=?
                """,
                (display_name, active, type_key, f"MOCK-{10000 + index}", org["id"], row["id"]),
            )
        else:
            salt, password_hash = make_hash(password)
            conn.execute(
                """
                INSERT INTO users(
                    username, salt, password_hash, display_name, role, active, created_at, user_type,
                    auth_source, employee_id, org_unit_id, classification_pending, sso_groups_json
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (username, salt, password_hash, display_name, "user", active, now_iso(), type_key, "local", f"MOCK-{10000 + index}", org["id"], 0, "[]"),
            )

    conn.execute("UPDATE users SET active=0 WHERE username GLOB 'mock[0-9][0-9][0-9]' AND CAST(SUBSTR(username,5) AS INTEGER)>?", (needed,))
    active_users = conn.execute(
        """
        SELECT u.*, COALESCE(t.include_in_members,1) include_in_members,
               COALESCE(t.include_in_morning,1) include_in_morning,
               COALESCE(t.include_in_rules,1) include_in_rules,
               COALESCE(t.include_in_thanks,1) include_in_thanks
        FROM users u LEFT JOIN user_types t ON t.key=u.user_type
        WHERE u.active=1 ORDER BY u.id
        """
    ).fetchall()
    if len(active_users) != target_users:
        raise RuntimeError(f"用户生成后活跃人数为 {len(active_users)}，预期 {target_users}。")
    return active_users


def seed_members(conn: sqlite3.Connection, users: list[sqlite3.Row], rng: random.Random) -> None:
    mock_users = [user for user in users if user["username"].startswith(USERNAME_PREFIX)]
    for order, user in enumerate(mock_users, start=100):
        skills = SKILL_GROUPS[order % len(SKILL_GROUPS)]
        tags = [skills[0], "白班" if order % 2 else "夜班", "骨干" if order % 7 == 0 else "协作"]
        member = conn.execute("SELECT id FROM members WHERE user_id=?", (user["id"],)).fetchone()
        values = (
            user["display_name"], TITLES[order % len(TITLES)],
            f"负责{skills[0]}、{skills[1]}及相关事项闭环", json.dumps(tags, ensure_ascii=False),
            f"擅长{skills[0]}，能够支撑跨团队问题定位。", json.dumps(skills, ensure_ascii=False),
            json.dumps([f"MOCK-{order % 8 + 1:02d}"], ensure_ascii=False), f"{skills[0]}、{skills[2]}", order,
        )
        if member:
            conn.execute(
                """
                UPDATE members SET name=?, title=?, responsibilities=?, tags=?, comment=?, skills=?, machine_scope=?,
                    expertise=?, backup_owner='', contact='', sort_order=?, active=1 WHERE id=?
                """,
                (*values, member["id"]),
            )
        else:
            conn.execute(
                """
                INSERT INTO members(user_id,name,title,responsibilities,tags,comment,created_at,active,skills,machine_scope,expertise,backup_owner,contact,sort_order)
                VALUES(?,?,?,?,?,?,?,1,?,?,?,?,?,?)
                """,
                (user["id"], *values[:5], now_iso(), values[5], values[6], values[7], "", "", values[8]),
            )
    conn.execute(
        """
        UPDATE members SET active=0
        WHERE user_id IN (SELECT id FROM users WHERE username GLOB 'mock[0-9][0-9][0-9]' AND active=0)
        """
    )


def seed_morning(conn: sqlite3.Connection, users: list[sqlite3.Row], rng: random.Random, today: dt.date) -> int:
    owners = [user for user in users if user["include_in_morning"] and user["username"].startswith(USERNAME_PREFIX)]
    workdays = workdays_ending(today, 12)
    inserted = 0
    for owner_index, owner in enumerate(owners):
        chains = [
            (MORNING_TITLES[owner_index % len(MORNING_TITLES)], rng.randint(4, 9), rng.choice(["doing", "risk"]), rng.choice(["normal", "high"])),
            (MORNING_TITLES[(owner_index + 5) % len(MORNING_TITLES)], rng.randint(2, 5), "done", rng.choice(["low", "normal", "high"])),
            (MORNING_TITLES[(owner_index + 9) % len(MORNING_TITLES)], 1, "todo", rng.choice(["normal", "high"])),
        ]
        for chain_index, (title, duration, final_status, priority) in enumerate(chains):
            dates = workdays[-duration:]
            root_id = None
            previous_id = None
            previous_date = None
            for day_index, item_day in enumerate(dates):
                is_last = day_index == len(dates) - 1
                if final_status == "done":
                    status = "done" if is_last else ("doing" if day_index else "todo")
                elif final_status == "risk":
                    status = "risk" if is_last or day_index >= len(dates) - 2 else "doing"
                else:
                    status = final_status if is_last else "doing"
                blocker = rng.choice(RISKS[:-1]) if status == "risk" else ""
                created = f"{item_day.isoformat()}T08:{10 + owner_index % 40:02d}:00"
                updated = f"{item_day.isoformat()}T09:{10 + chain_index * 10:02d}:00"
                cursor = conn.execute(
                    """
                    INSERT INTO morning_items(
                        owner_id,item_date,title,detail,status,priority,blocker,due_date,updated_by,created_at,updated_at,
                        active,root_id,carry_from_id,carried_from_date,version
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        owner["id"], date_iso(item_day), f"{MOCK_PREFIX} {title}", rng.choice(PROGRESS_TEXT), status,
                        priority, blocker, date_iso(today + dt.timedelta(days=owner_index % 4)), owner["id"], created, updated,
                        1, root_id, previous_id, date_iso(previous_date) if previous_date else None, day_index + 1,
                    ),
                )
                if root_id is None:
                    root_id = cursor.lastrowid
                    conn.execute("UPDATE morning_items SET root_id=? WHERE id=?", (root_id, root_id))
                previous_id = cursor.lastrowid
                previous_date = item_day
                inserted += 1
    return inserted


def seed_forum(conn: sqlite3.Connection, users: list[sqlite3.Row], rng: random.Random, today: dt.date) -> tuple[int, int]:
    authors = [user for user in users if user["username"].startswith(USERNAME_PREFIX)]
    all_ids = [user["id"] for user in users]
    post_ids: list[int] = []
    reply_count = 0
    reactions = ["+1", "👍", "收到", "辛苦了", "✅", "👏", "💡", "🚀"]
    for index in range(120):
        author = authors[index % len(authors)]
        category = POST_CATEGORIES[index % len(POST_CATEGORIES)]
        created_day = today - dt.timedelta(days=index % 60)
        created_at = f"{created_day.isoformat()}T{8 + index % 12:02d}:{index % 60:02d}:00"
        title = f"{MOCK_PREFIX} {POST_TITLES[index % len(POST_TITLES)]} #{index + 1}"
        cursor = conn.execute(
            """
            INSERT INTO team_posts(user_id,kind,title,category,status,pinned,view_count,content,org_unit_id,updated_at,created_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                author["id"], "roast" if category == "roast" else "comment", title, category, "resolved" if index % 9 == 0 else "open",
                1 if index % 29 == 0 else 0, 15 + (index * 17) % 420,
                f"{POST_TITLES[index % len(POST_TITLES)]}，请大家结合现场情况补充经验和建议。", author["org_unit_id"], created_at, created_at,
            ),
        )
        post_id = cursor.lastrowid
        post_ids.append(post_id)
        root_replies: list[int] = []
        for reply_index in range(2 + index % 5):
            replier_id = all_ids[(index * 7 + reply_index * 11) % len(all_ids)]
            parent_id = root_replies[reply_index % len(root_replies)] if root_replies and reply_index >= 3 else None
            reply_at = f"{created_day.isoformat()}T{10 + reply_index % 10:02d}:{(index + reply_index * 7) % 60:02d}:00"
            reply_cursor = conn.execute(
                "INSERT INTO team_post_replies(post_id,parent_reply_id,user_id,content,created_at) VALUES(?,?,?,?,?)",
                (post_id, parent_id, replier_id, rng.choice(REPLY_TEXTS), reply_at),
            )
            reply_id = reply_cursor.lastrowid
            if parent_id is None:
                root_replies.append(reply_id)
            reply_count += 1
            for reaction_index in range(index % 3):
                reactor = all_ids[(index + reply_index + reaction_index * 13) % len(all_ids)]
                conn.execute(
                    "INSERT OR IGNORE INTO team_reply_reactions(reply_id,user_id,reaction,created_at) VALUES(?,?,?,?)",
                    (reply_id, reactor, reactions[(index + reaction_index) % len(reactions)], reply_at),
                )
        for reaction_index in range(1 + index % 4):
            reactor = all_ids[(index * 3 + reaction_index * 17) % len(all_ids)]
            conn.execute(
                "INSERT OR IGNORE INTO team_post_reactions(post_id,user_id,reaction,created_at) VALUES(?,?,?,?)",
                (post_id, reactor, reactions[(index + reaction_index) % len(reactions)], created_at),
            )
    return len(post_ids), reply_count


def seed_moments(conn: sqlite3.Connection, users: list[sqlite3.Row], rng: random.Random, today: dt.date) -> tuple[int, int]:
    creators = [user for user in users if user["username"].startswith(USERNAME_PREFIX)]
    image_count = 0
    for index in range(24):
        creator = creators[index % len(creators)]
        event_day = today - dt.timedelta(days=index * 12)
        title = f"{MOCK_PREFIX} {MOMENT_TITLES[index % len(MOMENT_TITLES)]}"
        created_at = f"{event_day.isoformat()}T18:00:00"
        cursor = conn.execute(
            """
            INSERT INTO team_moments(org_unit_id,title,story,category,event_date,created_by,created_at,updated_at)
            VALUES(?,?,?,?,?,?,?,?)
            """,
            (
                creator["org_unit_id"], title,
                "团队围绕目标协同攻坚，从问题识别、方案验证到结果复盘形成完整闭环。这一刻值得被记录，也感谢每一位成员的投入。",
                ["milestone", "breakthrough", "recognition", "growth"][index % 4], date_iso(event_day), creator["id"], created_at, created_at,
            ),
        )
        for image_index in range(1 + index % 6):
            image_data = make_mock_png(index * 7 + image_index)
            conn.execute(
                "INSERT INTO team_moment_images(moment_id,filename,mime_type,image_data,sort_order,created_at) VALUES(?,?,?,?,?,?)",
                (cursor.lastrowid, f"mock-moment-{index + 1:02d}-{image_index + 1}.png", "image/png", image_data, image_index, created_at),
            )
            image_count += 1
    return 24, image_count


def seed_thanks(conn: sqlite3.Connection, users: list[sqlite3.Row], rng: random.Random, today: dt.date) -> int:
    participants = [user for user in users if user["include_in_thanks"]]
    voters = [user for user in participants if user["username"].startswith(USERNAME_PREFIX)]
    current_week = week_start(today)
    count = 0
    for week_offset in range(12):
        start = current_week - dt.timedelta(weeks=week_offset)
        for voter_index, voter in enumerate(voters):
            receiver_count = 2 if (voter_index + week_offset) % 4 else 3
            candidates = [user for user in participants if user["id"] != voter["id"]]
            rng.shuffle(candidates)
            cross_org = [user for user in candidates if user["org_unit_id"] != voter["org_unit_id"]]
            same_org = [user for user in candidates if user["org_unit_id"] == voter["org_unit_id"]]
            selected: list[sqlite3.Row] = []
            if cross_org and (voter_index + week_offset) % 3 == 0:
                selected.append(cross_org[0])
            for candidate in [*same_org, *cross_org, *candidates]:
                if candidate["id"] not in {item["id"] for item in selected}:
                    selected.append(candidate)
                if len(selected) >= receiver_count:
                    break
            for receiver in selected:
                created_at = f"{(start + dt.timedelta(days=(voter_index + receiver['id']) % 5)).isoformat()}T17:30:00"
                conn.execute(
                    "INSERT OR IGNORE INTO thank_you_votes(voter_id,receiver_id,week_start,evidence,created_at) VALUES(?,?,?,?,?)",
                    (voter["id"], receiver["id"], date_iso(start), f"{MOCK_PREFIX} {rng.choice(THANKS_EVIDENCE)}", created_at),
                )
                count += 1
    return count


def seed_scores(conn: sqlite3.Connection, users: list[sqlite3.Row], rng: random.Random, today: dt.date, admin_id: int) -> int:
    rules = [
        ("红榜-高质量闭环", "red", "主动推动问题闭环，并形成可复用经验。"),
        ("红榜-跨团队协作", "red", "主动支援其他团队并按期交付结果。"),
        ("红榜-质量改进", "red", "识别重大风险并推动完成预防措施。"),
        ("黑榜-交接遗漏", "black", "关键交接信息未同步，影响后续处理。"),
        ("黑榜-任务逾期", "black", "承诺事项逾期且未提前说明风险。"),
    ]
    rule_ids: dict[str, list[int]] = {"red": [], "black": []}
    for title, kind, content in rules:
        cursor = conn.execute(
            "INSERT INTO red_black_rules(title,kind,content,effective_from,active,created_by,created_at) VALUES(?,?,?,?,1,?,?)",
            (f"{MOCK_PREFIX} {title}", kind, content, f"{today.year}-01-01", admin_id, now_iso()),
        )
        rule_ids[kind].append(cursor.lastrowid)
    participants = [user for user in users if user["include_in_rules"]]
    count = 0
    for month in range(1, 13):
        for index, user in enumerate(participants):
            if (index * 7 + month) % 4 == 0:
                points = 1 + (index + month) % 5
                rule_id = rule_ids["red"][(index + month) % len(rule_ids["red"])]
                score_day = dt.date(today.year, month, min(5 + index % 22, 28))
                conn.execute(
                    "INSERT INTO red_black_scores(user_id,rule_id,kind,points,reason,score_date,created_by,created_at) VALUES(?,?,?,?,?,?,?,?)",
                    (user["id"], rule_id, "red", points, f"{MOCK_PREFIX} 完成关键事项并形成可复用成果。", date_iso(score_day), admin_id, f"{score_day.isoformat()}T18:00:00"),
                )
                count += 1
            if (index * 5 + month) % 11 == 0:
                points = -(1 + (index + month) % 3)
                rule_id = rule_ids["black"][(index + month) % len(rule_ids["black"])]
                score_day = dt.date(today.year, month, min(8 + index % 18, 28))
                conn.execute(
                    "INSERT INTO red_black_scores(user_id,rule_id,kind,points,reason,score_date,created_by,created_at) VALUES(?,?,?,?,?,?,?,?)",
                    (user["id"], rule_id, "black", points, f"{MOCK_PREFIX} 交接或进度同步不完整，需要复盘改进。", date_iso(score_day), admin_id, f"{score_day.isoformat()}T18:10:00"),
                )
                count += 1
    return count


def seed_meetings(conn: sqlite3.Connection, users: list[sqlite3.Row], rng: random.Random, today: dt.date, admin_id: int) -> tuple[int, int, int]:
    orgs = conn.execute("SELECT id,name FROM org_units WHERE active=1 ORDER BY id").fetchall()
    meeting_count = item_count = attendance_count = 0
    for index in range(36):
        org = orgs[index % len(orgs)]
        types = conn.execute(
            "SELECT id,name FROM meeting_topic_types WHERE active=1 AND org_unit_id=? ORDER BY sort_order,id",
            (org["id"],),
        ).fetchall()
        options = conn.execute(
            """
            SELECT o.id,o.type_id,o.title,o.duration_minutes
            FROM meeting_topic_options o
            JOIN meeting_topic_types t ON t.id=o.type_id
            WHERE o.active=1 AND t.active=1 AND t.org_unit_id=?
            ORDER BY o.type_id,o.sort_order,o.id
            """,
            (org["id"],),
        ).fetchall()
        meeting_day = today - dt.timedelta(days=(35 - index) * 7)
        status = "completed" if meeting_day < today else "scheduled"
        creator = users[(index * 7) % len(users)]
        cursor = conn.execute(
            "INSERT INTO meetings(meeting_date,start_time,title,summary,status,created_by,org_unit_id,created_at) VALUES(?,?,?,?,?,?,?,?)",
            (
                date_iso(meeting_day), f"{8 + index % 9:02d}:{'30' if index % 2 else '00'}",
                f"{MOCK_PREFIX} {org['name']} 第{index + 1}次协同例会", "聚焦进度、风险、技术复盘和行动安排。", status,
                creator["id"], org["id"], f"{meeting_day.isoformat()}T08:00:00",
            ),
        )
        meeting_id = cursor.lastrowid
        meeting_count += 1
        for sort_order in range(5):
            option = options[(index * 3 + sort_order) % len(options)] if options else None
            topic_type = types[(index + sort_order) % len(types)] if types else None
            owner = users[(index * 11 + sort_order * 7) % len(users)]
            title = option["title"] if option else ["进度同步", "质量风险", "技术复盘", "协同事项", "行动安排"][sort_order]
            item_status = "done" if status == "completed" and sort_order < 4 else ("doing" if sort_order == 0 else "todo")
            conn.execute(
                """
                INSERT INTO meeting_items(
                    meeting_id,section,title,detail,owner_id,status,due_date,created_by,created_at,type_id,option_id,
                    minutes,open_issues,next_steps,sort_order,duration_minutes,expected_output,materials
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    meeting_id, topic_type["name"] if topic_type else "协同议题", f"{MOCK_PREFIX} {title}",
                    "同步当前状态、关键变化和需要团队决策的事项。", owner["id"], item_status,
                    date_iso(meeting_day + dt.timedelta(days=7)), creator["id"], f"{meeting_day.isoformat()}T08:00:00",
                    topic_type["id"] if topic_type else None, option["id"] if option else None,
                    "已确认当前进展与风险，责任人将按约定时间继续推进。" if status == "completed" else "",
                    "仍需关注跨团队资源与变更窗口。" if sort_order == 1 else "", "下次会议前更新处理结果。",
                    sort_order, option["duration_minutes"] if option else 10, "形成明确结论和责任分工", "相关数据看板及现场记录",
                ),
            )
            item_count += 1
        local_users = [user for user in users if user["org_unit_id"] == org["id"]]
        attendees = local_users[:]
        if len(attendees) < 18:
            attendees.extend(user for user in users if user["id"] not in {item["id"] for item in attendees})
        attendees = attendees[: min(len(attendees), 18 + index % 13)]
        for attendee_index, attendee in enumerate(attendees):
            attendance_status = "present"
            if attendee_index % 19 == 0:
                attendance_status = "late"
            elif attendee_index % 23 == 0:
                attendance_status = "leave"
            elif attendee_index % 29 == 0:
                attendance_status = "absent"
            donation_required = int(attendance_status in ("late", "absent"))
            conn.execute(
                """
                INSERT INTO meeting_attendance(
                    meeting_id,user_id,status,donation_required,donation_amount,donation_done,note,updated_by,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?)
                """,
                (meeting_id, attendee["id"], attendance_status, donation_required, 20 if donation_required else 0, index % 2 if donation_required else 0, "", admin_id, f"{meeting_day.isoformat()}T12:00:00"),
            )
            attendance_count += 1
    return meeting_count, item_count, attendance_count


def seed_shifts(conn: sqlite3.Connection, users: list[sqlite3.Row], today: dt.date, admin_id: int) -> tuple[int, int]:
    participants = [user for user in users if user["username"].startswith(USERNAME_PREFIX)]
    participants_by_org = {}
    for user in participants:
        participants_by_org.setdefault(user["org_unit_id"], []).append(user)
    machines_by_org = {}
    machine_sequence = 0
    for org_unit_id in sorted(participants_by_org):
        machines_by_org[org_unit_id] = []
        for _ in range(2):
            machine_sequence += 1
            cursor = conn.execute(
                "INSERT INTO machines(org_unit_id,name,description) VALUES(?,?,?)",
                (org_unit_id, f"MOCK-{machine_sequence:02d}", f"{MOCK_PREFIX} 用于 100 人规模预览的测试机台"),
            )
            machines_by_org[org_unit_id].append(cursor.lastrowid)
    first = today.replace(day=1)
    next_month = (first + dt.timedelta(days=32)).replace(day=1)
    end = (next_month + dt.timedelta(days=32)).replace(day=1) - dt.timedelta(days=1)
    shift_count = 0
    current = first
    day_index = 0
    while current <= end:
        for org_unit_id, machine_ids in machines_by_org.items():
            org_participants = participants_by_org[org_unit_id]
            for machine_index, machine_id in enumerate(machine_ids):
                for shift_index, shift_type in enumerate(("day", "night")):
                    user = org_participants[(day_index * 17 + machine_index * 5 + shift_index) % len(org_participants)]
                    conn.execute(
                        "INSERT INTO shifts(machine_id,user_id,shift_type,shift_date,hours,note,created_by,created_at) VALUES(?,?,?,?,?,?,?,?)",
                        (machine_id, user["id"], shift_type, date_iso(current), 12, f"{MOCK_PREFIX} 月度排班", admin_id, now_iso()),
                    )
                    shift_count += 1
        current += dt.timedelta(days=1)
        day_index += 1
    return len(machine_ids), shift_count


def seed_links(conn: sqlite3.Connection, users: list[sqlite3.Row], today: dt.date) -> int:
    categories = [row["name"] for row in conn.execute("SELECT name FROM link_categories WHERE active=1 ORDER BY sort_order,id")]
    if not categories:
        categories = ["通用"]
    creators = [user for user in users if user["username"].startswith(USERNAME_PREFIX)]
    for index in range(48):
        creator = creators[index % len(creators)]
        category = categories[index % len(categories)]
        conn.execute(
            """
            INSERT INTO links(
                title,url,category,description,created_by,created_at,pinned,invalid,click_count,last_clicked_at,
                quality_note,machine_scope,process_tags
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                f"{MOCK_PREFIX} {category}资料入口 {index + 1}", f"https://example.com/team-loop/mock/{index + 1}", category,
                "团队日常使用的看板、规范或协作资料入口。", creator["id"], now_iso(), 1 if index < 5 else 0,
                1 if index % 23 == 0 else 0, 20 + (index * 37) % 900, now_iso(), "Mock 数据，供列表和搜索体验使用。",
                json.dumps([f"MOCK-{index % 8 + 1:02d}"], ensure_ascii=False),
                json.dumps(["交接", "复盘", "看板"][0:1 + index % 3], ensure_ascii=False),
            ),
        )
    return 48


def seed_processes(conn: sqlite3.Connection, users: list[sqlite3.Row], today: dt.date, admin_id: int) -> tuple[int, int, int]:
    orgs = conn.execute("SELECT id,name FROM org_units WHERE active=1 ORDER BY id").fetchall()
    templates: list[tuple[int, list[tuple[int, int | None]]]] = []
    template_names = ["现场异常闭环", "版本发布检查", "质量问题复盘", "新机台导入", "夜班交接", "知识沉淀"]
    node_defs = [
        ("准备输入材料", None), ("确认责任人与范围", None), ("现场信息收集", 0), ("数据分析", 0),
        ("方案验证", 2), ("风险复核", 3), ("发布或执行", 4), ("结果确认", 6), ("复盘沉淀", 7),
    ]
    for index, name in enumerate(template_names):
        org = orgs[index % len(orgs)]
        cursor = conn.execute(
            "INSERT INTO process_templates(org_unit_id,name,description,active,version,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
            (org["id"], f"{MOCK_PREFIX} {name}", "包含并行分支和父子依赖的 Mock 流程模板。", 1, 1, admin_id, now_iso(), now_iso()),
        )
        template_id = cursor.lastrowid
        node_ids: list[int] = []
        mapping: list[tuple[int, int | None]] = []
        for sort_order, (node_title, parent_index) in enumerate(node_defs):
            parent_id = node_ids[parent_index] if parent_index is not None else None
            node_cursor = conn.execute(
                "INSERT INTO process_template_items(template_id,parent_item_id,title,description,required,sort_order) VALUES(?,?,?,?,?,?)",
                (template_id, parent_id, node_title, f"完成{name}中的“{node_title}”检查。", 0 if sort_order in (3, 5) else 1, sort_order),
            )
            node_ids.append(node_cursor.lastrowid)
            mapping.append((node_cursor.lastrowid, parent_index))
        templates.append((template_id, mapping))

    owners = [user for user in users if user["username"].startswith(USERNAME_PREFIX)]
    instance_count = instance_item_count = 0
    for index in range(72):
        template_id, template_nodes = templates[index % len(templates)]
        owner = owners[index % len(owners)]
        completed = index % 5 == 0
        status = "completed" if completed else "active"
        started = today - dt.timedelta(days=index % 45)
        cursor = conn.execute(
            """
            INSERT INTO process_instances(
                template_id,org_unit_id,owner_id,title,status,due_date,started_at,completed_at,active,version,created_by,created_at,updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                template_id, owner["org_unit_id"], owner["id"], f"{MOCK_PREFIX} {template_names[index % len(template_names)]} #{index + 1}", status,
                date_iso(started + dt.timedelta(days=14)), f"{started.isoformat()}T09:00:00",
                f"{(started + dt.timedelta(days=6)).isoformat()}T17:30:00" if completed else None, 1, 1, owner["id"],
                f"{started.isoformat()}T09:00:00", now_iso(),
            ),
        )
        instance_id = cursor.lastrowid
        created_nodes: list[int] = []
        for sort_order, (template_node_id, parent_index) in enumerate(template_nodes):
            template_node = conn.execute("SELECT * FROM process_template_items WHERE id=?", (template_node_id,)).fetchone()
            parent_item_id = created_nodes[parent_index] if parent_index is not None else None
            node_completed = int(completed or sort_order < index % 7)
            node_cursor = conn.execute(
                """
                INSERT INTO process_instance_items(
                    instance_id,template_item_id,parent_item_id,title,description,required,sort_order,completed,completed_at,completed_by,version
                ) VALUES(?,?,?,?,?,?,?,?,?,?,1)
                """,
                (
                    instance_id, template_node_id, parent_item_id, template_node["title"], template_node["description"], template_node["required"],
                    sort_order, node_completed, f"{(started + dt.timedelta(days=min(sort_order,6))).isoformat()}T17:00:00" if node_completed else None,
                    owner["id"] if node_completed else None,
                ),
            )
            created_nodes.append(node_cursor.lastrowid)
            instance_item_count += 1
        instance_count += 1
    return len(templates), instance_count, instance_item_count


def validate(conn: sqlite3.Connection, target_users: int) -> dict[str, int | str]:
    counts = {
        "active_users": conn.execute("SELECT COUNT(*) FROM users WHERE active=1").fetchone()[0],
        "mock_users": conn.execute("SELECT COUNT(*) FROM users WHERE active=1 AND username GLOB 'mock[0-9][0-9][0-9]'").fetchone()[0],
        "active_members": conn.execute("SELECT COUNT(*) FROM members m JOIN users u ON u.id=m.user_id WHERE m.active=1 AND u.active=1").fetchone()[0],
        "morning_items": conn.execute("SELECT COUNT(*) FROM morning_items WHERE title LIKE ?", (f"{MOCK_PREFIX}%",)).fetchone()[0],
        "forum_topics": conn.execute("SELECT COUNT(*) FROM team_posts WHERE title LIKE ?", (f"{MOCK_PREFIX}%",)).fetchone()[0],
        "meetings": conn.execute("SELECT COUNT(*) FROM meetings WHERE title LIKE ?", (f"{MOCK_PREFIX}%",)).fetchone()[0],
        "thank_you_votes": conn.execute("SELECT COUNT(*) FROM thank_you_votes WHERE evidence LIKE ?", (f"{MOCK_PREFIX}%",)).fetchone()[0],
        "scores": conn.execute("SELECT COUNT(*) FROM red_black_scores WHERE reason LIKE ?", (f"{MOCK_PREFIX}%",)).fetchone()[0],
        "shifts": conn.execute("SELECT COUNT(*) FROM shifts s JOIN machines m ON m.id=s.machine_id WHERE m.name LIKE 'MOCK-%'").fetchone()[0],
        "process_instances": conn.execute("SELECT COUNT(*) FROM process_instances WHERE title LIKE ?", (f"{MOCK_PREFIX}%",)).fetchone()[0],
        "moments": conn.execute("SELECT COUNT(*) FROM team_moments WHERE title LIKE ?", (f"{MOCK_PREFIX}%",)).fetchone()[0],
    }
    if counts["active_users"] != target_users:
        raise RuntimeError(f"活跃用户校验失败：{counts['active_users']} != {target_users}")
    over_limit = conn.execute(
        """
        SELECT v.voter_id,v.week_start,COUNT(*)
        FROM thank_you_votes v JOIN users u ON u.id=v.voter_id
        WHERE u.username GLOB 'mock[0-9][0-9][0-9]'
        GROUP BY v.voter_id,v.week_start HAVING COUNT(*)>3 LIMIT 1
        """
    ).fetchone()
    if over_limit:
        raise RuntimeError(f"Thank You 每周上限校验失败：{tuple(over_limit)}")
    self_vote = conn.execute(
        """
        SELECT v.id FROM thank_you_votes v JOIN users u ON u.id=v.voter_id
        WHERE u.username GLOB 'mock[0-9][0-9][0-9]' AND v.voter_id=v.receiver_id LIMIT 1
        """
    ).fetchone()
    if self_vote:
        raise RuntimeError(f"发现自我感谢记录：{self_vote['id']}")
    fk_errors = conn.execute("PRAGMA foreign_key_check").fetchall()
    if fk_errors:
        raise RuntimeError(f"外键校验失败：{fk_errors[:5]}")
    quick_check = conn.execute("PRAGMA quick_check").fetchone()[0]
    if quick_check != "ok":
        raise RuntimeError(f"数据库 quick_check 失败：{quick_check}")
    counts["quick_check"] = quick_check
    return counts


def main() -> int:
    args = parse_args()
    if not 10 <= args.target_users <= 1000:
        raise SystemExit("--target-users 必须在 10 到 1000 之间。")
    database = assert_gray_database(args.database)
    if args.dry_run:
        with sqlite3.connect(database) as conn:
            real_active = conn.execute("SELECT COUNT(*) FROM users WHERE active=1 AND username NOT GLOB 'mock[0-9][0-9][0-9]'").fetchone()[0]
        print(json.dumps({"database": str(database), "target_users": args.target_users, "real_active_users": real_active, "mock_users_needed": max(0, args.target_users - real_active)}, ensure_ascii=False, indent=2))
        return 0

    rng = random.Random(args.seed)
    today = dt.date.today()
    conn = sqlite3.connect(database, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA journal_mode=WAL")
    backup = backup_database(conn, database)
    summary: dict[str, object] = {"database": str(database), "backup": str(backup), "seed": args.seed}
    try:
        conn.execute("BEGIN IMMEDIATE")
        users = ensure_users(conn, args.target_users, args.password, rng)
        admin = next((user for user in users if user["role"] == "admin"), None)
        if not admin:
            raise RuntimeError("缺少活跃管理员，无法生成需管理员创建的业务数据。")
        seed_members(conn, users, rng)
        summary["morning_items_created"] = seed_morning(conn, users, rng, today)
        summary["forum_topics_created"], summary["forum_replies_created"] = seed_forum(conn, users, rng, today)
        summary["moments_created"], summary["moment_images_created"] = seed_moments(conn, users, rng, today)
        summary["thank_you_votes_created"] = seed_thanks(conn, users, rng, today)
        summary["scores_created"] = seed_scores(conn, users, rng, today, admin["id"])
        summary["meetings_created"], summary["meeting_items_created"], summary["attendance_created"] = seed_meetings(conn, users, rng, today, admin["id"])
        summary["machines_created"], summary["shifts_created"] = seed_shifts(conn, users, today, admin["id"])
        summary["links_created"] = seed_links(conn, users, today)
        summary["process_templates_created"], summary["process_instances_created"], summary["process_items_created"] = seed_processes(conn, users, today, admin["id"])
        conn.commit()
        summary["validation"] = validate(conn, args.target_users)
    except Exception:
        conn.rollback()
        conn.close()
        print(f"生成失败，数据库已回滚。写入前备份：{backup}", file=sys.stderr)
        raise
    finally:
        try:
            conn.close()
        except Exception:
            pass

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"Mock 登录账号：mock001 ~ mock{summary['validation']['mock_users']:03d}，统一密码：{args.password}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
