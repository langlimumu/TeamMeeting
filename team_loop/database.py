from .common import *

def ensure_column(conn, table, column, definition):
    columns = [row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()]
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def seed_meeting_topics(conn):
    count = conn.execute("SELECT COUNT(*) FROM meeting_topic_types").fetchone()[0]
    if count:
        return
    defaults = [
        ("进度同步", "#3370ff", ["本周完成", "下周计划", "里程碑风险"]),
        ("问题风险", "#f54a45", ["现场阻塞", "资源协调", "质量风险"]),
        ("技术复盘", "#00b578", ["故障案例", "经验沉淀", "标准优化"]),
        ("行动项", "#ff8f1f", ["待办分配", "截止确认", "关闭验收"]),
    ]
    for index, (name, color, options) in enumerate(defaults, start=1):
        cursor = conn.execute(
            "INSERT INTO meeting_topic_types(name, color, sort_order, active) VALUES(?,?,?,1)",
            (name, color, index),
        )
        type_id = cursor.lastrowid
        for option_index, title in enumerate(options, start=1):
            conn.execute(
                "INSERT INTO meeting_topic_options(type_id, title, default_detail, sort_order, active) VALUES(?,?,?,?,1)",
                (type_id, title, "", option_index),
            )


def seed_link_categories(conn):
    count = conn.execute("SELECT COUNT(*) FROM link_categories").fetchone()[0]
    if count:
        return
    for index, name in enumerate(["通用", "文档", "系统", "工具", "流程"], start=1):
        conn.execute(
            "INSERT INTO link_categories(name, sort_order, active, created_at) VALUES(?,?,1,?)",
            (name, index, now_iso()),
        )


def seed_system_settings(conn):
    for key, label, value, value_type, description in DEFAULT_SETTINGS:
        conn.execute(
            """
            INSERT OR IGNORE INTO system_settings(key, label, value, value_type, description, updated_at)
            VALUES(?,?,?,?,?,?)
            """,
            (key, label, value, value_type, description, now_iso()),
        )
        conn.execute(
            """
            UPDATE system_settings
            SET label=?, value_type=?, description=?
            WHERE key=?
            """,
            (label, value_type, description, key),
        )


def seed_user_types(conn):
    for key, name, description, sort_order, locked in SYSTEM_USER_TYPES:
        conn.execute(
            """
            INSERT OR IGNORE INTO user_types(key, name, description, sort_order, locked, active, created_at)
            VALUES(?,?,?,?,?,1,?)
            """,
            (key, name, description, sort_order, locked, now_iso()),
        )
        if key == GUEST_USER_TYPE_KEY:
            conn.execute(
                "UPDATE user_types SET name=?, description=?, sort_order=?, locked=1, active=1 WHERE key=?",
                (name, description, sort_order, key),
            )
    for type_key, modules in INITIAL_TYPE_OPERATIONS.items():
        for module_key, actions in modules.items():
            conn.execute(
                """
                INSERT OR IGNORE INTO module_permissions(
                    user_type_key, module_key, can_view, can_create, can_edit, can_delete, updated_at
                ) VALUES(?,?,?,?,?,?,?)
                """,
                (type_key, module_key, *actions, now_iso()),
            )


def normalize_org_slug(value):
    slug = re.sub(r"[^a-z0-9-]+", "-", str(value or "").strip().lower()).strip("-")
    if not slug or len(slug) > 48:
        raise AppError(400, "团队路由只能使用 1-48 位小写字母、数字和短横线")
    return slug


def organization_rows(conn, active_only=True):
    where = "WHERE o.active=1" if active_only else ""
    rows = rows_to_list(conn.execute(
        f"""
        SELECT o.*, p.name AS parent_name, t.name AS default_user_type_name,
               (SELECT COUNT(*) FROM users u WHERE u.org_unit_id=o.id AND u.active=1) AS user_count
        FROM org_units o
        LEFT JOIN org_units p ON p.id=o.parent_id
        LEFT JOIN user_types t ON t.key=o.default_user_type
        {where}
        ORDER BY o.sort_order, o.name, o.id
        """
    ).fetchall())
    lookup = {row["id"]: row for row in rows}
    path_cache = {}
    label_path_cache = {}

    def resolve_path(row_id, seen=None):
        if row_id in path_cache:
            return path_cache[row_id]
        row = lookup.get(row_id)
        if not row:
            return ""
        seen = set(seen or ())
        if row_id in seen:
            return row["slug"]
        seen.add(row_id)
        parent_path = resolve_path(row.get("parent_id"), seen) if row.get("parent_id") else ""
        path_cache[row_id] = "/".join(part for part in (parent_path, row["slug"]) if part)
        return path_cache[row_id]

    def resolve_label_path(row_id, seen=None):
        if row_id in label_path_cache:
            return label_path_cache[row_id]
        row = lookup.get(row_id)
        if not row:
            return ""
        seen = set(seen or ())
        if row_id in seen:
            return row["name"]
        seen.add(row_id)
        parent_path = resolve_label_path(row.get("parent_id"), seen) if row.get("parent_id") else ""
        label_path_cache[row_id] = " / ".join(part for part in (parent_path, row["name"]) if part)
        return label_path_cache[row_id]

    for row in rows:
        row["path"] = resolve_path(row["id"])
        row["label_path"] = resolve_label_path(row["id"])
        row["route"] = f"/org/{row['path']}"
        row["depth"] = max(0, row["path"].count("/"))
        try:
            groups = json.loads(row.get("sso_groups") or "[]")
        except json.JSONDecodeError:
            groups = []
        row["sso_groups"] = [str(group).strip() for group in groups if str(group).strip()]

    children = {}
    for row in rows:
        parent_id = row.get("parent_id") if row.get("parent_id") in lookup else None
        children.setdefault(parent_id, []).append(row)
    for siblings in children.values():
        siblings.sort(key=lambda item: (item.get("sort_order") or 0, item.get("name") or "", item["id"]))

    ordered = []

    def append_branch(parent_id):
        for child in children.get(parent_id, []):
            ordered.append(child)
            append_branch(child["id"])

    append_branch(None)
    if len(ordered) != len(rows):
        known = {row["id"] for row in ordered}
        ordered.extend(row for row in rows if row["id"] not in known)
    return ordered


def seed_organization_units(conn):
    if conn.execute("SELECT COUNT(*) FROM org_units").fetchone()[0]:
        return
    created = now_iso()
    cursor = conn.execute(
        """
        INSERT INTO org_units(name, slug, parent_id, visibility_mode, default_user_type, sso_groups, sort_order, active, created_at, updated_at)
        VALUES('ESS','ess',NULL,'all',?, '[]',10,1,?,?)
        """,
        (DEFAULT_USER_TYPE_KEY, created, created),
    )
    root_id = cursor.lastrowid
    second_level = {}
    for order, name in enumerate(("MO", "ES", "SN"), start=1):
        cursor = conn.execute(
            """
            INSERT INTO org_units(name, slug, parent_id, visibility_mode, default_user_type, sso_groups, sort_order, active, created_at, updated_at)
            VALUES(?,?,?,'subtree',?, '[]',?,1,?,?)
            """,
            (name, name.lower(), root_id, DEFAULT_USER_TYPE_KEY, order * 10, created, created),
        )
        second_level[name] = cursor.lastrowid
    for order, name in enumerate(("WS", "RS", "WH", "RH"), start=1):
        conn.execute(
            """
            INSERT INTO org_units(name, slug, parent_id, visibility_mode, default_user_type, sso_groups, sort_order, active, created_at, updated_at)
            VALUES(?,?,?,'unit',?, '[]',?,1,?,?)
            """,
            (name, name.lower(), second_level["MO"], DEFAULT_USER_TYPE_KEY, order * 10, created, created),
        )
    conn.execute("UPDATE users SET org_unit_id=? WHERE org_unit_id IS NULL", (root_id,))


