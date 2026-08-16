from ..permissions import *


class SystemHandlerMixin:
    def list_recycle_bin(self):
        self.require_admin()
        with connect() as conn:
            items = rows_to_list(
                conn.execute(
                    """
                    SELECT r.*, u.display_name AS deleted_by_name
                    FROM recycle_bin r
                    LEFT JOIN users u ON u.id=r.deleted_by
                    WHERE r.status='deleted'
                    ORDER BY r.deleted_at DESC, r.id DESC
                    """
                ).fetchall()
            )
        labels = {
            "user": "用户",
            "link": "常用链接",
            "team_post": "讨论主题",
            "team_reply": "团队回复",
            "meeting_item": "会议议题",
            "team_moment": "团队时刻",
        }
        for item in items:
            item["entity_label"] = labels.get(item["entity_type"], item["entity_type"])
            try:
                item["payload"] = json.loads(item.get("payload") or "{}")
            except json.JSONDecodeError:
                item["payload"] = {}
            item["can_purge"] = item["entity_type"] != "user"
        return items

    def restore_recycle_item(self, recycle_id):
        admin = self.require_admin()
        with connect() as conn:
            item = conn.execute(
                "SELECT * FROM recycle_bin WHERE id=? AND status='deleted'",
                (recycle_id,),
            ).fetchone()
            if not item:
                raise AppError(404, "回收站记录不存在")
            payload = json.loads(item["payload"] or "{}")
            entity_type = item["entity_type"]
            if entity_type == "link":
                conn.execute("UPDATE links SET deleted_at=NULL, deleted_by=NULL WHERE id=?", (item["entity_id"],))
            elif entity_type == "meeting_item":
                conn.execute("UPDATE meeting_items SET deleted_at=NULL, deleted_by=NULL WHERE id=?", (item["entity_id"],))
            elif entity_type == "team_post":
                conn.execute("UPDATE team_posts SET deleted_at=NULL, deleted_by=NULL WHERE id=?", (item["entity_id"],))
            elif entity_type == "team_reply":
                reply_ids = [int(value) for value in payload.get("reply_ids") or [item["entity_id"]]]
                placeholders = ",".join("?" for _ in reply_ids)
                conn.execute(
                    f"UPDATE team_post_replies SET deleted_at=NULL, deleted_by=NULL WHERE id IN ({placeholders})",
                    reply_ids,
                )
            elif entity_type == "team_moment":
                conn.execute("UPDATE team_moments SET deleted_at=NULL, deleted_by=NULL WHERE id=?", (item["entity_id"],))
            elif entity_type == "user":
                conn.execute("UPDATE users SET active=1 WHERE id=?", (item["entity_id"],))
                conn.execute("UPDATE members SET active=1 WHERE user_id=?", (item["entity_id"],))
            else:
                raise AppError(400, "该类型暂不支持恢复")
            conn.execute(
                "UPDATE recycle_bin SET status='restored', resolved_by=?, resolved_at=? WHERE id=?",
                (admin["id"], now_iso(), recycle_id),
            )
            write_audit(conn, admin, "recycle.restore", entity_type, item["entity_id"], "回收站内容已恢复", {"recycle_id": recycle_id}, self.client_address[0])
        return {"message": "内容已恢复", "items": self.list_recycle_bin()}

    def purge_recycle_item(self, recycle_id):
        admin = self.require_admin()
        with connect() as conn:
            item = conn.execute(
                "SELECT * FROM recycle_bin WHERE id=? AND status='deleted'",
                (recycle_id,),
            ).fetchone()
            if not item:
                raise AppError(404, "回收站记录不存在")
            if item["entity_type"] == "user":
                raise AppError(400, "用户历史记录需要保留，只能停用或恢复账号")
            payload = json.loads(item["payload"] or "{}")
            if item["entity_type"] == "link":
                conn.execute("DELETE FROM links WHERE id=?", (item["entity_id"],))
            elif item["entity_type"] == "meeting_item":
                conn.execute("DELETE FROM meeting_items WHERE id=?", (item["entity_id"],))
            elif item["entity_type"] == "team_post":
                conn.execute("DELETE FROM team_posts WHERE id=?", (item["entity_id"],))
            elif item["entity_type"] == "team_reply":
                reply_ids = [int(value) for value in payload.get("reply_ids") or [item["entity_id"]]]
                placeholders = ",".join("?" for _ in reply_ids)
                conn.execute(f"DELETE FROM team_reply_reactions WHERE reply_id IN ({placeholders})", reply_ids)
                conn.execute(f"DELETE FROM team_post_replies WHERE id IN ({placeholders})", reply_ids)
            elif item["entity_type"] == "team_moment":
                conn.execute("DELETE FROM team_moments WHERE id=?", (item["entity_id"],))
            else:
                raise AppError(400, "该类型暂不支持彻底删除")
            conn.execute(
                "UPDATE recycle_bin SET status='purged', resolved_by=?, resolved_at=? WHERE id=?",
                (admin["id"], now_iso(), recycle_id),
            )
            write_audit(conn, admin, "recycle.purge", item["entity_type"], item["entity_id"], "回收站内容已彻底删除", {"recycle_id": recycle_id}, self.client_address[0])
        return {"message": "内容已彻底删除", "items": self.list_recycle_bin()}

    def can_view_module(self, user, module_key):
        try:
            self.require_module(user, module_key, "view")
            return True
        except AppError:
            return False

    def archive_years(self, user):
        sources = [
            ("meetings", "会议", "meetings", "meeting_date", "1=1"),
            ("meeting_items", "会议议题", "meeting_items", "created_at", "deleted_at IS NULL"),
            ("team_posts", "团队讨论", "team_posts", "created_at", "deleted_at IS NULL"),
            ("team_replies", "团队回复", "team_post_replies", "created_at", "deleted_at IS NULL AND post_id IN (SELECT id FROM team_posts WHERE deleted_at IS NULL)"),
            ("moments", "团队时刻", "team_moments", "event_date", "deleted_at IS NULL"),
            ("morning", "早例会事项", "morning_items", "item_date", "active=1"),
        ]
        allowed = {
            "meetings": self.can_view_module(user, "meetings"),
            "meeting_items": self.can_view_module(user, "meetings"),
            "team_posts": self.can_view_module(user, "members"),
            "team_replies": self.can_view_module(user, "members"),
            "moments": self.can_view_module(user, "moments"),
            "morning": self.can_view_module(user, "morning"),
        }
        year_map = {}
        with connect() as conn:
            for key, label, table, date_col, where in sources:
                if not allowed.get(key):
                    continue
                rows = conn.execute(
                    f"""
                    SELECT substr({date_col}, 1, 4) AS year, COUNT(*) AS count
                    FROM {table}
                    WHERE {where} AND {date_col} IS NOT NULL AND length({date_col}) >= 4
                    GROUP BY substr({date_col}, 1, 4)
                    """
                ).fetchall()
                for row in rows:
                    year = row["year"]
                    if not year or not str(year).isdigit():
                        continue
                    bucket = year_map.setdefault(year, {"year": year, "total": 0, "types": {}})
                    bucket["types"][key] = {"label": label, "count": row["count"]}
                    bucket["total"] += int(row["count"] or 0)
        return {"years": sorted(year_map.values(), key=lambda item: item["year"], reverse=True)}

    def search_archive(self, user, query):
        keyword = (query.get("keyword") or [""])[0].strip()
        year = (query.get("year") or [""])[0].strip()
        type_filter = (query.get("type") or ["all"])[0].strip() or "all"
        limit = min(80, max(10, int((query.get("limit") or ["40"])[0] or 40)))
        if len(keyword) > 80:
            raise AppError(400, "搜索关键词最多 80 个字符")
        if year and (not year.isdigit() or len(year) != 4):
            raise AppError(400, "年份格式不正确")
        allowed_types = {"all", "meetings", "meeting_items", "team_posts", "team_replies", "moments", "morning"}
        if type_filter not in allowed_types:
            type_filter = "all"
        like = f"%{keyword}%"
        results = []

        def wants(item_type):
            return type_filter == "all" or type_filter == item_type

        def in_year(column):
            return f" AND substr({column}, 1, 4)=?" if year else ""

        def add_result(item_type, label, item_id, title, body, item_date, owner="", module=""):
            text = " ".join([str(title or ""), str(body or ""), str(owner or "")]).strip()
            if keyword and keyword.lower() not in text.lower():
                return
            results.append({
                "type": item_type,
                "type_label": label,
                "id": item_id,
                "title": title or label,
                "body": (body or "")[:500],
                "date": item_date or "",
                "owner": owner or "",
                "module": module,
            })

        with connect() as conn:
            if wants("meetings") and self.can_view_module(user, "meetings"):
                params = []
                where = "1=1"
                if keyword:
                    where += " AND (m.title LIKE ? OR COALESCE(m.summary, '') LIKE ?)"
                    params.extend([like, like])
                if year:
                    where += in_year("m.meeting_date")
                    params.append(year)
                rows = rows_to_list(conn.execute(
                    f"""
                    SELECT m.id, m.title, m.summary, m.meeting_date, u.display_name AS owner
                    FROM meetings m
                    LEFT JOIN users u ON u.id = m.created_by
                    WHERE {where}
                    ORDER BY m.meeting_date DESC, m.id DESC
                    LIMIT ?
                    """,
                    [*params, limit],
                ).fetchall())
                for row in rows:
                    add_result("meetings", "会议", row["id"], row["title"], row.get("summary"), row["meeting_date"], row.get("owner"), "meetings")

            if wants("meeting_items") and self.can_view_module(user, "meetings"):
                params = []
                where = "i.deleted_at IS NULL"
                if keyword:
                    where += " AND (i.title LIKE ? OR COALESCE(i.detail, '') LIKE ? OR COALESCE(i.minutes, '') LIKE ? OR COALESCE(i.open_issues, '') LIKE ? OR COALESCE(i.next_steps, '') LIKE ?)"
                    params.extend([like, like, like, like, like])
                if year:
                    where += in_year("m.meeting_date")
                    params.append(year)
                rows = rows_to_list(conn.execute(
                    f"""
                    SELECT i.id, i.title, i.detail, i.minutes, i.open_issues, i.next_steps, m.meeting_date, COALESCE(u.display_name, '') AS owner
                    FROM meeting_items i
                    JOIN meetings m ON m.id = i.meeting_id
                    LEFT JOIN users u ON u.id = i.owner_id
                    WHERE {where}
                    ORDER BY m.meeting_date DESC, i.id DESC
                    LIMIT ?
                    """,
                    [*params, limit],
                ).fetchall())
                for row in rows:
                    body = "；".join(filter(None, [row.get("detail"), row.get("minutes"), row.get("open_issues"), row.get("next_steps")]))
                    add_result("meeting_items", "会议议题", row["id"], row["title"], body, row["meeting_date"], row.get("owner"), "meetings")

            if wants("team_posts") and self.can_view_module(user, "members"):
                params = []
                where = "p.deleted_at IS NULL"
                if keyword:
                    where += " AND (COALESCE(p.title, '') LIKE ? OR p.content LIKE ? OR COALESCE(p.category, '') LIKE ? OR u.display_name LIKE ?)"
                    params.extend([like, like, like, like])
                if year:
                    where += in_year("p.created_at")
                    params.append(year)
                rows = rows_to_list(conn.execute(
                    f"""
                    SELECT p.id, p.kind, p.category, p.title, p.content, p.created_at, u.display_name AS owner
                    FROM team_posts p
                    JOIN users u ON u.id = p.user_id
                    WHERE {where}
                    ORDER BY p.created_at DESC, p.id DESC
                    LIMIT ?
                    """,
                    [*params, limit],
                ).fetchall())
                for row in rows:
                    add_result("team_posts", "团队讨论", row["id"], row.get("title") or row.get("category") or "讨论主题", row["content"], row["created_at"], row.get("owner"), "members")

            if wants("team_replies") and self.can_view_module(user, "members"):
                params = []
                where = "r.deleted_at IS NULL AND p.deleted_at IS NULL"
                if keyword:
                    where += " AND (r.content LIKE ? OR u.display_name LIKE ?)"
                    params.extend([like, like])
                if year:
                    where += in_year("r.created_at")
                    params.append(year)
                rows = rows_to_list(conn.execute(
                    f"""
                    SELECT r.id, r.content, r.created_at, u.display_name AS owner
                    FROM team_post_replies r
                    JOIN team_posts p ON p.id = r.post_id
                    JOIN users u ON u.id = r.user_id
                    WHERE {where}
                    ORDER BY r.created_at DESC, r.id DESC
                    LIMIT ?
                    """,
                    [*params, limit],
                ).fetchall())
                for row in rows:
                    add_result("team_replies", "团队回复", row["id"], "回复", row["content"], row["created_at"], row.get("owner"), "members")

            if wants("moments") and self.can_view_module(user, "moments"):
                org_where, org_params = self.organization_current_entity_filter(conn, "m.org_unit_id", user)
                params = list(org_params)
                where = f"m.deleted_at IS NULL AND {org_where}"
                if keyword:
                    where += " AND (m.title LIKE ? OR m.story LIKE ? OR u.display_name LIKE ?)"
                    params.extend([like, like, like])
                if year:
                    where += in_year("m.event_date")
                    params.append(year)
                rows = rows_to_list(conn.execute(
                    f"""
                    SELECT m.id, m.title, m.story, m.event_date, u.display_name AS owner
                    FROM team_moments m
                    JOIN users u ON u.id=m.created_by
                    WHERE {where}
                    ORDER BY m.event_date DESC, m.id DESC
                    LIMIT ?
                    """,
                    [*params, limit],
                ).fetchall())
                for row in rows:
                    add_result("moments", "团队时刻", row["id"], row["title"], row["story"], row["event_date"], row.get("owner"), "moments")

            if wants("morning") and self.can_view_module(user, "morning"):
                params = []
                where = "i.active=1"
                if keyword:
                    where += " AND (i.title LIKE ? OR COALESCE(i.detail, '') LIKE ? OR COALESCE(i.blocker, '') LIKE ? OR u.display_name LIKE ?)"
                    params.extend([like, like, like, like])
                if year:
                    where += in_year("i.item_date")
                    params.append(year)
                rows = rows_to_list(conn.execute(
                    f"""
                    SELECT i.id, i.title, i.detail, i.blocker, i.item_date, u.display_name AS owner
                    FROM morning_items i
                    JOIN users u ON u.id = i.owner_id
                    WHERE {where}
                    ORDER BY i.item_date DESC, i.id DESC
                    LIMIT ?
                    """,
                    [*params, limit],
                ).fetchall())
                for row in rows:
                    body = "；".join(filter(None, [row.get("detail"), row.get("blocker")]))
                    add_result("morning", "早例会事项", row["id"], row["title"], body, row["item_date"], row.get("owner"), "morning")

        results.sort(key=lambda item: (item.get("date") or "", item.get("id") or 0), reverse=True)
        return {"results": results[:limit], "keyword": keyword, "year": year, "type": type_filter}

    def backup_path_from_payload(self):
        data = read_json(self)
        filename = (data.get("filename") or "").strip()
        if not filename or "/" in filename or "\\" in filename or not filename.endswith(".db"):
            raise AppError(400, "备份文件名不合法")
        file_path = (BACKUP_DIR / filename).resolve()
        if BACKUP_DIR.resolve() not in file_path.parents or not file_path.exists():
            raise AppError(404, "备份文件不存在")
        return filename, file_path

    def inspect_backup_file(self, file_path):
        required_tables = ["users", "members", "meetings", "meeting_items", "team_posts", "morning_items", "backups"]
        try:
            with sqlite3.connect(file_path) as conn:
                conn.row_factory = sqlite3.Row
                quick_check = conn.execute("PRAGMA quick_check").fetchone()[0]
                if quick_check != "ok":
                    return False, f"完整性检查失败：{quick_check}", {}
                tables = {
                    row["name"]
                    for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
                }
                missing = [table for table in required_tables if table not in tables]
                if missing:
                    return False, f"缺少关键表：{', '.join(missing)}", {}
                counts = {
                    table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                    for table in required_tables
                }
                return True, "备份可正常打开，关键表完整", counts
        except sqlite3.Error as exc:
            return False, f"备份无法读取：{exc}", {}

    def update_backup_check_result(self, filename, ok, message, extra=None):
        file_path = BACKUP_DIR / filename
        size = file_path.stat().st_size if file_path.exists() else 0
        with connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO backups(filename, size_bytes, kind, created_at)
                VALUES(?,?,?,?)
                """,
                (filename, size, "manual", now_iso()),
            )
            conn.execute(
                """
                UPDATE backups
                SET verify_status=?, verified_at=?, verify_message=?
                WHERE filename=?
                """,
                ("ok" if ok else "failed", now_iso(), message, filename),
            )

    def verify_backup(self):
        admin = self.require_admin()
        filename, file_path = self.backup_path_from_payload()
        ok, message, counts = self.inspect_backup_file(file_path)
        self.update_backup_check_result(filename, ok, message, counts)
        with connect() as conn:
            write_audit(
                conn,
                admin,
                "backup.verify",
                "backup",
                None,
                "备份校验通过" if ok else "备份校验失败",
                {"filename": filename, "message": message, "counts": counts},
                self.client_address[0],
            )
        return {"ok": ok, "message": message, "counts": counts, "backups": self.list_backups()}

    def restore_backup(self):
        admin = self.require_admin()
        filename, file_path = self.backup_path_from_payload()
        ok, message, counts = self.inspect_backup_file(file_path)
        self.update_backup_check_result(filename, ok, message, counts)
        if not ok:
            raise AppError(400, f"备份校验未通过，已取消恢复：{message}")
        pre_restore = create_database_backup(kind="manual", user_id=admin["id"])
        try:
            with sqlite3.connect(file_path) as source, sqlite3.connect(DB_PATH) as dest:
                source.backup(dest)
            init_db()
            restore_message = f"已恢复到备份 {filename}；恢复前备份：{pre_restore['filename'] if pre_restore else '未生成'}"
            with connect() as conn:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO backups(filename, size_bytes, kind, created_at, verify_status, verified_at, verify_message)
                    VALUES(?,?,?,?,?,?,?)
                    """,
                    (filename, file_path.stat().st_size, "manual", now_iso(), "ok", now_iso(), message),
                )
                conn.execute(
                    """
                    UPDATE backups
                    SET restored_at=?, restored_by=?, restore_message=?
                    WHERE filename=?
                    """,
                    (now_iso(), admin["id"], restore_message, filename),
                )
                write_audit(
                    conn,
                    admin,
                    "backup.restore",
                    "backup",
                    None,
                    "数据库已按指定备份恢复",
                    {"filename": filename, "pre_restore": pre_restore, "counts": counts},
                    self.client_address[0],
                )
        except Exception as exc:
            with connect() as conn:
                conn.execute(
                    "UPDATE backups SET restore_message=? WHERE filename=?",
                    (f"恢复失败：{exc}", filename),
                )
                write_audit(
                    conn,
                    admin,
                    "backup.restore_failed",
                    "backup",
                    None,
                    "数据库恢复失败",
                    {"filename": filename, "error": str(exc), "pre_restore": pre_restore},
                    self.client_address[0],
                )
            raise AppError(500, f"恢复失败：{exc}") from exc
        return {"message": restore_message, "backups": self.list_backups(), "pre_restore": pre_restore}

    def list_settings(self):
        self.require_admin()
        with connect() as conn:
            settings = rows_to_list(
                conn.execute(
                    """
                    SELECT s.*, u.display_name AS updated_by_name
                    FROM system_settings s
                    LEFT JOIN users u ON u.id = s.updated_by
                    ORDER BY s.key
                    """
                ).fetchall()
            )
            for setting in settings:
                if setting["value_type"] != "password":
                    continue
                setting["configured"] = bool(sso_setting(conn, setting["key"]))
                setting["value"] = ""
            return settings

    def public_settings(self):
        keys = (
            "app_brand_name",
            "app_team_name",
            "red_black_show_black_points",
            "red_black_show_black_details",
            "sso_enabled",
            "sso_auto_login",
            "sso_button_label",
        )
        placeholders = ",".join("?" for _ in keys)
        with connect() as conn:
            rows = rows_to_list(
                conn.execute(
                    f"SELECT key, value FROM system_settings WHERE key IN ({placeholders})",
                    keys,
                ).fetchall()
            )
            config = sso_configuration(conn)
        values = {key: value for key, _, value, _, _ in DEFAULT_SETTINGS if key in keys}
        values.update({row["key"]: row["value"] for row in rows})
        values["sso_enabled"] = "1" if config["enabled"] else "0"
        values["sso_auto_login"] = "1" if config["auto_login"] else "0"
        values["sso_button_label"] = config["button_label"]
        values["sso_ready"] = "1" if sso_configuration_ready(config) else "0"
        values["https_required"] = "1" if REQUIRE_HTTPS else "0"
        return values

    def diagnose_sso(self):
        self.require_admin()
        data = read_json(self)
        access_token = str(data.get("access_token") or "").strip()
        if len(access_token) > 16384:
            raise AppError(400, "Access Token 长度异常")
        with connect() as conn:
            config = sso_configuration(conn)
            missing = sso_missing_fields(config)
        result = {
            "enabled": config["enabled"],
            "mode": config["mode"],
            "auto_provision": config["auto_provision"],
            "client_secret_configured": bool(config["client_secret"]),
            "missing": missing,
            "username_claim": config["username_claim"],
            "display_name_claim": config["display_name_claim"],
            "group_claim": config["group_claim"],
            "scopes": config["scopes"],
            "redirect_uri": self.sso_redirect_uri(config) if not missing else (config.get("redirect_uri") or ""),
            "userinfo_checked": False,
            "connection_pool": sso_http_pool_stats(),
        }
        result["warnings"] = []
        if config["mode"] == "manual" and config["scopes"] != "get_user_info":
            result["warnings"].append(
                "华为云 OneAccess 的 OAuth2 Scope 固定为 get_user_info；当前值不同，请确认身份平台要求"
            )
        if missing:
            result["status"] = "incomplete"
            result["message"] = f"已保存配置仍缺少：{'、'.join(missing)}"
            return result
        discovery = load_oidc_discovery(config, force_refresh=True)
        result["connection_pool"] = sso_http_pool_stats()
        result["status"] = "configured"
        result["message"] = "已保存的 OAuth2 配置完整"
        result["authorization_host"] = urlparse(discovery["authorization_endpoint"]).netloc
        result["token_host"] = urlparse(discovery["token_endpoint"]).netloc
        result["userinfo_host"] = urlparse(discovery["userinfo_endpoint"]).netloc
        if not access_token:
            return result
        claims = fetch_json(
            discovery["userinfo_endpoint"],
            headers={"Authorization": f"Bearer {access_token}"},
            purpose="UserInfo 诊断",
        )
        result["connection_pool"] = sso_http_pool_stats()
        identity_claims = resolve_sso_identity(claims, config)
        available_claims = sorted(str(key) for key in claims.keys())[:40]
        result.update({
            "userinfo_checked": True,
            "available_claims": available_claims,
            "employee_id": identity_claims["employee_id"],
            "display_name": identity_claims["display_name"],
            "username_claim_used": identity_claims["username_claim_used"],
            "display_name_claim_used": identity_claims["display_name_claim_used"],
            "groups": identity_claims["groups"][:20],
        })
        if not identity_claims["employee_id"]:
            result["status"] = "mapping_failed"
            result["message"] = "UserInfo 调用成功，但没有找到可用于匹配账号的工号字段"
            return result
        with connect() as conn:
            matched_org = match_sso_org_unit(conn, identity_claims["groups"])
            existing = conn.execute(
                """
                SELECT id, display_name, username, employee_id, active, auth_source
                FROM users
                WHERE LOWER(employee_id)=LOWER(?) OR LOWER(username)=LOWER(?)
                ORDER BY CASE WHEN LOWER(employee_id)=LOWER(?) THEN 0 ELSE 1 END
                LIMIT 1
                """,
                (
                    identity_claims["employee_id"],
                    identity_claims["employee_id"],
                    identity_claims["employee_id"],
                ),
            ).fetchone()
        result["status"] = "matched" if existing else "will_create"
        result["message"] = "已匹配现有系统用户" if existing else (
            "未匹配现有用户，首次 SSO 登录时将创建访客账号"
            if config["auto_provision"]
            else "未匹配现有用户，且自动创建已关闭"
        )
        result["existing_user"] = (
            {
                "id": existing["id"],
                "display_name": existing["display_name"],
                "username": existing["username"],
                "employee_id": existing["employee_id"],
                "active": bool(existing["active"]),
                "auth_source": existing["auth_source"],
            }
            if existing else None
        )
        result["suggested_org"] = (
            {"id": matched_org["id"], "name": matched_org["name"], "path": matched_org["path"]}
            if matched_org else None
        )
        return result

    def update_settings(self):
        admin = self.require_admin()
        data = read_json(self)
        settings = data.get("settings") if isinstance(data.get("settings"), dict) else data
        if not isinstance(settings, dict) or not settings:
            raise AppError(400, "没有可更新配置")
        allowed = {key for key, *_ in DEFAULT_SETTINGS}
        sso_settings_changed = any(str(key).startswith("sso_") for key in settings)
        with connect() as conn:
            for key, value in settings.items():
                if key not in allowed:
                    continue
                row = conn.execute("SELECT value_type FROM system_settings WHERE key=?", (key,)).fetchone()
                if not row:
                    continue
                normalized = str(value).strip()
                if row["value_type"] == "password" and not normalized:
                    continue
                if row["value_type"] == "number":
                    try:
                        normalized = str(max(0, int(float(normalized))))
                    except ValueError:
                        raise AppError(400, f"{key} 必须是数字")
                if row["value_type"] == "boolean":
                    normalized = "1" if normalized in ("1", "true", "on", "yes", "启用") else "0"
                if key in ("sso_issuer_url", "sso_redirect_uri", "sso_authorization_url", "sso_token_url", "sso_userinfo_url") and normalized:
                    labels = {
                        "sso_issuer_url": "OIDC Issuer",
                        "sso_redirect_uri": "OIDC 回调地址",
                        "sso_authorization_url": "OAuth2 授权地址",
                        "sso_token_url": "OAuth2 Token 地址",
                        "sso_userinfo_url": "OAuth2 用户信息地址",
                    }
                    validate_sso_url(normalized, labels[key])
                if key == "sso_mode" and normalized not in ("discovery", "manual"):
                    raise AppError(400, "OAuth2 配置方式不正确")
                if key == "sso_default_user_type":
                    normalized = GUEST_USER_TYPE_KEY
                conn.execute(
                    "UPDATE system_settings SET value=?, updated_by=?, updated_at=? WHERE key=?",
                    (normalized, admin["id"], now_iso(), key),
                )
            config = sso_configuration(conn)
            if config["enabled"]:
                if not sso_configuration_ready(config):
                    if config["mode"] == "manual":
                        raise AppError(400, "启用企业 SSO 前必须填写 Client ID 以及三个 OAuth2 服务地址")
                    raise AppError(400, "启用企业 SSO 前必须填写 OIDC Issuer 和 Client ID")
                if config["mode"] == "manual":
                    for key, label in (("authorization_url", "OAuth2 授权地址"), ("token_url", "OAuth2 Token 地址"), ("userinfo_url", "OAuth2 用户信息地址")):
                        validate_sso_url(config[key], label)
                else:
                    validate_sso_url(config["issuer_url"], "OIDC Issuer")
                if config["redirect_uri"]:
                    validate_sso_url(config["redirect_uri"], "OIDC 回调地址")
                if config["auto_provision"] and not conn.execute(
                    "SELECT key FROM user_types WHERE key=? AND active=1",
                    (GUEST_USER_TYPE_KEY,),
                ).fetchone():
                    raise AppError(400, "启用 SSO 自动建号前必须保留访客权限模板")
            write_audit(
                conn,
                admin,
                "settings.update",
                "system_settings",
                None,
                "系统配置已更新",
                {"keys": list(settings.keys())},
                self.client_address[0],
            )
        if sso_settings_changed:
            clear_sso_http_state()
        return {"message": "系统配置已更新", "settings": self.list_settings()}

    def list_audit_logs(self, query):
        self.require_admin()
        limit = 100
        if query.get("limit"):
            try:
                limit = max(20, min(500, int(query["limit"][0])))
            except ValueError:
                limit = 100
        with connect() as conn:
            logs = rows_to_list(
                conn.execute(
                    """
                    SELECT l.*, u.display_name AS actor
                    FROM audit_logs l
                    LEFT JOIN users u ON u.id = l.user_id
                    ORDER BY l.created_at DESC, l.id DESC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
            )
        for log in logs:
            try:
                log["metadata"] = json.loads(log.get("metadata") or "{}")
            except json.JSONDecodeError:
                log["metadata"] = {}
        return logs

    def list_backups(self):
        self.require_admin()
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        with connect() as conn:
            rows = rows_to_list(
                conn.execute(
                    """
                    SELECT b.*, u.display_name AS creator
                    FROM backups b
                    LEFT JOIN users u ON u.id = b.created_by
                    ORDER BY b.created_at DESC, b.id DESC
                    """
                ).fetchall()
            )
        known = {row["filename"] for row in rows}
        for file_path in sorted(BACKUP_DIR.glob("*.db"), reverse=True):
            if file_path.name not in known:
                rows.append(
                    {
                        "id": None,
                        "filename": file_path.name,
                        "size_bytes": file_path.stat().st_size,
                        "kind": "manual",
                        "creator": "",
                        "created_at": dt.datetime.fromtimestamp(file_path.stat().st_mtime).replace(microsecond=0).isoformat(),
                        "verify_status": "",
                        "verified_at": "",
                        "verify_message": "",
                        "restored_at": "",
                        "restore_message": "",
                    }
                )
        return rows

    def create_manual_backup(self):
        admin = self.require_admin()
        backup = create_database_backup(kind="manual", user_id=admin["id"])
        if not backup:
            raise AppError(500, "备份失败")
        return {"message": "备份已创建", "backup": backup, "backups": self.list_backups()}