def claim_path_value(claims, path):
    value = claims
    for part in str(path or "").split("."):
        if not part or not isinstance(value, dict):
            return None
        if part in value:
            value = value[part]
            continue
        matched_key = next((key for key in value if str(key).casefold() == part.casefold()), None)
        if matched_key is None:
            return None
        value = value[matched_key]
    return value


def sso_claim_sources(claims):
    sources = [claims]
    for key in ("data", "result", "user", "userInfo", "userinfo"):
        nested = claim_path_value(claims, key)
        if isinstance(nested, dict) and nested not in sources:
            sources.append(nested)
    return sources


def claim_values(claims, path):
    value = None
    for source in sso_claim_sources(claims):
        value = claim_path_value(source, path)
        if value not in (None, "", []):
            break
    if isinstance(value, (str, int)):
        raw_values = re.split(r"[,;]", str(value))
    elif isinstance(value, list):
        raw_values = value
    else:
        return []
    return [str(item).strip() for item in raw_values if str(item).strip()]


def match_sso_org_unit(conn, group_values):
    normalized = {str(value).strip().casefold() for value in group_values if str(value).strip()}
    units = organization_rows(conn)
    matches = [
        unit for unit in units
        if normalized.intersection(str(group).casefold() for group in unit.get("sso_groups", []))
    ]
    if matches:
        return sorted(matches, key=lambda unit: (-unit["depth"], unit["sort_order"], unit["id"]))[0]
    return None


def migrate_dynamic_user_types(conn):
    migration_key = "dynamic_user_types_v1"
    if conn.execute("SELECT key FROM schema_migrations WHERE key=?", (migration_key,)).fetchone():
        return

    legacy_internal = conn.execute("SELECT key FROM user_types WHERE key='internal'").fetchone()
    if legacy_internal:
        conn.execute(
            """
            INSERT OR REPLACE INTO module_permissions(
                user_type_key, module_key, can_view, can_create, can_edit, can_delete, updated_at
            )
            SELECT ?, module_key, can_view, can_create, can_edit, can_delete, ?
            FROM module_permissions WHERE user_type_key='internal'
            """,
            (DEFAULT_USER_TYPE_KEY, now_iso()),
        )
        conn.execute("UPDATE users SET user_type=? WHERE user_type='internal'", (DEFAULT_USER_TYPE_KEY,))
        conn.execute("DELETE FROM module_permissions WHERE user_type_key='internal'")
        conn.execute("UPDATE user_types SET active=0, locked=0 WHERE key='internal'")

    legacy_partner = conn.execute("SELECT key FROM user_types WHERE key='partner'").fetchone()
    if legacy_partner:
        assigned = conn.execute("SELECT COUNT(*) FROM users WHERE user_type='partner' AND active=1").fetchone()[0]
        if assigned:
            conn.execute(
                "UPDATE user_types SET name='受限用户类型', description='由旧权限配置迁移，可自由改名和调整权限。', locked=0, active=1 WHERE key='partner'"
            )
        else:
            conn.execute("DELETE FROM module_permissions WHERE user_type_key='partner'")
            conn.execute("UPDATE user_types SET active=0, locked=0 WHERE key='partner'")

    conn.execute(
        "INSERT INTO schema_migrations(key, applied_at) VALUES(?,?)",
        (migration_key, now_iso()),
    )


def migrate_operation_permissions(conn):
    migration_key = "operation_permissions_v1"
    if conn.execute("SELECT key FROM schema_migrations WHERE key=?", (migration_key,)).fetchone():
        return
    conn.execute("UPDATE module_permissions SET can_create=0, can_edit=0, can_delete=0")
    for type_key, modules in INITIAL_TYPE_OPERATIONS.items():
        for module_key, actions in modules.items():
            conn.execute(
                """
                INSERT INTO module_permissions(
                    user_type_key, module_key, can_view, can_create, can_edit, can_delete, updated_at
                ) VALUES(?,?,?,?,?,?,?)
                ON CONFLICT(user_type_key, module_key) DO UPDATE SET
                    can_view=excluded.can_view,
                    can_create=excluded.can_create,
                    can_edit=excluded.can_edit,
                    can_delete=excluded.can_delete,
                    updated_at=excluded.updated_at
                """,
                (type_key, module_key, *actions, now_iso()),
            )
    conn.execute(
        "INSERT INTO schema_migrations(key, applied_at) VALUES(?,?)",
        (migration_key, now_iso()),
    )


def migrate_team_moments_permissions(conn):
    migration_key = "team_moments_permissions_v1"
    if conn.execute("SELECT key FROM schema_migrations WHERE key=?", (migration_key,)).fetchone():
        return
    conn.execute(
        """
        INSERT INTO module_permissions(
            user_type_key, module_key, can_view, can_create, can_edit, can_delete, updated_at
        )
        SELECT user_type_key, 'moments', can_view, can_create, can_edit, can_delete, ?
        FROM module_permissions
        WHERE module_key='members'
        ON CONFLICT(user_type_key, module_key) DO NOTHING
        """,
        (now_iso(),),
    )
    conn.execute(
        """
        INSERT INTO module_permissions(
            user_type_key, module_key, can_view, can_create, can_edit, can_delete, updated_at
        ) VALUES(?, 'moments', 0, 0, 0, 0, ?)
        ON CONFLICT(user_type_key, module_key) DO UPDATE SET
            can_view=0, can_create=0, can_edit=0, can_delete=0, updated_at=excluded.updated_at
        """,
        (GUEST_USER_TYPE_KEY, now_iso()),
    )
    conn.execute(
        "INSERT INTO schema_migrations(key, applied_at) VALUES(?,?)",
        (migration_key, now_iso()),
    )


def seed_morning_items(conn):
    count = conn.execute("SELECT COUNT(*) FROM morning_items").fetchone()[0]
    if count:
        return
    users = conn.execute("SELECT id, display_name FROM users WHERE active=1 ORDER BY id LIMIT 4").fetchall()
    if not users:
        return
    samples = [
        ("TOPTB 夜班遗留闭环", "确认温控波动截图，上午同步是否需要补充复盘材料。", "doing", "high", "温控趋势需要王工确认", today_iso()),
        ("质量复盘模板更新", "整理红黑榜引用标准，让周会纪要可以直接复用。", "todo", "normal", "", today_iso()),
        ("现场报修跟进", "核对机台 A 报修工单状态，确认维修窗口。", "risk", "high", "等待供应商回复备件时间", today_iso()),
        ("常用链接梳理", "把高频看板和 SOP 链接置顶并补充关键词。", "done", "low", "", today_iso()),
    ]
    for index, sample in enumerate(samples):
        user = users[index % len(users)]
        cursor = conn.execute(
            """
            INSERT INTO morning_items(owner_id, item_date, title, detail, status, priority, blocker, due_date, updated_by, created_at, updated_at, active)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,1)
            """,
            (user["id"], sample[5], sample[0], sample[1], sample[2], sample[3], sample[4], sample[5], user["id"], now_iso(), now_iso()),
        )
        conn.execute("UPDATE morning_items SET root_id=? WHERE id=?", (cursor.lastrowid, cursor.lastrowid))


def seed_morning_history_samples(conn):
    existing = conn.execute("SELECT COUNT(*) FROM morning_items WHERE title LIKE '样例-%'").fetchone()[0]
    if existing:
        return
    users = conn.execute("SELECT id, display_name FROM users WHERE active=1 ORDER BY id LIMIT 6").fetchall()
    if not users:
        return
    chains = [
        {
            "owner": 0,
            "title": "样例-TOPTB 温控波动复盘",
            "priority": "high",
            "entries": [
                ("2026-06-30", "risk", "夜班出现两次温控上探，先确认报警截图和点检记录。", "需要王工补充趋势截图", "2026-07-01"),
                ("2026-07-01", "doing", "已拿到报警截图，等待白班复核实际温区影响。", "复核结论未同步", "2026-07-02"),
                ("2026-07-02", "done", "复核完成，波动来自测试台切换，已写入复盘模板。", "", "2026-07-02"),
            ],
        },
        {
            "owner": 1,
            "title": "样例-机台 A 报警截图补齐",
            "priority": "normal",
            "entries": [
                ("2026-07-01", "todo", "需要补齐 3 张报警截图，作为红黑榜事实依据。", "", "2026-07-03"),
                ("2026-07-02", "risk", "截图缺少夜班 02:30 的一张，先联系夜班补发。", "夜班截图未找到", "2026-07-03"),
                ("2026-07-03", "doing", "已补到 2 张，剩余 1 张从监控导出。", "监控导出权限待确认", "2026-07-04"),
                ("2026-07-04", "doing", "继续跟进监控导出权限，今天下班前确认。", "权限审批未完成", "2026-07-04"),
            ],
        },
        {
            "owner": 2,
            "title": "样例-SOP 点检表更新",
            "priority": "normal",
            "entries": [
                ("2026-07-02", "todo", "把老化测试台点检步骤补进 SOP 标准库。", "", "2026-07-03"),
                ("2026-07-03", "done", "SOP 已更新，常用链接里已补充入口。", "", "2026-07-03"),
            ],
        },
        {
            "owner": 3,
            "title": "样例-夜班交接问题跟踪",
            "priority": "high",
            "entries": [
                ("2026-07-03", "risk", "夜班交接记录有两处描述不一致，影响异常归因。", "交接口径不一致", "2026-07-04"),
                ("2026-07-04", "risk", "早会需要统一交接口径，并确定后续记录模板。", "缺少统一模板", "2026-07-04"),
            ],
        },
        {
            "owner": 4,
            "title": "样例-供应商备件到货确认",
            "priority": "high",
            "entries": [
                ("2026-07-01", "risk", "机台 B 备用传感器缺货，供应商未给明确到货时间。", "供应商回复不明确", "2026-07-04"),
                ("2026-07-04", "risk", "今天必须确认到货日期，否则排班要规避机台 B 风险窗口。", "到货日期未锁定", "2026-07-04"),
            ],
        },
        {
            "owner": 5,
            "title": "样例-常用链接关键词补充",
            "priority": "low",
            "entries": [
                ("2026-07-04", "todo", "给高频看板和 SOP 链接补充适用范围关键词。", "", "2026-07-05"),
            ],
        },
    ]
    for chain in chains:
        root_id = None
        previous_id = None
        previous_date = None
        owner = users[chain["owner"] % len(users)]
        for item_date, status, detail, blocker, due_date in chain["entries"]:
            cursor = conn.execute(
                """
                INSERT INTO morning_items(
                    owner_id, item_date, title, detail, status, priority, blocker, due_date,
                    root_id, carry_from_id, carried_from_date, updated_by, created_at, updated_at, active
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,1)
                """,
                (
                    owner["id"],
                    item_date,
                    chain["title"],
                    detail,
                    status,
                    chain["priority"],
                    blocker,
                    due_date,
                    root_id,
                    previous_id,
                    previous_date,
                    owner["id"],
                    f"{item_date}T08:30:00",
                    f"{item_date}T09:00:00",
                ),
            )
            if root_id is None:
                root_id = cursor.lastrowid
                conn.execute("UPDATE morning_items SET root_id=? WHERE id=?", (root_id, cursor.lastrowid))
            previous_id = cursor.lastrowid
            previous_date = item_date


def ensure_morning_carryover(conn, item_date):
    target_date = dt.date.fromisoformat(item_date)
    if target_date < dt.date.today():
        return 0
    source_items = rows_to_list(
        conn.execute(
            """
            SELECT i.*
            FROM morning_items i
            JOIN users owner ON owner.id=i.owner_id AND owner.active=1
            LEFT JOIN user_types owner_type ON owner_type.key=owner.user_type
            WHERE i.item_date < ?
              AND i.active=1
              AND i.status!='done'
              AND COALESCE(owner_type.include_in_morning, 1)=1
              AND NOT EXISTS (
                  SELECT 1
                  FROM morning_items newer
                  WHERE COALESCE(newer.root_id, newer.id)=COALESCE(i.root_id, i.id)
                    AND newer.item_date < ?
                    AND (
                        newer.item_date > i.item_date
                        OR (newer.item_date = i.item_date AND newer.id > i.id)
                    )
              )
            ORDER BY i.owner_id, i.id
            """,
            (item_date, item_date),
        ).fetchall()
    )
    carried_count = 0
    for item in source_items:
        root_id = item.get("root_id") or item["id"]
        exists = conn.execute(
            """
            SELECT id
            FROM morning_items
            WHERE item_date=? AND COALESCE(root_id, id)=?
            """,
            (item_date, root_id),
        ).fetchone()
        if exists:
            continue
        conn.execute(
            """
            INSERT INTO morning_items(
                owner_id, item_date, title, detail, status, priority, blocker, due_date,
                root_id, carry_from_id, carried_from_date, updated_by, created_at, updated_at, active
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,1)
            """,
            (
                item["owner_id"],
                item_date,
                item["title"],
                item.get("detail") or "",
                item["status"],
                item.get("priority") or "normal",
                item.get("blocker") or "",
                item.get("due_date") or item_date,
                root_id,
                item["id"],
                item["item_date"],
                item.get("updated_by"),
                now_iso(),
                now_iso(),
            ),
        )
        carried_count += 1
    return carried_count


def get_setting_value(conn, key, default=None):
    row = conn.execute("SELECT value FROM system_settings WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def get_int_setting(conn, key, default, minimum=None, maximum=None):
    try:
        value = int(get_setting_value(conn, key, default))
    except (TypeError, ValueError):
        value = int(default)
    if minimum is not None:
        value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return value


def get_float_setting(conn, key, default, minimum=None, maximum=None):
    try:
        value = float(get_setting_value(conn, key, default))
    except (TypeError, ValueError):
        value = float(default)
    if minimum is not None:
        value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return value


def sso_setting(conn, key, default=""):
    env_key = f"TEAM_LOOP_{key.upper()}"
    env_value = os.environ.get(env_key)
    if env_value is not None:
        return env_value.strip()
    return str(get_setting_value(conn, key, default) or "").strip()


def sso_configuration(conn):
    enabled = sso_setting(conn, "sso_enabled", "0").lower() in ("1", "true", "yes", "on", "启用")
    mode = sso_setting(conn, "sso_mode", "discovery").lower()
    if mode not in ("discovery", "manual"):
        mode = "discovery"
    return {
        "enabled": enabled,
        "auto_login": sso_setting(conn, "sso_auto_login", "1").lower() in ("1", "true", "yes", "on", "启用"),
        "mode": mode,
        "button_label": sso_setting(conn, "sso_button_label", "企业 SSO 登录") or "企业 SSO 登录",
        "issuer_url": sso_setting(conn, "sso_issuer_url").rstrip("/"),
        "authorization_url": sso_setting(conn, "sso_authorization_url"),
        "token_url": sso_setting(conn, "sso_token_url"),
        "userinfo_url": sso_setting(conn, "sso_userinfo_url"),
        "client_id": sso_setting(conn, "sso_client_id"),
        "client_secret": sso_setting(conn, "sso_client_secret"),
        "redirect_uri": sso_setting(conn, "sso_redirect_uri"),
        "scopes": sso_setting(conn, "sso_scopes", "openid profile email") or "openid profile email",
        "username_claim": sso_setting(conn, "sso_username_claim", "preferred_username") or "preferred_username",
        "display_name_claim": sso_setting(conn, "sso_display_name_claim", "name") or "name",
        "group_claim": sso_setting(conn, "sso_group_claim", "groups") or "groups",
        "default_user_type": GUEST_USER_TYPE_KEY,
        "auto_provision": sso_setting(conn, "sso_auto_provision", "1").lower() in ("1", "true", "yes", "on", "启用"),
    }


def sso_configuration_ready(config):
    return bool(config.get("enabled")) and not sso_missing_fields(config)


def sso_missing_fields(config):
    missing = []
    if not config.get("client_id"):
        missing.append("Client ID")
    if config.get("mode") == "manual":
        for key, label in (
            ("authorization_url", "OAuth2 认证地址"),
            ("token_url", "Access Token 地址"),
            ("userinfo_url", "UserInfo 地址"),
        ):
            if not config.get(key):
                missing.append(label)
    elif not config.get("issuer_url"):
        missing.append("OIDC Issuer 地址")
    return missing


def base64url_digest(value):
    digest = hashlib.sha256(value.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def claim_value(claims, path):
    for source in sso_claim_sources(claims):
        value = claim_path_value(source, path)
        if isinstance(value, (str, int)) and str(value).strip():
            return str(value).strip()
    return ""


SSO_USERNAME_FALLBACKS = (
    "userName", "username", "employee_id", "employeeNumber", "employee_no",
    "job_number", "preferred_username", "upn", "email", "id",
)

SSO_RETURN_VIEWS = {
    "members", "dashboard", "archive", "morning", "processes", "meetings",
    "shifts", "rules", "thanks", "links", "users", "system",
}


def sanitize_sso_return_to(value):
    raw = str(value or "").strip()
    if not raw:
        return ""
    if re.search(r"[\x00-\x1f\x7f\\]", raw):
        return ""
    parsed = urlparse(raw)
    if parsed.scheme or parsed.netloc or not parsed.path.startswith("/") or parsed.path.startswith("//"):
        return ""
    path = parsed.path.rstrip("/") or "/"
    if path != "/" and not re.fullmatch(r"/org/[a-zA-Z0-9._~-]+(?:/[a-zA-Z0-9._~-]+)*", path):
        return ""
    view = (parse_qs(parsed.query).get("view") or [""])[0].strip().lower()
    if view not in SSO_RETURN_VIEWS:
        return path
    return f"{path}?{urlencode({'view': view})}"


def append_sso_notice(return_to, key, value):
    target = sanitize_sso_return_to(return_to) or "/"
    parsed = urlparse(target)
    query = parse_qs(parsed.query, keep_blank_values=True)
    query[key] = [str(value)]
    return f"{parsed.path}?{urlencode(query, doseq=True)}"


def resolve_sso_identity(claims, config):
    employee_id = claim_value(claims, config.get("username_claim"))
    username_claim_used = config.get("username_claim") if employee_id else ""
    if not employee_id:
        for fallback in SSO_USERNAME_FALLBACKS:
            employee_id = claim_value(claims, fallback)
            if employee_id:
                username_claim_used = fallback
                break
    display_name = claim_value(claims, config.get("display_name_claim"))
    display_name_claim_used = config.get("display_name_claim") if display_name else ""
    if not display_name:
        for fallback in ("name", "displayName", "display_name", "realName", "userName", "username"):
            display_name = claim_value(claims, fallback)
            if display_name:
                display_name_claim_used = fallback
                break
    subject = claim_value(claims, "sub") or claim_value(claims, "id") or employee_id
    groups = claim_values(claims, config.get("group_claim") or "groups")
    return {
        "employee_id": employee_id.strip()[:120],
        "display_name": (display_name or employee_id).strip()[:120],
        "subject": subject.strip()[:240],
        "groups": groups[:100],
        "username_claim_used": username_claim_used,
        "display_name_claim_used": display_name_claim_used,
    }


def write_audit(conn, user, action, entity_type, entity_id=None, summary="", metadata=None, ip_address=""):
    user_id = user.get("id") if isinstance(user, dict) else user
    conn.execute(
        """
        INSERT INTO audit_logs(user_id, action, entity_type, entity_id, summary, metadata, ip_address, created_at)
        VALUES(?,?,?,?,?,?,?,?)
        """,
        (
            user_id,
            action,
            entity_type,
            entity_id,
            summary,
            json.dumps(metadata or {}, ensure_ascii=False),
            ip_address,
            now_iso(),
        ),
    )


def add_recycle_record(conn, entity_type, entity_id, title, user, payload=None):
    conn.execute(
        """
        INSERT INTO recycle_bin(entity_type, entity_id, title, payload, deleted_by, deleted_at, status)
        VALUES(?,?,?,?,?,?, 'deleted')
        """,
        (
            entity_type,
            entity_id,
            title or f"{entity_type} #{entity_id}",
            json.dumps(payload or {}, ensure_ascii=False),
            user["id"],
            now_iso(),
        ),
    )


def prune_old_backups(conn):
    retention_days = get_int_setting(conn, "backup_retention_days", 30, minimum=0, maximum=3650)
    if retention_days <= 0:
        return
    cutoff = dt.datetime.now() - dt.timedelta(days=retention_days)
    for row in conn.execute("SELECT id, filename, created_at FROM backups").fetchall():
        try:
            created_at = dt.datetime.fromisoformat(row["created_at"])
        except ValueError:
            continue
        if created_at >= cutoff:
            continue
        backup_path = BACKUP_DIR / row["filename"]
        if backup_path.exists():
            backup_path.unlink()
        conn.execute("DELETE FROM backups WHERE id=?", (row["id"],))


def create_database_backup(kind="manual", user_id=None):
    if not DB_PATH.exists():
        return None
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"weekly_team_{kind}_{stamp}.db"
    target = BACKUP_DIR / filename
    with sqlite3.connect(DB_PATH) as source, sqlite3.connect(target) as dest:
        source.backup(dest)
    size = target.stat().st_size
    with connect() as conn:
        cursor = conn.execute(
            "INSERT INTO backups(filename, size_bytes, kind, created_by, created_at) VALUES(?,?,?,?,?)",
            (filename, size, kind, user_id, now_iso()),
        )
        write_audit(
            conn,
            user_id,
            "backup.create",
            "backup",
            cursor.lastrowid,
            "自动备份已生成" if kind == "auto" else "手动备份已生成",
            {"filename": filename, "size_bytes": size, "kind": kind},
        )
        prune_old_backups(conn)
    return {"filename": filename, "size_bytes": size, "kind": kind}


def ensure_daily_backup():
    if not DB_PATH.exists():
        return
    with connect() as conn:
        enabled = get_setting_value(conn, "backup_auto_enabled", "1") != "0"
        if not enabled:
            return
        today_prefix = f"weekly_team_auto_{dt.datetime.now().strftime('%Y%m%d')}_"
        exists = conn.execute(
            "SELECT id FROM backups WHERE kind='auto' AND filename LIKE ? LIMIT 1",
            (f"{today_prefix}%",),
        ).fetchone()
    if exists:
        return
    if any(BACKUP_DIR.glob(f"{today_prefix}*.db")):
        return
    create_database_backup(kind="auto", user_id=None)


def default_member_title(role):
    return "管理员" if role == "admin" else "团队成员"


def sync_member_for_user(conn, user_id):
    user = conn.execute(
        "SELECT id, display_name, role, active FROM users WHERE id=?",
        (user_id,),
    ).fetchone()
    if not user:
        return
    members = conn.execute("SELECT id, title FROM members WHERE user_id=? ORDER BY id", (user_id,)).fetchall()
    if members:
        member = members[0]
        duplicate_ids = [row["id"] for row in members[1:]]
        if duplicate_ids:
            placeholders = ",".join("?" for _ in duplicate_ids)
            conn.execute(f"UPDATE members SET active=0 WHERE id IN ({placeholders})", duplicate_ids)
        title = member["title"] or default_member_title(user["role"])
        conn.execute(
            "UPDATE members SET name=?, title=?, active=? WHERE id=?",
            (user["display_name"], title, user["active"], member["id"]),
        )
        return
    conn.execute(
        "INSERT INTO members(user_id, name, avatar_url, title, responsibilities, tags, comment, created_at, active) VALUES(?,?,?,?,?,?,?,?,?)",
        (user["id"], user["display_name"], "", default_member_title(user["role"]), "", "[]", "", now_iso(), user["active"]),
    )


def sync_members_with_users(conn):
    for user in conn.execute("SELECT id FROM users").fetchall():
        sync_member_for_user(conn, user["id"])


def init_db():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with connect() as conn:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA wal_autocheckpoint = 1000")
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                employee_id TEXT,
                salt TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                display_name TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('admin', 'user')),
                user_type TEXT NOT NULL DEFAULT 'default',
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS user_types (
                key TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                sort_order INTEGER NOT NULL DEFAULT 0,
                locked INTEGER NOT NULL DEFAULT 0,
                active INTEGER NOT NULL DEFAULT 1,
                version INTEGER NOT NULL DEFAULT 1,
                include_in_members INTEGER NOT NULL DEFAULT 1,
                include_in_morning INTEGER NOT NULL DEFAULT 1,
                include_in_rules INTEGER NOT NULL DEFAULT 1,
                include_in_thanks INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS org_units (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                slug TEXT NOT NULL,
                parent_id INTEGER REFERENCES org_units(id),
                visibility_mode TEXT NOT NULL DEFAULT 'unit' CHECK(visibility_mode IN ('all', 'subtree', 'unit')),
                default_user_type TEXT REFERENCES user_types(key),
                sso_groups TEXT NOT NULL DEFAULT '[]',
                sort_order INTEGER NOT NULL DEFAULT 0,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS module_permissions (
                user_type_key TEXT NOT NULL REFERENCES user_types(key) ON DELETE CASCADE,
                module_key TEXT NOT NULL,
                can_view INTEGER NOT NULL DEFAULT 1,
                can_create INTEGER NOT NULL DEFAULT 1,
                can_edit INTEGER NOT NULL DEFAULT 1,
                can_delete INTEGER NOT NULL DEFAULT 1,
                updated_at TEXT NOT NULL,
                PRIMARY KEY(user_type_key, module_key)
            );

            CREATE TABLE IF NOT EXISTS members (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                name TEXT NOT NULL,
                avatar_url TEXT,
                title TEXT,
                responsibilities TEXT,
                tags TEXT NOT NULL DEFAULT '[]',
                comment TEXT,
                sort_order INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS member_posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                member_id INTEGER NOT NULL REFERENCES members(id) ON DELETE CASCADE,
                user_id INTEGER NOT NULL REFERENCES users(id),
                kind TEXT NOT NULL CHECK(kind IN ('comment', 'roast')),
                content TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS team_posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id),
                kind TEXT NOT NULL CHECK(kind IN ('comment', 'roast')),
                title TEXT,
                category TEXT NOT NULL DEFAULT 'general',
                status TEXT NOT NULL DEFAULT 'open',
                pinned INTEGER NOT NULL DEFAULT 0,
                view_count INTEGER NOT NULL DEFAULT 0,
                content TEXT NOT NULL,
                updated_at TEXT,
                deleted_at TEXT,
                deleted_by INTEGER REFERENCES users(id),
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS team_post_replies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                post_id INTEGER NOT NULL REFERENCES team_posts(id) ON DELETE CASCADE,
                parent_reply_id INTEGER REFERENCES team_post_replies(id) ON DELETE CASCADE,
                user_id INTEGER NOT NULL REFERENCES users(id),
                content TEXT NOT NULL,
                deleted_at TEXT,
                deleted_by INTEGER REFERENCES users(id),
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS team_post_reactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                post_id INTEGER NOT NULL REFERENCES team_posts(id) ON DELETE CASCADE,
                user_id INTEGER NOT NULL REFERENCES users(id),
                reaction TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(post_id, user_id, reaction)
            );

            CREATE TABLE IF NOT EXISTS team_reply_reactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                reply_id INTEGER NOT NULL REFERENCES team_post_replies(id) ON DELETE CASCADE,
                user_id INTEGER NOT NULL REFERENCES users(id),
                reaction TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(reply_id, user_id, reaction)
            );

            CREATE TABLE IF NOT EXISTS team_moments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                org_unit_id INTEGER NOT NULL REFERENCES org_units(id),
                title TEXT NOT NULL,
                story TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT 'milestone',
                event_date TEXT NOT NULL,
                created_by INTEGER NOT NULL REFERENCES users(id),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                deleted_at TEXT,
                deleted_by INTEGER REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS team_moment_images (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                moment_id INTEGER NOT NULL REFERENCES team_moments(id) ON DELETE CASCADE,
                filename TEXT NOT NULL,
                mime_type TEXT NOT NULL,
                image_data BLOB NOT NULL,
                sort_order INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS red_black_rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                kind TEXT NOT NULL CHECK(kind IN ('red', 'black')),
                content TEXT NOT NULL,
                effective_from TEXT,
                effective_to TEXT,
                active INTEGER NOT NULL DEFAULT 1,
                created_by INTEGER NOT NULL REFERENCES users(id),
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS red_black_scores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id),
                rule_id INTEGER REFERENCES red_black_rules(id) ON DELETE SET NULL,
                kind TEXT NOT NULL CHECK(kind IN ('red', 'black')),
                points INTEGER NOT NULL,
                reason TEXT NOT NULL,
                score_date TEXT NOT NULL,
                created_by INTEGER NOT NULL REFERENCES users(id),
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS meetings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                meeting_date TEXT NOT NULL,
                title TEXT NOT NULL,
                summary TEXT,
                status TEXT NOT NULL DEFAULT 'open',
                created_by INTEGER NOT NULL REFERENCES users(id),
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS meeting_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                meeting_id INTEGER NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
                section TEXT NOT NULL,
                title TEXT NOT NULL,
                detail TEXT,
                minutes TEXT,
                owner_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                status TEXT NOT NULL DEFAULT 'todo',
                due_date TEXT,
                created_by INTEGER NOT NULL REFERENCES users(id),
                deleted_at TEXT,
                deleted_by INTEGER REFERENCES users(id),
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS meeting_topic_types (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                color TEXT NOT NULL DEFAULT '#3370ff',
                sort_order INTEGER NOT NULL DEFAULT 0,
                active INTEGER NOT NULL DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS meeting_topic_options (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type_id INTEGER NOT NULL REFERENCES meeting_topic_types(id) ON DELETE CASCADE,
                title TEXT NOT NULL,
                default_detail TEXT,
                owner_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                recurrence_weeks INTEGER NOT NULL DEFAULT 1,
                recurrence_type TEXT NOT NULL DEFAULT 'weekly',
                recurrence_value TEXT NOT NULL DEFAULT '1',
                sort_order INTEGER NOT NULL DEFAULT 0,
                active INTEGER NOT NULL DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS meeting_topic_links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                meeting_id INTEGER NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
                type_id INTEGER NOT NULL REFERENCES meeting_topic_types(id) ON DELETE CASCADE,
                sort_order INTEGER NOT NULL DEFAULT 0,
                created_by INTEGER REFERENCES users(id),
                created_at TEXT NOT NULL,
                UNIQUE(meeting_id, type_id)
            );

            CREATE TABLE IF NOT EXISTS meeting_attendance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                meeting_id INTEGER NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
                user_id INTEGER NOT NULL REFERENCES users(id),
                status TEXT NOT NULL CHECK(status IN ('present', 'leave', 'absent', 'late')),
                donation_required INTEGER NOT NULL DEFAULT 0,
                donation_amount REAL NOT NULL DEFAULT 0,
                donation_done INTEGER NOT NULL DEFAULT 0,
                note TEXT,
                updated_by INTEGER NOT NULL REFERENCES users(id),
                updated_at TEXT NOT NULL,
                UNIQUE(meeting_id, user_id)
            );

            CREATE TABLE IF NOT EXISTS links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                url TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT '通用',
                description TEXT,
                pinned INTEGER NOT NULL DEFAULT 0,
                invalid INTEGER NOT NULL DEFAULT 0,
                click_count INTEGER NOT NULL DEFAULT 0,
                last_clicked_at TEXT,
                quality_note TEXT,
                machine_scope TEXT NOT NULL DEFAULT '[]',
                process_tags TEXT NOT NULL DEFAULT '[]',
                created_by INTEGER NOT NULL REFERENCES users(id),
                deleted_at TEXT,
                deleted_by INTEGER REFERENCES users(id),
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS recycle_bin (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entity_type TEXT NOT NULL,
                entity_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                payload TEXT NOT NULL DEFAULT '{}',
                deleted_by INTEGER NOT NULL REFERENCES users(id),
                deleted_at TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'deleted',
                resolved_by INTEGER REFERENCES users(id),
                resolved_at TEXT
            );

            CREATE TABLE IF NOT EXISTS reminder_reads (
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                reminder_key TEXT NOT NULL,
                read_at TEXT NOT NULL,
                PRIMARY KEY(user_id, reminder_key)
            );

            CREATE TABLE IF NOT EXISTS schema_migrations (
                key TEXT PRIMARY KEY,
                applied_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS link_categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                sort_order INTEGER NOT NULL DEFAULT 0,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS machines (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                description TEXT
            );

            CREATE TABLE IF NOT EXISTS shifts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                machine_id INTEGER NOT NULL REFERENCES machines(id),
                user_id INTEGER NOT NULL REFERENCES users(id),
                shift_type TEXT NOT NULL CHECK(shift_type IN ('day', 'night')),
                shift_date TEXT NOT NULL,
                hours REAL NOT NULL DEFAULT 12,
                note TEXT,
                created_by INTEGER NOT NULL REFERENCES users(id),
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS auth_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                token_hash TEXT NOT NULL UNIQUE,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                ip_address TEXT,
                user_agent TEXT,
                created_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                revoked_at TEXT
            );

            CREATE TABLE IF NOT EXISTS login_attempts (
                username TEXT NOT NULL,
                ip_address TEXT NOT NULL,
                failed_count INTEGER NOT NULL DEFAULT 0,
                window_started_at TEXT NOT NULL,
                locked_until TEXT,
                updated_at TEXT NOT NULL,
                PRIMARY KEY(username, ip_address)
            );

            CREATE TABLE IF NOT EXISTS sso_login_states (
                state_hash TEXT PRIMARY KEY,
                nonce TEXT NOT NULL,
                code_verifier TEXT NOT NULL,
                redirect_uri TEXT NOT NULL,
                return_to TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                used_at TEXT
            );

            CREATE TABLE IF NOT EXISTS thank_you_votes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                voter_id INTEGER NOT NULL REFERENCES users(id),
                receiver_id INTEGER NOT NULL REFERENCES users(id),
                week_start TEXT NOT NULL,
                evidence TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(voter_id, receiver_id, week_start)
            );

            CREATE TABLE IF NOT EXISTS morning_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_id INTEGER NOT NULL REFERENCES users(id),
                item_date TEXT NOT NULL,
                title TEXT NOT NULL,
                detail TEXT,
                status TEXT NOT NULL DEFAULT 'todo',
                priority TEXT NOT NULL DEFAULT 'normal',
                blocker TEXT,
                due_date TEXT,
                root_id INTEGER,
                carry_from_id INTEGER REFERENCES morning_items(id),
                carried_from_date TEXT,
                updated_by INTEGER REFERENCES users(id),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                version INTEGER NOT NULL DEFAULT 1,
                active INTEGER NOT NULL DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS process_templates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                org_unit_id INTEGER NOT NULL REFERENCES org_units(id),
                name TEXT NOT NULL,
                description TEXT,
                active INTEGER NOT NULL DEFAULT 1,
                version INTEGER NOT NULL DEFAULT 1,
                created_by INTEGER NOT NULL REFERENCES users(id),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS process_template_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                template_id INTEGER NOT NULL REFERENCES process_templates(id) ON DELETE CASCADE,
                parent_item_id INTEGER REFERENCES process_template_items(id) ON DELETE SET NULL,
                title TEXT NOT NULL,
                description TEXT,
                required INTEGER NOT NULL DEFAULT 1,
                sort_order INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS process_instances (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                template_id INTEGER REFERENCES process_templates(id),
                org_unit_id INTEGER NOT NULL REFERENCES org_units(id),
                owner_id INTEGER NOT NULL REFERENCES users(id),
                title TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active', 'completed', 'cancelled')),
                due_date TEXT,
                started_at TEXT NOT NULL,
                completed_at TEXT,
                active INTEGER NOT NULL DEFAULT 1,
                version INTEGER NOT NULL DEFAULT 1,
                created_by INTEGER NOT NULL REFERENCES users(id),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS process_instance_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                instance_id INTEGER NOT NULL REFERENCES process_instances(id) ON DELETE CASCADE,
                template_item_id INTEGER REFERENCES process_template_items(id) ON DELETE SET NULL,
                parent_item_id INTEGER REFERENCES process_instance_items(id) ON DELETE SET NULL,
                title TEXT NOT NULL,
                description TEXT,
                required INTEGER NOT NULL DEFAULT 1,
                sort_order INTEGER NOT NULL DEFAULT 0,
                completed INTEGER NOT NULL DEFAULT 0,
                completed_at TEXT,
                completed_by INTEGER REFERENCES users(id),
                version INTEGER NOT NULL DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS system_settings (
                key TEXT PRIMARY KEY,
                label TEXT NOT NULL,
                value TEXT NOT NULL,
                value_type TEXT NOT NULL DEFAULT 'text',
                description TEXT,
                updated_by INTEGER REFERENCES users(id),
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER REFERENCES users(id),
                action TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                entity_id INTEGER,
                summary TEXT,
                metadata TEXT,
                ip_address TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS backups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT NOT NULL UNIQUE,
                size_bytes INTEGER NOT NULL DEFAULT 0,
                kind TEXT NOT NULL CHECK(kind IN ('auto', 'manual')),
                created_by INTEGER REFERENCES users(id),
                created_at TEXT NOT NULL
            );
            """
        )
        ensure_column(conn, "users", "user_type", "TEXT NOT NULL DEFAULT 'default'")
        ensure_column(conn, "users", "auth_source", "TEXT NOT NULL DEFAULT 'local'")
        ensure_column(conn, "users", "external_subject", "TEXT")
        ensure_column(conn, "users", "employee_id", "TEXT")
        ensure_column(conn, "users", "org_unit_id", "INTEGER")
        ensure_column(conn, "users", "classification_pending", "INTEGER NOT NULL DEFAULT 0")
        ensure_column(conn, "users", "suggested_org_unit_id", "INTEGER")
        ensure_column(conn, "users", "sso_groups_json", "TEXT NOT NULL DEFAULT '[]'")
        ensure_column(conn, "users", "sso_last_login_at", "TEXT")
        ensure_column(conn, "sso_login_states", "return_to", "TEXT NOT NULL DEFAULT ''")
        ensure_column(conn, "user_types", "version", "INTEGER NOT NULL DEFAULT 1")
        ensure_column(conn, "user_types", "include_in_members", "INTEGER NOT NULL DEFAULT 1")
        ensure_column(conn, "user_types", "include_in_morning", "INTEGER NOT NULL DEFAULT 1")
        ensure_column(conn, "user_types", "include_in_rules", "INTEGER NOT NULL DEFAULT 1")
        ensure_column(conn, "user_types", "include_in_thanks", "INTEGER NOT NULL DEFAULT 1")
        ensure_column(conn, "members", "active", "INTEGER NOT NULL DEFAULT 1")
        ensure_column(conn, "members", "sort_order", "INTEGER NOT NULL DEFAULT 0")
        ensure_column(conn, "members", "skills", "TEXT NOT NULL DEFAULT '[]'")
        ensure_column(conn, "members", "machine_scope", "TEXT NOT NULL DEFAULT '[]'")
        ensure_column(conn, "members", "expertise", "TEXT")
        ensure_column(conn, "members", "backup_owner", "TEXT")
        ensure_column(conn, "members", "contact", "TEXT")
        ensure_column(conn, "module_permissions", "can_create", "INTEGER NOT NULL DEFAULT 1")
        ensure_column(conn, "module_permissions", "can_edit", "INTEGER NOT NULL DEFAULT 1")
        ensure_column(conn, "module_permissions", "can_delete", "INTEGER NOT NULL DEFAULT 1")
        ensure_column(conn, "team_post_replies", "parent_reply_id", "INTEGER")
        ensure_column(conn, "team_post_replies", "deleted_at", "TEXT")
        ensure_column(conn, "team_post_replies", "deleted_by", "INTEGER")
        ensure_column(conn, "team_posts", "title", "TEXT")
        ensure_column(conn, "team_posts", "category", "TEXT NOT NULL DEFAULT 'general'")
        ensure_column(conn, "team_posts", "status", "TEXT NOT NULL DEFAULT 'open'")
        ensure_column(conn, "team_posts", "pinned", "INTEGER NOT NULL DEFAULT 0")
        ensure_column(conn, "team_posts", "view_count", "INTEGER NOT NULL DEFAULT 0")
        ensure_column(conn, "team_posts", "updated_at", "TEXT")
        ensure_column(conn, "team_posts", "deleted_at", "TEXT")
        ensure_column(conn, "team_posts", "deleted_by", "INTEGER")
        ensure_column(conn, "team_posts", "org_unit_id", "INTEGER")
        ensure_column(conn, "links", "pinned", "INTEGER NOT NULL DEFAULT 0")
        ensure_column(conn, "links", "invalid", "INTEGER NOT NULL DEFAULT 0")
        ensure_column(conn, "links", "click_count", "INTEGER NOT NULL DEFAULT 0")
        ensure_column(conn, "links", "last_clicked_at", "TEXT")
        ensure_column(conn, "backups", "verify_status", "TEXT")
        ensure_column(conn, "backups", "verified_at", "TEXT")
        ensure_column(conn, "backups", "verify_message", "TEXT")
        ensure_column(conn, "backups", "restored_at", "TEXT")
        ensure_column(conn, "backups", "restored_by", "INTEGER")
        ensure_column(conn, "backups", "restore_message", "TEXT")
        ensure_column(conn, "links", "quality_note", "TEXT")
        ensure_column(conn, "links", "machine_scope", "TEXT NOT NULL DEFAULT '[]'")
        ensure_column(conn, "links", "process_tags", "TEXT NOT NULL DEFAULT '[]'")
        ensure_column(conn, "links", "deleted_at", "TEXT")
        ensure_column(conn, "links", "deleted_by", "INTEGER")
        ensure_column(conn, "meeting_items", "type_id", "INTEGER")
        ensure_column(conn, "meeting_items", "option_id", "INTEGER")
        ensure_column(conn, "meeting_items", "minutes", "TEXT")
        ensure_column(conn, "meeting_items", "open_issues", "TEXT")
        ensure_column(conn, "meeting_items", "next_steps", "TEXT")
        ensure_column(conn, "meeting_items", "deleted_at", "TEXT")
        ensure_column(conn, "meeting_items", "deleted_by", "INTEGER")
        ensure_column(conn, "meeting_items", "sort_order", "INTEGER NOT NULL DEFAULT 0")
        ensure_column(conn, "meeting_items", "duration_minutes", "INTEGER NOT NULL DEFAULT 10")
        ensure_column(conn, "meeting_items", "expected_output", "TEXT")
        ensure_column(conn, "meeting_items", "materials", "TEXT")
        ensure_column(conn, "meeting_items", "carried_from_id", "INTEGER")
        ensure_column(conn, "meetings", "start_time", "TEXT")
        ensure_column(conn, "meetings", "org_unit_id", "INTEGER")
        ensure_column(conn, "meeting_attendance", "donation_amount", "REAL NOT NULL DEFAULT 0")
        ensure_column(conn, "meeting_topic_options", "owner_id", "INTEGER")
        ensure_column(conn, "meeting_topic_options", "recurrence_weeks", "INTEGER NOT NULL DEFAULT 1")
        ensure_column(conn, "meeting_topic_options", "recurrence_type", "TEXT NOT NULL DEFAULT 'weekly'")
        ensure_column(conn, "meeting_topic_options", "recurrence_value", "TEXT NOT NULL DEFAULT '1'")
        ensure_column(conn, "meeting_topic_options", "duration_minutes", "INTEGER NOT NULL DEFAULT 10")
        ensure_column(conn, "meeting_topic_options", "expected_output", "TEXT")
        ensure_column(conn, "meeting_topic_options", "materials", "TEXT")
        ensure_column(conn, "morning_items", "priority", "TEXT NOT NULL DEFAULT 'normal'")
        ensure_column(conn, "morning_items", "blocker", "TEXT")
        ensure_column(conn, "morning_items", "due_date", "TEXT")
        ensure_column(conn, "morning_items", "root_id", "INTEGER")
        ensure_column(conn, "morning_items", "carry_from_id", "INTEGER")
        ensure_column(conn, "morning_items", "carried_from_date", "TEXT")
        ensure_column(conn, "morning_items", "updated_by", "INTEGER")
        ensure_column(conn, "morning_items", "updated_at", "TEXT")
        ensure_column(conn, "morning_items", "version", "INTEGER NOT NULL DEFAULT 1")
        ensure_column(conn, "morning_items", "active", "INTEGER NOT NULL DEFAULT 1")
        ensure_column(conn, "process_template_items", "parent_item_id", "INTEGER")
        ensure_column(conn, "process_instance_items", "parent_item_id", "INTEGER")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_auth_sessions_user_active ON auth_sessions(user_id, revoked_at, expires_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_auth_sessions_token ON auth_sessions(token_hash)")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_auth_identity ON users(auth_source, external_subject) WHERE external_subject IS NOT NULL AND external_subject<>''")
        conn.execute("UPDATE users SET employee_id=username WHERE employee_id IS NULL OR trim(employee_id)=''")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_employee_id ON users(employee_id COLLATE NOCASE) WHERE employee_id IS NOT NULL AND trim(employee_id)<>''")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_org_units_parent_slug ON org_units(COALESCE(parent_id, 0), slug) WHERE active=1")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_users_org_unit ON users(org_unit_id, active)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_sso_states_expiry ON sso_login_states(expires_at, used_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_shifts_user_date ON shifts(user_id, shift_date)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_team_posts_activity ON team_posts(pinned, updated_at, created_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_team_posts_org ON team_posts(org_unit_id, deleted_at, updated_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_team_moments_org_date ON team_moments(org_unit_id, deleted_at, event_date DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_team_moment_images_moment ON team_moment_images(moment_id, sort_order, id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_meetings_org_date ON meetings(org_unit_id, meeting_date)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_process_templates_org ON process_templates(org_unit_id, active, updated_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_process_instances_owner ON process_instances(owner_id, status, active, updated_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_process_instances_org ON process_instances(org_unit_id, status, active, updated_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_process_instance_items ON process_instance_items(instance_id, sort_order)")
        conn.execute("UPDATE team_posts SET title=substr(content, 1, 40) WHERE title IS NULL OR trim(title)=''")
        conn.execute("UPDATE team_posts SET category=CASE WHEN kind='roast' THEN 'roast' ELSE 'general' END WHERE category IS NULL OR trim(category)=''")
        conn.execute("UPDATE team_posts SET status='open' WHERE status IS NULL OR trim(status)=''")
        conn.execute("UPDATE team_posts SET updated_at=created_at WHERE updated_at IS NULL OR trim(updated_at)=''")
        conn.execute("UPDATE meeting_topic_options SET recurrence_type='weekly' WHERE recurrence_type IS NULL OR recurrence_type=''")
        conn.execute("UPDATE meeting_topic_options SET recurrence_value=CAST(COALESCE(recurrence_weeks, 1) AS TEXT) WHERE recurrence_value IS NULL OR recurrence_value=''")
        conn.execute("UPDATE meeting_topic_options SET recurrence_value=CAST(COALESCE(recurrence_weeks, 1) AS TEXT) WHERE recurrence_type='weekly'")
        conn.execute("UPDATE meetings SET status='scheduled' WHERE status='open' OR status IS NULL OR status=''")
        conn.execute("UPDATE meetings SET status='completed' WHERE status='closed'")
        conn.execute("UPDATE meeting_items SET sort_order=id WHERE sort_order IS NULL OR sort_order=0")
        conn.execute("UPDATE users SET user_type=? WHERE user_type IS NULL OR user_type=''", (DEFAULT_USER_TYPE_KEY,))
        root_org = conn.execute("SELECT id FROM org_units WHERE active=1 AND parent_id IS NULL ORDER BY sort_order, id LIMIT 1").fetchone()
        if root_org:
            conn.execute("UPDATE users SET org_unit_id=? WHERE org_unit_id IS NULL", (root_org["id"],))
            conn.execute("UPDATE team_posts SET org_unit_id=(SELECT org_unit_id FROM users WHERE users.id=team_posts.user_id) WHERE org_unit_id IS NULL")
            conn.execute("UPDATE meetings SET org_unit_id=(SELECT org_unit_id FROM users WHERE users.id=meetings.created_by) WHERE org_unit_id IS NULL")
        conn.execute("UPDATE members SET sort_order=id WHERE sort_order IS NULL OR sort_order=0")
        conn.execute("UPDATE morning_items SET updated_at=created_at WHERE updated_at IS NULL OR updated_at=''")
        conn.execute("UPDATE morning_items SET root_id=id WHERE root_id IS NULL")
        seed_meeting_topics(conn)
        seed_link_categories(conn)
        seed_system_settings(conn)
        seed_user_types(conn)
        seed_organization_units(conn)
        conn.execute(
            """
            UPDATE system_settings
            SET label='SSO 新用户初始权限', value=?,
                description='自动创建的 SSO 用户先使用访客只读权限，等待管理员分类'
            WHERE key='sso_default_user_type'
            """,
            (GUEST_USER_TYPE_KEY,),
        )
        conn.execute(
            """
            UPDATE user_types
            SET include_in_members=0, include_in_morning=0, include_in_rules=0, include_in_thanks=0
            WHERE key=?
            """,
            (GUEST_USER_TYPE_KEY,),
        )
        migrate_dynamic_user_types(conn)
        migrate_operation_permissions(conn)
        migrate_team_moments_permissions(conn)
        count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        if count == 0:
            admin_salt, admin_hash = make_hash("admin123")
            user_salt, user_hash = make_hash("user123")
            conn.execute(
                "INSERT INTO users(username, employee_id, salt, password_hash, display_name, role, user_type, created_at) VALUES(?,?,?,?,?,?,?,?)",
                ("admin", "admin", admin_salt, admin_hash, "管理员", "admin", DEFAULT_USER_TYPE_KEY, now_iso()),
            )
            conn.execute(
                "INSERT INTO users(username, employee_id, salt, password_hash, display_name, role, user_type, created_at) VALUES(?,?,?,?,?,?,?,?)",
                ("user", "user", user_salt, user_hash, "示例成员", "user", DEFAULT_USER_TYPE_KEY, now_iso()),
            )
            conn.execute(
                "INSERT INTO machines(name, description) VALUES(?, ?)",
                ("机台 A", "默认示例机台，可在管理员视图中维护"),
            )
            conn.execute(
                "INSERT INTO machines(name, description) VALUES(?, ?)",
                ("机台 B", "默认示例机台，可在管理员视图中维护"),
            )
            conn.execute(
                "INSERT INTO members(user_id, name, avatar_url, title, responsibilities, tags, comment, created_at) VALUES(?,?,?,?,?,?,?,?)",
                (1, "管理员", "", "项目负责人", "周例会组织、规则维护、资源协调", json.dumps(["统筹", "规则"], ensure_ascii=False), "负责让团队信息流动起来。", now_iso()),
            )
            conn.execute(
                "INSERT INTO members(user_id, name, avatar_url, title, responsibilities, tags, comment, created_at) VALUES(?,?,?,?,?,?,?,?)",
                (2, "示例成员", "", "技术成员", "问题跟进、现场支持、经验沉淀", json.dumps(["执行", "现场"], ensure_ascii=False), "一线问题的主要贡献者。", now_iso()),
            )
        root_org = conn.execute("SELECT id FROM org_units WHERE active=1 AND parent_id IS NULL ORDER BY sort_order, id LIMIT 1").fetchone()
        if root_org:
            conn.execute("UPDATE users SET org_unit_id=? WHERE org_unit_id IS NULL", (root_org["id"],))
        seed_morning_items(conn)
        seed_morning_history_samples(conn)
        sync_members_with_users(conn)


