from ..permissions import *


class OperationsHandlerMixin:
    def list_rules(self, query):
        clauses = ["1=1"]
        params = []
        if query.get("kind"):
            clauses.append("kind=?")
            params.append(query["kind"][0])
        with connect() as conn:
            return rows_to_list(conn.execute(f"SELECT * FROM red_black_rules WHERE {' AND '.join(clauses)} ORDER BY created_at DESC", params).fetchall())

    def create_rule(self):
        admin = self.require_admin()
        data = read_json(self)
        content = (data.get("content") or "").strip()
        if not content:
            raise AppError(400, "规则内容不能为空")
        title = (data.get("title") or content[:24] or "红黑榜规则").strip()
        kind = data.get("kind") if data.get("kind") in ("red", "black") else "red"
        with connect() as conn:
            cursor = conn.execute(
                "INSERT INTO red_black_rules(title, kind, content, effective_from, effective_to, active, created_by, created_at) VALUES(?,?,?,?,?,?,?,?)",
                (title, kind, content, None, None, 1, admin["id"], now_iso()),
            )
            write_audit(conn, admin, "rule.create", "red_black_rule", cursor.lastrowid, "红黑榜规则已发布", {"kind": kind}, self.client_address[0])
        return {"message": "规则已发布", "rules": self.list_rules({})}

    def list_scores(self, query):
        where, params = date_filter(query, "s.score_date")
        user = self.current_user(required=False)
        with connect() as conn:
            org_where, org_params = self.organization_current_user_filter(conn, "u", user)
            show_black_details = bool(user and user.get("role") == "admin") or get_setting_value(
                conn, "red_black_show_black_details", "1"
            ) == "1"
            clauses = [where, org_where]
            params.extend(org_params)
            if query.get("user_id") and query["user_id"][0]:
                try:
                    user_id = int(query["user_id"][0])
                except (TypeError, ValueError):
                    raise AppError(400, "成员参数不正确")
                clauses.append("s.user_id=?")
                params.append(user_id)
            if not show_black_details:
                clauses.append("s.kind='red'")
            return rows_to_list(
                conn.execute(
                    f"""
                    SELECT s.*, u.display_name, r.title AS rule_title
                    FROM red_black_scores s
                    JOIN users u ON u.id = s.user_id
                    LEFT JOIN red_black_rules r ON r.id = s.rule_id
                    WHERE {' AND '.join(clauses)}
                    ORDER BY s.score_date DESC, s.created_at DESC
                    """,
                    params,
                ).fetchall()
            )

    def create_score(self):
        admin = self.require_admin()
        data = read_json(self)
        points = abs(int(data.get("points") or 0))
        if data.get("kind") == "black":
            points = -points
        with connect() as conn:
            org_where, org_params = self.organization_current_user_filter(conn, "u", admin)
            eligible = conn.execute(
                f"""
                SELECT u.id
                FROM users u
                LEFT JOIN user_types t ON t.key=u.user_type
                WHERE u.id=? AND u.active=1 AND COALESCE(t.include_in_rules, 1)=1 AND {org_where}
                """,
                [data.get("user_id"), *org_params],
            ).fetchone()
            if not eligible:
                raise AppError(400, "该账号未纳入红黑榜名单")
            cursor = conn.execute(
                "INSERT INTO red_black_scores(user_id, rule_id, kind, points, reason, score_date, created_by, created_at) VALUES(?,?,?,?,?,?,?,?)",
                (data.get("user_id"), data.get("rule_id") or None, data.get("kind"), points, data.get("reason") or "", data.get("score_date") or today_iso(), admin["id"], now_iso()),
            )
            write_audit(conn, admin, "score.create", "red_black_score", cursor.lastrowid, "红黑榜积分已记录", {"user_id": data.get("user_id"), "points": points}, self.client_address[0])
        return {"message": "积分已记录", "scores": self.list_scores({})}

    def update_score(self, score_id):
        admin = self.require_admin()
        data = read_json(self)
        with connect() as conn:
            org_where, org_params = self.organization_current_user_filter(conn, "u", admin)
            score = conn.execute(
                f"""
                SELECT s.*
                FROM red_black_scores s
                JOIN users u ON u.id=s.user_id
                WHERE s.id=? AND {org_where}
                """,
                [score_id, *org_params],
            ).fetchone()
            if not score:
                raise AppError(404, "积分记录不存在")
            if score["score_date"] != today_iso():
                raise AppError(400, "仅允许编辑当天积分明细")
            kind = data.get("kind") if data.get("kind") in ("red", "black") else score["kind"]
            points = abs(int(data.get("points") or abs(int(score["points"] or 0))))
            if kind == "black":
                points = -points
            score_date = data.get("score_date") or score["score_date"]
            if score_date != today_iso():
                raise AppError(400, "积分日期只能保持当天")
            user_id = int(data.get("user_id") or score["user_id"])
            if not conn.execute(
                f"""
                SELECT u.id FROM users u
                LEFT JOIN user_types t ON t.key=u.user_type
                WHERE u.id=? AND u.active=1 AND COALESCE(t.include_in_rules, 1)=1 AND {org_where}
                """,
                [user_id, *org_params],
            ).fetchone():
                raise AppError(400, "该账号未纳入红黑榜名单")
            rule_id = data.get("rule_id") or None
            if rule_id:
                rule = conn.execute("SELECT id, kind FROM red_black_rules WHERE id=? AND active=1", (rule_id,)).fetchone()
                if not rule:
                    raise AppError(404, "规则不存在")
                kind = rule["kind"]
                if kind == "black":
                    points = -abs(points)
                else:
                    points = abs(points)
            conn.execute(
                """
                UPDATE red_black_scores
                SET user_id=?, rule_id=?, kind=?, points=?, reason=?, score_date=?
                WHERE id=?
                """,
                (user_id, rule_id, kind, points, data.get("reason") or "", score_date, score_id),
            )
            write_audit(conn, admin, "score.update", "red_black_score", score_id, "红黑榜积分已更新", {"fields": list(data.keys())}, self.client_address[0])
        return {"message": "积分已更新", "scores": self.list_scores({"from": [today_iso()], "to": [today_iso()]})}

    def red_black_dashboard(self, query):
        where, params = date_filter(query, "s.score_date")
        user = self.current_user(required=False)
        with connect() as conn:
            org_where, org_params = self.organization_current_user_filter(conn, "u", user)
            show_black_points = bool(user and user.get("role") == "admin") or get_setting_value(
                conn, "red_black_show_black_points", "1"
            ) == "1"
            users = rows_to_list(
                conn.execute(
                    f"""
                    SELECT u.id, u.display_name FROM users u
                    LEFT JOIN user_types t ON t.key=u.user_type
                    WHERE u.active=1 AND COALESCE(t.include_in_rules, 1)=1 AND {org_where}
                    ORDER BY u.display_name
                    """,
                    org_params,
                ).fetchall()
            )
            totals = rows_to_list(
                conn.execute(
                    f"""
                    SELECT u.id, u.display_name,
                           SUM(CASE WHEN s.kind='red' THEN ABS(s.points) ELSE 0 END) AS red_points,
                           SUM(CASE WHEN s.kind='black' THEN ABS(s.points) ELSE 0 END) AS black_points
                    FROM users u
                    LEFT JOIN user_types t ON t.key=u.user_type
                    LEFT JOIN red_black_scores s ON s.user_id = u.id AND {where}
                    WHERE u.active=1 AND COALESCE(t.include_in_rules, 1)=1 AND {org_where}
                    GROUP BY u.id
                    ORDER BY red_points DESC, black_points ASC, u.display_name
                    """,
                    [*params, *org_params],
                ).fetchall()
            )
            timeline = rows_to_list(
                conn.execute(
                    f"""
                    SELECT s.score_date,
                           SUM(CASE WHEN s.kind='red' THEN ABS(s.points) ELSE 0 END) AS red_points,
                           SUM(CASE WHEN s.kind='black' THEN ABS(s.points) ELSE 0 END) AS black_points
                    FROM red_black_scores s
                    JOIN users u ON u.id=s.user_id
                    WHERE {where} AND {org_where}
                    GROUP BY s.score_date
                    ORDER BY s.score_date
                    """,
                    [*params, *org_params],
                ).fetchall()
            )
            monthly_rows = rows_to_list(
                conn.execute(
                    f"""
                    SELECT s.user_id,
                           strftime('%m', s.score_date) AS month,
                           SUM(CASE WHEN s.kind='red' THEN ABS(s.points) ELSE 0 END) AS red_points,
                           SUM(CASE WHEN s.kind='black' THEN ABS(s.points) ELSE 0 END) AS black_points
                    FROM red_black_scores s
                    JOIN users u ON u.id=s.user_id
                    WHERE {where} AND {org_where}
                    GROUP BY s.user_id, strftime('%m', s.score_date)
                    """,
                    [*params, *org_params],
                ).fetchall()
            )
        annual_map = {
            user["id"]: {
                "id": user["id"],
                "display_name": user["display_name"],
                "months": {str(month): {"red": 0, "black": 0} for month in range(1, 13)},
                "total_red": 0,
                "total_black": 0,
            }
            for user in users
        }
        for row in monthly_rows:
            user_id = row["user_id"]
            if user_id not in annual_map:
                continue
            month = str(int(row["month"] or 0)) if row.get("month") else ""
            if month in annual_map[user_id]["months"]:
                red_points = int(row["red_points"] or 0)
                black_points = int(row["black_points"] or 0)
                annual_map[user_id]["months"][month] = {"red": red_points, "black": black_points}
                annual_map[user_id]["total_red"] += red_points
                annual_map[user_id]["total_black"] += black_points
        annual = sorted(
            annual_map.values(),
            key=lambda item: (-int(item["total_red"] or 0), int(item["total_black"] or 0), item["display_name"]),
        )
        if not show_black_points:
            for item in totals:
                item["black_points"] = 0
            for item in timeline:
                item["black_points"] = 0
            for item in annual:
                item["total_black"] = 0
                for month in item["months"].values():
                    month["black"] = 0
            totals.sort(key=lambda item: (-int(item["red_points"] or 0), item["display_name"]))
            annual.sort(key=lambda item: (-int(item["total_red"] or 0), item["display_name"]))
        return {
            "totals": totals,
            "timeline": timeline,
            "annual": annual,
            "show_black_points": show_black_points,
        }

    def list_meetings(self, query):
        where, params = date_filter(query, "m.meeting_date")
        with connect() as conn:
            context = self.organization_context(conn)
            org_where, org_params = self.organization_entity_filter(conn, "m.org_unit_id", inherit_ancestors=True)
            attendance_where, attendance_params = self.organization_current_user_filter(conn, "u")
            meetings = rows_to_list(
                conn.execute(
                    f"""
                    SELECT m.*, u.display_name AS creator, o.name AS org_unit_name
                    FROM meetings m
                    JOIN users u ON u.id = m.created_by
                    LEFT JOIN org_units o ON o.id=m.org_unit_id
                    WHERE {where} AND {org_where}
                    ORDER BY m.meeting_date DESC
                    """,
                    [*params, *org_params],
                ).fetchall()
            )
            items = rows_to_list(
                conn.execute(
                    """
                    SELECT i.*, u.display_name AS owner_name,
                           c.display_name AS created_by_name,
                           t.name AS type_name, t.color AS type_color,
                           o.title AS option_title
                    FROM meeting_items i
                    LEFT JOIN users u ON u.id = i.owner_id
                    LEFT JOIN users c ON c.id = i.created_by
                    LEFT JOIN meeting_topic_types t ON t.id = i.type_id
                    LEFT JOIN meeting_topic_options o ON o.id = i.option_id
                    WHERE i.deleted_at IS NULL
                    ORDER BY i.meeting_id, i.sort_order, i.created_at
                    """
                ).fetchall()
            )
            attendance = rows_to_list(
                conn.execute(
                    f"""
                    SELECT a.*, u.display_name
                    FROM meeting_attendance a
                    JOIN users u ON u.id = a.user_id
                    WHERE {attendance_where}
                    ORDER BY u.display_name
                    """,
                    attendance_params,
                ).fetchall()
            )
            topic_links = rows_to_list(
                conn.execute(
                    """
                    SELECT l.meeting_id, t.id, t.name, t.color, t.sort_order
                    FROM meeting_topic_links l
                    JOIN meeting_topic_types t ON t.id = l.type_id
                    WHERE t.active=1
                    ORDER BY l.sort_order, t.sort_order, t.id
                    """
                ).fetchall()
            )
        item_map = {}
        for item in items:
            item_map.setdefault(item["meeting_id"], []).append(item)
        attendance_map = {}
        for record in attendance:
            attendance_map.setdefault(record["meeting_id"], []).append(record)
        topic_map = {}
        for topic in topic_links:
            topic_map.setdefault(topic["meeting_id"], []).append({
                "id": topic["id"],
                "name": topic["name"],
                "color": topic["color"],
                "sort_order": topic["sort_order"],
            })
        for meeting in meetings:
            meeting["inherited"] = meeting["org_unit_id"] not in context["visible_ids"]
            meeting_items = item_map.get(meeting["id"], [])
            meeting_topics = topic_map.get(meeting["id"], [])
            seen_topics = {topic["id"] for topic in meeting_topics}
            for item in meeting_items:
                if item.get("type_id") and item["type_id"] not in seen_topics:
                    meeting_topics.append({
                        "id": item["type_id"],
                        "name": item.get("type_name") or item.get("section") or "议题",
                        "color": item.get("type_color") or "#3370ff",
                        "sort_order": 999,
                    })
                    seen_topics.add(item["type_id"])
            meeting["items"] = meeting_items
            meeting["attendance"] = attendance_map.get(meeting["id"], [])
            meeting["topic_types"] = meeting_topics
            meeting["topic_type_ids"] = [topic["id"] for topic in meeting_topics]
        return meetings

    def create_meeting(self, user):
        data = read_json(self)
        start_time = str(data.get("start_time") or "").strip()
        if start_time and not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", start_time):
            raise AppError(400, "会议开始时间格式不正确")
        with connect() as conn:
            default_title = get_setting_value(conn, "meeting_default_title", "周例会")
            org_context = self.organization_context(conn, user)
            org_unit_id = org_context["selected"]["id"] if org_context["selected"] else user.get("org_unit_id")
            cursor = conn.execute(
                "INSERT INTO meetings(meeting_date, start_time, title, summary, status, created_by, org_unit_id, created_at) VALUES(?,?,?,?,?,?,?,?)",
                (data.get("meeting_date") or today_iso(), start_time or None, data.get("title") or default_title, data.get("summary") or "", "draft", user["id"], org_unit_id, now_iso()),
            )
            meeting_id = cursor.lastrowid
            for topic_id in data.get("topic_type_ids") or []:
                link_meeting_topic(conn, meeting_id, topic_id, user["id"])
            write_audit(conn, user, "meeting.create", "meeting", meeting_id, "会议已创建", {"meeting_date": data.get("meeting_date") or today_iso()}, self.client_address[0])
        return {"message": "会议已创建", "meeting_id": meeting_id, "meetings": self.list_meetings({})}

    def update_meeting(self, meeting_id):
        admin = self.require_admin()
        data = read_json(self)
        allowed_statuses = {"draft", "scheduled", "in_progress", "completed", "archived"}
        fields = []
        values = []
        for key in ("meeting_date", "start_time", "title", "summary"):
            if key in data:
                value = str(data.get(key) or "").strip()
                if key in ("meeting_date", "title") and not value:
                    raise AppError(400, "会议日期和标题不能为空")
                if key == "start_time" and value and not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value):
                    raise AppError(400, "会议开始时间格式不正确")
                fields.append(f"{key}=?")
                values.append(value or None if key == "start_time" else value)
        if "status" in data:
            status = str(data.get("status") or "").strip()
            if status not in allowed_statuses:
                raise AppError(400, "会议状态不正确")
            fields.append("status=?")
            values.append(status)
        if not fields:
            raise AppError(400, "没有可更新字段")
        values.append(meeting_id)
        with connect() as conn:
            self.require_meeting_access(conn, meeting_id, admin)
            meeting = conn.execute("SELECT id, status FROM meetings WHERE id=?", (meeting_id,)).fetchone()
            if not meeting:
                raise AppError(404, "会议不存在")
            conn.execute(f"UPDATE meetings SET {', '.join(fields)} WHERE id=?", values)
            write_audit(conn, admin, "meeting.update", "meeting", meeting_id, "会议状态或信息已更新", {"fields": list(data.keys())}, self.client_address[0])
        return {"message": "会议已更新", "meetings": self.list_meetings({})}

    def copy_previous_meeting_agenda(self, meeting_id):
        admin = self.require_admin()
        with connect() as conn:
            self.require_meeting_access(conn, meeting_id, admin)
            meeting = conn.execute("SELECT * FROM meetings WHERE id=?", (meeting_id,)).fetchone()
            if not meeting:
                raise AppError(404, "会议不存在")
            if meeting["status"] in ("completed", "archived"):
                raise AppError(400, "已结束会议不能调整议题")
            previous = conn.execute(
                "SELECT id FROM meetings WHERE meeting_date<? AND title=? AND org_unit_id=? ORDER BY meeting_date DESC, id DESC LIMIT 1",
                (meeting["meeting_date"], meeting["title"], meeting["org_unit_id"]),
            ).fetchone()
            if not previous:
                previous = conn.execute(
                    "SELECT id FROM meetings WHERE meeting_date<? AND org_unit_id=? ORDER BY meeting_date DESC, id DESC LIMIT 1",
                    (meeting["meeting_date"], meeting["org_unit_id"]),
                ).fetchone()
            if not previous:
                raise AppError(400, "没有可沿用的历史会议")
            source_items = conn.execute(
                "SELECT * FROM meeting_items WHERE meeting_id=? AND deleted_at IS NULL ORDER BY sort_order, id",
                (previous["id"],),
            ).fetchall()
            existing_titles = {
                row["title"] for row in conn.execute(
                    "SELECT title FROM meeting_items WHERE meeting_id=? AND deleted_at IS NULL", (meeting_id,)
                ).fetchall()
            }
            copied = 0
            for item in source_items:
                if item["title"] in existing_titles:
                    continue
                conn.execute(
                    """
                    INSERT INTO meeting_items(
                        meeting_id, section, title, detail, minutes, owner_id, status, due_date,
                        created_by, created_at, type_id, option_id, sort_order, duration_minutes,
                        expected_output, materials, carried_from_id
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        meeting_id, item["section"], item["title"], item["detail"] or "", "",
                        item["owner_id"], "todo", None, admin["id"], now_iso(), item["type_id"],
                        item["option_id"], item["sort_order"], item["duration_minutes"] or 10,
                        item["expected_output"] or "", item["materials"] or "", item["id"],
                    ),
                )
                link_meeting_topic(conn, meeting_id, item["type_id"], admin["id"])
                copied += 1
            write_audit(conn, admin, "meeting.copy_agenda", "meeting", meeting_id, "已沿用上场会议议题", {"source_meeting_id": previous["id"], "copied": copied}, self.client_address[0])
        return {"message": f"已沿用 {copied} 个议题", "meetings": self.list_meetings({})}

    def update_meeting_topics(self, meeting_id):
        admin = self.require_admin()
        data = read_json(self)
        topic_ids = data.get("topic_type_ids") or []
        if isinstance(topic_ids, str):
            topic_ids = [item.strip() for item in topic_ids.split(",") if item.strip()]
        normalized = []
        for topic_id in topic_ids:
            try:
                value = int(topic_id)
            except (TypeError, ValueError):
                continue
            if value not in normalized:
                normalized.append(value)
        with connect() as conn:
            self.require_meeting_access(conn, meeting_id, admin)
            meeting = conn.execute("SELECT id, status FROM meetings WHERE id=?", (meeting_id,)).fetchone()
            if not meeting:
                raise AppError(404, "会议不存在")
            if meeting["status"] in ("completed", "archived"):
                raise AppError(400, "已结束会议不能调整主题，请先重新开启")
            active = {
                row["id"]
                for row in conn.execute(
                    "SELECT id FROM meeting_topic_types WHERE active=1 AND id IN ({})".format(",".join("?" for _ in normalized) or "NULL"),
                    normalized,
                ).fetchall()
            } if normalized else set()
            conn.execute("DELETE FROM meeting_topic_links WHERE meeting_id=?", (meeting_id,))
            for index, topic_id in enumerate(normalized):
                if topic_id not in active:
                    continue
                conn.execute(
                    """
                    INSERT OR IGNORE INTO meeting_topic_links(
                        meeting_id, type_id, sort_order, created_by, created_at
                    ) VALUES(?,?,?,?,?)
                    """,
                    (meeting_id, topic_id, index, admin["id"], now_iso()),
                )
            write_audit(conn, admin, "meeting.topics_update", "meeting", meeting_id, "会议主题已更新", {"topic_type_ids": normalized}, self.client_address[0])
        return {"message": "会议主题已更新", "meetings": self.list_meetings({})}

    def bulk_generate_meetings(self):
        admin = self.require_admin()
        data = read_json(self)
        start = week_start(data.get("start_date") or today_iso())
        summary = (data.get("summary") or "按预设议题自动生成").strip()
        start_date = dt.date.fromisoformat(start)
        created_meetings = 0
        created_items = 0
        with connect() as conn:
            org_context = self.organization_context(conn, admin)
            org_unit_id = org_context["selected"]["id"] if org_context["selected"] else admin.get("org_unit_id")
            default_weeks = get_int_setting(conn, "meeting_bulk_default_weeks", 4, minimum=1, maximum=52)
            weeks = max(1, min(52, int(data.get("weeks") or default_weeks)))
            title = (data.get("title") or get_setting_value(conn, "meeting_default_title", "周例会")).strip()
            start_time = str(data.get("start_time") or "").strip()
            if start_time and not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", start_time):
                raise AppError(400, "会议开始时间格式不正确")
            options = rows_to_list(
                conn.execute(
                    """
                    SELECT o.*, t.name AS type_name
                    FROM meeting_topic_options o
                    JOIN meeting_topic_types t ON t.id = o.type_id
                    WHERE o.active=1 AND t.active=1
                    ORDER BY o.sort_order, o.id
                    """
                ).fetchall()
            )
            if not options:
                raise AppError(400, "请先维护预设议题")
            for offset in range(weeks):
                meeting_date = (start_date + dt.timedelta(weeks=offset)).isoformat()
                meeting = conn.execute(
                    "SELECT id FROM meetings WHERE meeting_date=? AND org_unit_id=? ORDER BY id LIMIT 1",
                    (meeting_date, org_unit_id),
                ).fetchone()
                if meeting:
                    meeting_id = meeting["id"]
                else:
                    cursor = conn.execute(
                        "INSERT INTO meetings(meeting_date, start_time, title, summary, status, created_by, org_unit_id, created_at) VALUES(?,?,?,?,?,?,?,?)",
                        (meeting_date, start_time or None, title, summary, "scheduled", admin["id"], org_unit_id, now_iso()),
                    )
                    meeting_id = cursor.lastrowid
                    created_meetings += 1
                for option in options:
                    if not recurrence_matches(option, offset, meeting_date):
                        continue
                    exists = conn.execute(
                        "SELECT id FROM meeting_items WHERE meeting_id=? AND option_id=?",
                        (meeting_id, option["id"]),
                    ).fetchone()
                    if exists:
                        continue
                    conn.execute(
                        """
                        INSERT INTO meeting_items(
                            meeting_id, section, title, detail, minutes, owner_id, status,
                            due_date, created_by, created_at, type_id, option_id, sort_order,
                            duration_minutes, expected_output, materials
                        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                        """,
                        (
                            meeting_id,
                            option["type_name"],
                            option["title"],
                            option["default_detail"] or "",
                            "",
                            option["owner_id"],
                            "todo",
                            None,
                            admin["id"],
                            now_iso(),
                            option["type_id"],
                            option["id"],
                            option["sort_order"] or 0,
                            option["duration_minutes"] or 10,
                            option["expected_output"] or "",
                            option["materials"] or "",
                        ),
                    )
                    link_meeting_topic(conn, meeting_id, option["type_id"], admin["id"])
                    created_items += 1
            write_audit(conn, admin, "meeting.bulk_generate", "meeting", None, "周例会已批量生成", {"weeks": weeks, "created_meetings": created_meetings, "created_items": created_items}, self.client_address[0])
        return {
            "message": f"已生成 {created_meetings} 场会议、{created_items} 个议题",
            "meetings": self.list_meetings({}),
        }

    def list_meeting_topics(self):
        with connect() as conn:
            types = rows_to_list(
                conn.execute(
                    "SELECT * FROM meeting_topic_types WHERE active=1 ORDER BY sort_order, id"
                ).fetchall()
            )
            options = rows_to_list(
                conn.execute(
                    """
                    SELECT o.*, u.display_name AS owner_name
                    FROM meeting_topic_options o
                    LEFT JOIN users u ON u.id = o.owner_id
                    WHERE o.active=1
                    ORDER BY o.sort_order, o.id
                    """
                ).fetchall()
            )
        option_map = {}
        for option in options:
            option_map.setdefault(option["type_id"], []).append(option)
        for topic_type in types:
            topic_type["options"] = option_map.get(topic_type["id"], [])
        return {"types": types}

    def create_meeting_topic_type(self):
        self.require_admin()
        data = read_json(self)
        with connect() as conn:
            cursor = conn.execute(
                "INSERT INTO meeting_topic_types(name, color, sort_order, active) VALUES(?,?,?,1)",
                (data.get("name"), data.get("color") or "#3370ff", int(data.get("sort_order") or 0)),
            )
            write_audit(conn, self.current_user(), "meeting_topic_type.create", "meeting_topic_type", cursor.lastrowid, "议题类型已创建", {"name": data.get("name")}, self.client_address[0])
        return {"message": "议题类型已创建", **self.list_meeting_topics()}

    def delete_meeting_topic_type(self, type_id):
        admin = self.require_admin()
        with connect() as conn:
            topic_type = conn.execute("SELECT id, name FROM meeting_topic_types WHERE id=? AND active=1", (type_id,)).fetchone()
            if not topic_type:
                raise AppError(404, "议题类型不存在")
            conn.execute("UPDATE meeting_topic_types SET active=0 WHERE id=?", (type_id,))
            conn.execute("UPDATE meeting_topic_options SET active=0 WHERE type_id=?", (type_id,))
            write_audit(conn, admin, "meeting_topic_type.delete", "meeting_topic_type", type_id, "议题类型已删除", {"name": topic_type["name"]}, self.client_address[0])
        return {"message": "议题类型已删除", **self.list_meeting_topics()}

    def current_meeting_owner_id(self, conn, raw_owner_id, user, strict=True):
        if raw_owner_id in (None, "", 0, "0"):
            return None
        try:
            owner_id = int(raw_owner_id)
        except (TypeError, ValueError):
            if strict:
                raise AppError(400, "责任人数据不正确")
            return None
        org_where, org_params = self.organization_current_user_filter(conn, "u", user)
        owner = conn.execute(
            f"SELECT u.id FROM users u WHERE u.id=? AND u.active=1 AND {org_where}",
            [owner_id, *org_params],
        ).fetchone()
        if owner:
            return owner_id
        if strict:
            raise AppError(400, "责任人不属于当前团队")
        return None

    def create_meeting_topic_option(self):
        admin = self.require_admin()
        data = read_json(self)
        recurrence_type, recurrence_value, recurrence_weeks = normalize_recurrence(data)
        with connect() as conn:
            owner_id = self.current_meeting_owner_id(conn, data.get("owner_id"), admin)
            cursor = conn.execute(
                "INSERT INTO meeting_topic_options(type_id, title, default_detail, owner_id, recurrence_weeks, recurrence_type, recurrence_value, sort_order, active, duration_minutes, expected_output, materials) VALUES(?,?,?,?,?,?,?,?,1,?,?,?)",
                (data.get("type_id"), data.get("title"), data.get("default_detail") or "", owner_id, recurrence_weeks, recurrence_type, recurrence_value, int(data.get("sort_order") or 0), max(1, min(180, int(data.get("duration_minutes") or 10))), data.get("expected_output") or "", data.get("materials") or ""),
            )
            write_audit(conn, self.current_user(), "meeting_topic_option.create", "meeting_topic_option", cursor.lastrowid, "预设议题已创建", {"title": data.get("title"), "recurrence_type": recurrence_type, "recurrence_value": recurrence_value}, self.client_address[0])
        return {"message": "议题选项已创建", **self.list_meeting_topics()}

    def update_meeting_topic_option(self, option_id):
        admin = self.require_admin()
        data = read_json(self)
        fields = []
        values = []
        for key in ("type_id", "title", "default_detail", "owner_id", "sort_order", "active", "duration_minutes", "expected_output", "materials"):
            if key in data:
                fields.append(f"{key}=?")
                value = data[key] or None if key == "owner_id" else data[key]
                if key == "duration_minutes":
                    value = max(1, min(180, int(value or 10)))
                values.append(value)
        if any(key in data for key in ("recurrence_rule", "recurrence_type", "recurrence_value", "recurrence_weeks")):
            recurrence_type, recurrence_value, recurrence_weeks = normalize_recurrence(data)
            fields.extend(["recurrence_weeks=?", "recurrence_type=?", "recurrence_value=?"])
            values.extend([recurrence_weeks, recurrence_type, recurrence_value])
        if not fields:
            raise AppError(400, "没有可更新字段")
        values.append(option_id)
        with connect() as conn:
            if "owner_id" in data:
                owner_index = fields.index("owner_id=?")
                values[owner_index] = self.current_meeting_owner_id(conn, data.get("owner_id"), admin)
            conn.execute(f"UPDATE meeting_topic_options SET {', '.join(fields)} WHERE id=?", values)
            write_audit(conn, admin, "meeting_topic_option.update", "meeting_topic_option", option_id, "预设议题已更新", {"fields": list(data.keys())}, self.client_address[0])
        return {"message": "预设议题已更新", **self.list_meeting_topics()}

    def delete_meeting_topic_option(self, option_id):
        admin = self.require_admin()
        with connect() as conn:
            conn.execute("UPDATE meeting_topic_options SET active=0 WHERE id=?", (option_id,))
            write_audit(conn, admin, "meeting_topic_option.delete", "meeting_topic_option", option_id, "预设议题已删除", {}, self.client_address[0])
        return {"message": "预设议题已删除", **self.list_meeting_topics()}

    def create_meeting_item(self, meeting_id, user):
        data = read_json(self)
        owner_is_explicit = bool(data.get("owner_id"))
        type_id = data.get("type_id") or None
        option_id = data.get("option_id") or None
        section = data.get("section") or "议题"
        title = data.get("title")
        detail = data.get("detail") or ""
        if option_id and user["role"] != "admin":
            raise AppError(403, "普通成员只能添加自定义议题")
        with connect() as conn:
            self.require_meeting_access(conn, meeting_id, user)
            if option_id:
                option = conn.execute(
                    """
                    SELECT o.*, t.name AS type_name
                    FROM meeting_topic_options o
                    JOIN meeting_topic_types t ON t.id = o.type_id
                    WHERE o.id=?
                    """,
                    (option_id,),
                ).fetchone()
                if option:
                    type_id = option["type_id"]
                    section = option["type_name"]
                    title = title or option["title"]
                    detail = detail or option["default_detail"] or ""
                    if not data.get("owner_id"):
                        data["owner_id"] = option["owner_id"]
                    if not data.get("duration_minutes"):
                        data["duration_minutes"] = option["duration_minutes"] or 10
                    if not data.get("expected_output"):
                        data["expected_output"] = option["expected_output"] or ""
                    if not data.get("materials"):
                        data["materials"] = option["materials"] or ""
            elif type_id:
                topic_type = conn.execute("SELECT name FROM meeting_topic_types WHERE id=?", (type_id,)).fetchone()
                if topic_type:
                    section = topic_type["name"]
            if not title:
                raise AppError(400, "议题标题不能为空")
            owner_id = self.current_meeting_owner_id(
                conn, data.get("owner_id"), user, strict=owner_is_explicit
            )
            meeting = conn.execute("SELECT status FROM meetings WHERE id=?", (meeting_id,)).fetchone()
            if not meeting:
                raise AppError(404, "会议不存在")
            if meeting["status"] in ("completed", "archived"):
                raise AppError(400, "已结束会议不能新增议题，请先重新开启")
            next_order = conn.execute("SELECT COALESCE(MAX(sort_order), 0) + 10 FROM meeting_items WHERE meeting_id=?", (meeting_id,)).fetchone()[0]
            cursor = conn.execute(
                "INSERT INTO meeting_items(meeting_id, section, title, detail, minutes, owner_id, status, due_date, created_by, created_at, type_id, option_id, sort_order, duration_minutes, expected_output, materials) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (meeting_id, section, title, detail, data.get("minutes") or "", owner_id, data.get("status") or "todo", data.get("due_date") or None, user["id"], now_iso(), type_id, option_id, next_order, max(1, min(180, int(data.get("duration_minutes") or 10))), data.get("expected_output") or "", data.get("materials") or ""),
            )
            link_meeting_topic(conn, meeting_id, type_id, user["id"])
            write_audit(conn, user, "meeting_item.create", "meeting_item", cursor.lastrowid, "会议议题已添加", {"meeting_id": meeting_id, "title": title}, self.client_address[0])
        return {"message": "议题已添加", "meetings": self.list_meetings({})}

    def add_meeting_preset_items(self, meeting_id):
        actor = self.current_user()
        data = read_json(self)
        requested = data.get("items") or []
        if not isinstance(requested, list) or not requested:
            raise AppError(400, "请至少勾选一个预设议题")
        if len(requested) > 100:
            raise AppError(400, "单次最多添加 100 个预设议题")

        normalized = []
        seen = set()
        for item in requested:
            if not isinstance(item, dict):
                continue
            try:
                option_id = int(item.get("option_id"))
            except (TypeError, ValueError):
                continue
            if option_id in seen:
                continue
            owner_id = item.get("owner_id") or None
            if owner_id is not None:
                try:
                    owner_id = int(owner_id)
                except (TypeError, ValueError):
                    raise AppError(400, "责任人数据不正确")
            normalized.append({"option_id": option_id, "owner_id": owner_id})
            seen.add(option_id)
        if not normalized:
            raise AppError(400, "没有可添加的预设议题")

        with connect() as conn:
            self.require_meeting_access(conn, meeting_id, actor)
            meeting = conn.execute("SELECT id, status FROM meetings WHERE id=?", (meeting_id,)).fetchone()
            if not meeting:
                raise AppError(404, "会议不存在")
            if meeting["status"] in ("completed", "archived"):
                raise AppError(400, "已结束会议不能新增议题，请先重新开启")

            existing = {
                row["option_id"]
                for row in conn.execute(
                    "SELECT option_id FROM meeting_items WHERE meeting_id=? AND option_id IS NOT NULL AND deleted_at IS NULL",
                    (meeting_id,),
                ).fetchall()
            }
            owner_where, owner_params = self.organization_current_user_filter(conn, "u", actor)
            valid_owners = {
                row["id"]
                for row in conn.execute(
                    f"SELECT u.id FROM users u WHERE u.active=1 AND {owner_where}", owner_params
                ).fetchall()
            }
            next_order = conn.execute(
                "SELECT COALESCE(MAX(sort_order), 0) + 10 FROM meeting_items WHERE meeting_id=?",
                (meeting_id,),
            ).fetchone()[0]
            added = 0
            skipped = 0
            for requested_item in normalized:
                if requested_item["option_id"] in existing:
                    skipped += 1
                    continue
                option = conn.execute(
                    """
                    SELECT o.*, t.name AS type_name
                    FROM meeting_topic_options o
                    JOIN meeting_topic_types t ON t.id=o.type_id
                    WHERE o.id=? AND o.active=1 AND t.active=1
                    """,
                    (requested_item["option_id"],),
                ).fetchone()
                if not option:
                    skipped += 1
                    continue
                requested_owner_id = requested_item["owner_id"]
                if requested_owner_id is not None and requested_owner_id not in valid_owners:
                    raise AppError(400, f"议题“{option['title']}”的责任人不可用")
                owner_id = requested_owner_id or (option["owner_id"] if option["owner_id"] in valid_owners else None)
                conn.execute(
                    """
                    INSERT INTO meeting_items(
                        meeting_id, section, title, detail, minutes, owner_id, status,
                        due_date, created_by, created_at, type_id, option_id, sort_order,
                        duration_minutes, expected_output, materials
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        meeting_id, option["type_name"], option["title"], option["default_detail"] or "", "",
                        owner_id, "todo", None, actor["id"], now_iso(), option["type_id"], option["id"],
                        next_order, option["duration_minutes"] or 10, option["expected_output"] or "",
                        option["materials"] or "",
                    ),
                )
                link_meeting_topic(conn, meeting_id, option["type_id"], actor["id"])
                existing.add(option["id"])
                next_order += 10
                added += 1
            if not added and skipped:
                raise AppError(409, "所选议题已加入本场会议，请刷新后重新选择")
            write_audit(
                conn, actor, "meeting.agenda_options_add", "meeting", meeting_id,
                "批量加入预设议题", {"added": added, "skipped": skipped}, self.client_address[0],
            )
        message = f"已加入 {added} 个议题"
        if skipped:
            message += f"，跳过 {skipped} 个重复或失效议题"
        return {"message": message, "meetings": self.list_meetings({})}

    def update_meeting_item(self, item_id):
        user = self.current_user()
        data = read_json(self)
        fields = []
        values = []
        for key in ("minutes", "detail", "open_issues", "next_steps", "status", "owner_id", "due_date", "duration_minutes", "expected_output", "materials", "sort_order"):
            if key in data:
                fields.append(f"{key}=?")
                value = data[key] or None if key in ("owner_id", "due_date") else data[key]
                if key == "duration_minutes":
                    value = max(1, min(180, int(value or 10)))
                values.append(value)
        if not fields:
            raise AppError(400, "没有可更新字段")
        values.append(item_id)
        with connect() as conn:
            self.require_meeting_item_access(conn, item_id, user)
            if "owner_id" in data:
                owner_index = fields.index("owner_id=?")
                values[owner_index] = self.current_meeting_owner_id(conn, data.get("owner_id"), user)
            item = conn.execute("SELECT i.id, m.status AS meeting_status FROM meeting_items i JOIN meetings m ON m.id=i.meeting_id WHERE i.id=? AND i.deleted_at IS NULL", (item_id,)).fetchone()
            if not item:
                raise AppError(404, "议题不存在")
            if item["meeting_status"] in ("completed", "archived"):
                raise AppError(400, "已结束会议内容已锁定，请先重新开启")
            conn.execute(f"UPDATE meeting_items SET {', '.join(fields)} WHERE id=?", values)
            write_audit(conn, user, "meeting_item.update", "meeting_item", item_id, "会议议题/纪要已更新", {"fields": list(data.keys())}, self.client_address[0])
        return {"message": "会议纪要已保存", "meetings": self.list_meetings({})}

    def reorder_meeting_items(self, meeting_id):
        user = self.current_user()
        data = read_json(self)
        item_ids = data.get("item_ids") or []
        try:
            item_ids = [int(item_id) for item_id in item_ids]
        except (TypeError, ValueError):
            raise AppError(400, "议题排序数据不正确")
        if not item_ids:
            raise AppError(400, "没有可排序的议题")
        with connect() as conn:
            self.require_meeting_access(conn, meeting_id, user)
            meeting = conn.execute("SELECT status FROM meetings WHERE id=?", (meeting_id,)).fetchone()
            if not meeting:
                raise AppError(404, "会议不存在")
            if meeting["status"] in ("completed", "archived"):
                raise AppError(400, "已结束会议内容已锁定")
            valid_ids = {
                row["id"] for row in conn.execute(
                    "SELECT id FROM meeting_items WHERE meeting_id=? AND deleted_at IS NULL", (meeting_id,)
                ).fetchall()
            }
            if set(item_ids) != valid_ids:
                raise AppError(400, "议题排序列表不完整，请刷新后重试")
            for index, item_id in enumerate(item_ids):
                conn.execute("UPDATE meeting_items SET sort_order=? WHERE id=?", ((index + 1) * 10, item_id))
            write_audit(conn, user, "meeting_items.reorder", "meeting", meeting_id, "会议议题顺序已调整", {"item_ids": item_ids}, self.client_address[0])
        return {"message": "议题顺序已保存", "meetings": self.list_meetings({})}

    def carry_forward_meeting_item(self, item_id):
        user = self.current_user()
        with connect() as conn:
            self.require_meeting_item_access(conn, item_id, user)
            item = conn.execute(
                "SELECT i.*, m.meeting_date, m.title AS meeting_title, m.org_unit_id FROM meeting_items i JOIN meetings m ON m.id=i.meeting_id WHERE i.id=? AND i.deleted_at IS NULL",
                (item_id,),
            ).fetchone()
            if not item:
                raise AppError(404, "议题不存在")
            next_meeting = conn.execute(
                "SELECT id FROM meetings WHERE meeting_date>? AND org_unit_id=? AND status NOT IN ('completed','archived') ORDER BY meeting_date, id LIMIT 1",
                (item["meeting_date"], item["org_unit_id"]),
            ).fetchone()
            if not next_meeting:
                raise AppError(400, "暂无下一场可承接的会议，请先创建会议")
            existing = conn.execute(
                "SELECT id FROM meeting_items WHERE meeting_id=? AND (carried_from_id=? OR title=?) AND deleted_at IS NULL",
                (next_meeting["id"], item_id, item["title"]),
            ).fetchone()
            if existing:
                raise AppError(400, "该议题已经顺延到下一场会议")
            next_order = conn.execute("SELECT COALESCE(MAX(sort_order), 0) + 10 FROM meeting_items WHERE meeting_id=?", (next_meeting["id"],)).fetchone()[0]
            cursor = conn.execute(
                """
                INSERT INTO meeting_items(
                    meeting_id, section, title, detail, minutes, owner_id, status, due_date,
                    created_by, created_at, type_id, option_id, sort_order, duration_minutes,
                    expected_output, materials, carried_from_id
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    next_meeting["id"], item["section"], item["title"], item["detail"] or "", "",
                    item["owner_id"], "todo", item["due_date"], user["id"], now_iso(), item["type_id"],
                    item["option_id"], next_order, item["duration_minutes"] or 10,
                    item["expected_output"] or "", item["materials"] or "", item_id,
                ),
            )
            link_meeting_topic(conn, next_meeting["id"], item["type_id"], user["id"])
            write_audit(conn, user, "meeting_item.carry_forward", "meeting_item", cursor.lastrowid, "议题已顺延到下一场会议", {"source_item_id": item_id, "target_meeting_id": next_meeting["id"]}, self.client_address[0])
        return {"message": "议题已顺延到下一场会议", "meetings": self.list_meetings({})}

    def delete_meeting_item(self, item_id, user):
        with connect() as conn:
            self.require_meeting_item_access(conn, item_id, user)
            item = conn.execute(
                "SELECT i.id, i.title, i.deleted_at, m.status AS meeting_status FROM meeting_items i JOIN meetings m ON m.id=i.meeting_id WHERE i.id=?",
                (item_id,),
            ).fetchone()
            if not item:
                raise AppError(404, "议题不存在")
            if item["deleted_at"]:
                raise AppError(400, "议题已经在回收站中")
            if item["meeting_status"] in ("completed", "archived"):
                raise AppError(400, "已结束会议内容已锁定，请先重新开启")
            conn.execute(
                "UPDATE meeting_items SET deleted_at=?, deleted_by=? WHERE id=?",
                (now_iso(), user["id"], item_id),
            )
            add_recycle_record(conn, "meeting_item", item_id, item["title"], user)
            write_audit(
                conn,
                user,
                "meeting_item.delete",
                "meeting_item",
                item_id,
                "会议议题已移入回收站",
                {},
                self.client_address[0],
            )
        return {"message": "会议议题已移入回收站", "meetings": self.list_meetings({})}

    def upsert_attendance(self, meeting_id):
        admin = self.require_admin()
        data = read_json(self)
        status = data.get("status") or "present"
        if status not in ("present", "leave", "absent", "late"):
            raise AppError(400, "参会状态不正确")
        donation_required = 1 if status in ("late", "absent") else 0
        try:
            donation_amount = max(0, float(data.get("donation_amount") or 0)) if donation_required else 0
        except (TypeError, ValueError):
            raise AppError(400, "乐捐金额不正确")
        donation_done = 1 if donation_required and data.get("donation_done") else 0
        with connect() as conn:
            self.require_meeting_access(conn, meeting_id, admin)
            org_where, org_params = self.organization_current_user_filter(conn, "u", admin)
            attendee = conn.execute(
                f"SELECT u.id FROM users u WHERE u.id=? AND u.active=1 AND {org_where}",
                [data.get("user_id"), *org_params],
            ).fetchone()
            if not attendee:
                raise AppError(400, "签到成员不属于当前团队")
            conn.execute(
                """
                INSERT INTO meeting_attendance(meeting_id, user_id, status, donation_required, donation_amount, donation_done, note, updated_by, updated_at)
                VALUES(?,?,?,?,?,?,?,?,?)
                ON CONFLICT(meeting_id, user_id) DO UPDATE SET
                    status=excluded.status,
                    donation_required=excluded.donation_required,
                    donation_amount=excluded.donation_amount,
                    donation_done=excluded.donation_done,
                    note=excluded.note,
                    updated_by=excluded.updated_by,
                    updated_at=excluded.updated_at
                """,
                (meeting_id, data.get("user_id"), status, donation_required, donation_amount, donation_done, data.get("note") or "", admin["id"], now_iso()),
            )
            write_audit(conn, admin, "attendance.upsert", "meeting_attendance", meeting_id, "参会状态已更新", {"meeting_id": meeting_id, "user_id": data.get("user_id"), "status": status, "donation_amount": donation_amount}, self.client_address[0])
        return {"message": "参会状态已更新", "meetings": self.list_meetings({})}

    def list_links(self):
        with connect() as conn:
            links = rows_to_list(
                conn.execute(
                    """
                    SELECT l.*, u.display_name AS creator
                    FROM links l
                    LEFT JOIN users u ON u.id = l.created_by
                    WHERE l.deleted_at IS NULL
                    ORDER BY l.invalid ASC, l.pinned DESC, COALESCE(l.click_count, 0) DESC, COALESCE(l.last_clicked_at, '') DESC, l.title
                    """
                ).fetchall()
            )
        for link in links:
            for key in ("machine_scope", "process_tags"):
                try:
                    link[key] = json.loads(link.get(key) or "[]")
                except json.JSONDecodeError:
                    link[key] = []
        return links

    def create_link(self):
        user = self.current_user()
        data = read_json(self)
        title = (data.get("title") or "").strip()
        url = (data.get("url") or "").strip()
        if not title or not url:
            raise AppError(400, "链接名称和地址不能为空")
        machine_scope = data.get("machine_scope") or []
        process_tags = data.get("process_tags") or []
        if isinstance(machine_scope, str):
            machine_scope = [item.strip() for item in machine_scope.split(",") if item.strip()]
        if isinstance(process_tags, str):
            process_tags = [item.strip() for item in process_tags.split(",") if item.strip()]
        with connect() as conn:
            category = data.get("category")
            if not category:
                first = conn.execute("SELECT name FROM link_categories WHERE active=1 ORDER BY sort_order, id LIMIT 1").fetchone()
                category = first["name"] if first else "通用"
            cursor = conn.execute(
                """
                INSERT INTO links(
                    title, url, category, description, machine_scope, process_tags,
                    pinned, invalid, quality_note, created_by, created_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    title,
                    url,
                    category,
                    data.get("description") or "",
                    json.dumps(machine_scope, ensure_ascii=False),
                    json.dumps(process_tags, ensure_ascii=False),
                    0,
                    0,
                    "",
                    user["id"],
                    now_iso(),
                ),
            )
            write_audit(conn, user, "link.create", "link", cursor.lastrowid, "常用链接已归档", {"title": title, "category": category}, self.client_address[0])
        return {"message": "链接已归档", "links": self.list_links()}

    def normalize_link_items(self, items):
        if isinstance(items, str):
            items = items.replace("，", ",").split(",")
        if not isinstance(items, list):
            return []
        return [str(item).strip() for item in items if str(item).strip()]

    def update_link(self, link_id, user):
        operator = self.require_internal_user(user)
        data = read_json(self)
        fields = []
        values = []
        if operator.get("role") != "admin" and any(key in data for key in ("pinned", "invalid", "quality_note")):
            raise AppError(403, "链接置顶、失效和质量状态仅管理员可维护")
        for key in ("pinned", "invalid"):
            if key in data:
                fields.append(f"{key}=?")
                values.append(1 if data.get(key) in (1, "1", True, "true", "on", "yes", "置顶", "失效") else 0)
        for key in ("title", "url", "quality_note", "description", "category"):
            if key in data:
                value = str(data.get(key) or "").strip()
                if key in ("title", "url") and not value:
                    raise AppError(400, "链接名称和地址不能为空")
                fields.append(f"{key}=?")
                values.append(value)
        for key in ("machine_scope", "process_tags"):
            if key in data:
                items = self.normalize_link_items(data.get(key) or [])
                fields.append(f"{key}=?")
                values.append(json.dumps(items, ensure_ascii=False))
        if not fields:
            raise AppError(400, "没有可更新字段")
        values.append(link_id)
        with connect() as conn:
            link = conn.execute("SELECT id, title FROM links WHERE id=? AND deleted_at IS NULL", (link_id,)).fetchone()
            if not link:
                raise AppError(404, "链接不存在")
            conn.execute(f"UPDATE links SET {', '.join(fields)} WHERE id=?", values)
            write_audit(
                conn,
                operator,
                "link.update",
                "link",
                link_id,
                "常用链接已更新",
                {"title": link["title"], "fields": list(data.keys())},
                self.client_address[0],
            )
        return {"message": "链接已更新", "links": self.list_links()}

    def delete_link(self, link_id, user):
        operator = self.require_internal_user(user)
        with connect() as conn:
            link = conn.execute("SELECT id, title, url, deleted_at FROM links WHERE id=?", (link_id,)).fetchone()
            if not link:
                raise AppError(404, "链接不存在")
            if link["deleted_at"]:
                raise AppError(400, "链接已经在回收站中")
            conn.execute(
                "UPDATE links SET deleted_at=?, deleted_by=? WHERE id=?",
                (now_iso(), operator["id"], link_id),
            )
            add_recycle_record(
                conn,
                "link",
                link_id,
                link["title"],
                operator,
                {"url": link["url"]},
            )
            write_audit(
                conn,
                operator,
                "link.delete",
                "link",
                link_id,
                "常用链接已删除",
                {"title": link["title"]},
                self.client_address[0],
            )
        return {"message": "链接已移入回收站", "links": self.list_links()}

    def list_link_categories(self):
        with connect() as conn:
            return rows_to_list(
                conn.execute(
                    "SELECT * FROM link_categories WHERE active=1 ORDER BY sort_order, id"
                ).fetchall()
            )

    def create_link_category(self):
        self.require_admin()
        data = read_json(self)
        name = (data.get("name") or "").strip()
        if not name:
            raise AppError(400, "分类名称不能为空")
        with connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO link_categories(name, sort_order, active, created_at) VALUES(?,?,1,?)",
                (name, int(data.get("sort_order") or 0), now_iso()),
            )
            conn.execute("UPDATE link_categories SET active=1 WHERE name=?", (name,))
            row = conn.execute("SELECT id FROM link_categories WHERE name=?", (name,)).fetchone()
            write_audit(conn, self.current_user(), "link_category.upsert", "link_category", row["id"] if row else None, "链接分类已保存", {"name": name}, self.client_address[0])
        return {"message": "链接分类已保存", "categories": self.list_link_categories()}

    def list_machines(self):
        with connect() as conn:
            return rows_to_list(conn.execute("SELECT * FROM machines ORDER BY name").fetchall())

    def create_machine(self):
        admin = self.require_admin()
        data = read_json(self)
        with connect() as conn:
            cursor = conn.execute("INSERT INTO machines(name, description) VALUES(?,?)", (data.get("name"), data.get("description") or ""))
            write_audit(conn, admin, "machine.create", "machine", cursor.lastrowid, "机台已创建", {"name": data.get("name")}, self.client_address[0])
        return {"message": "机台已创建", "machines": self.list_machines()}

    def delete_machine(self, machine_id):
        admin = self.require_admin()
        with connect() as conn:
            machine = conn.execute("SELECT * FROM machines WHERE id=?", (machine_id,)).fetchone()
            if not machine:
                raise AppError(404, "机台不存在")
            shift_count = conn.execute("SELECT COUNT(*) AS count FROM shifts WHERE machine_id=?", (machine_id,)).fetchone()["count"]
            conn.execute("DELETE FROM shifts WHERE machine_id=?", (machine_id,))
            conn.execute("DELETE FROM machines WHERE id=?", (machine_id,))
            write_audit(
                conn,
                admin,
                "machine.delete",
                "machine",
                machine_id,
                "机台已删除",
                {"name": machine["name"], "deleted_shifts": shift_count},
                self.client_address[0],
            )
        return {"message": "机台已删除", "machines": self.list_machines()}

    def list_shifts(self, query):
        where, params = date_filter(query, "s.shift_date")
        with connect() as conn:
            org_where, org_params = self.organization_current_user_filter(conn, "u")
            return rows_to_list(
                conn.execute(
                    f"""
                    SELECT s.*, u.display_name, m.name AS machine_name
                    FROM shifts s
                    JOIN users u ON u.id = s.user_id
                    JOIN machines m ON m.id = s.machine_id
                    WHERE {where} AND {org_where}
                    ORDER BY s.shift_date DESC, m.name, s.shift_type
                    """,
                    [*params, *org_params],
                ).fetchall()
            )

    def create_shift(self):
        admin = self.require_admin()
        data = read_json(self)
        dates = data.get("shift_dates")
        if isinstance(dates, str):
            dates = [item.strip() for item in dates.replace("\n", ",").split(",") if item.strip()]
        if not dates:
            start = data.get("shift_start_date") or data.get("shift_date") or today_iso()
            end = data.get("shift_end_date") or start
            dates = date_range(start, end)
        dates = list(dict.fromkeys(dates))
        machine_id = int(data.get("machine_id") or 0)
        user_id = int(data.get("user_id") or 0)
        shift_type = data.get("shift_type")
        if shift_type not in ("day", "night"):
            raise AppError(400, "班次类型不正确")
        with connect() as conn:
            org_where, org_params = self.organization_current_user_filter(conn, "u", admin)
            default_hours = get_float_setting(conn, "shift_default_hours", 12, minimum=0.5, maximum=24)
            max_daily_hours = get_float_setting(conn, "shift_max_daily_hours", 24, minimum=1, maximum=48)
            hours = float(data.get("hours") or default_hours)
            if hours <= 0 or hours > 24:
                raise AppError(400, "单条排班工时需要在 0 到 24 小时之间")
            machine = conn.execute("SELECT id, name FROM machines WHERE id=?", (machine_id,)).fetchone()
            member = conn.execute(f"SELECT id, display_name FROM users u WHERE id=? AND active=1 AND {org_where}", [user_id, *org_params]).fetchone()
            if not machine or not member:
                raise AppError(404, "机台或排班成员不存在")
            conflicts = []
            for shift_date in dates:
                try:
                    dt.date.fromisoformat(shift_date)
                except ValueError:
                    raise AppError(400, f"排班日期格式不正确：{shift_date}")
                duplicate = conn.execute(
                    """
                    SELECT id FROM shifts
                    WHERE machine_id=? AND user_id=? AND shift_type=? AND shift_date=?
                    """,
                    (machine_id, user_id, shift_type, shift_date),
                ).fetchone()
                daily_hours = conn.execute(
                    "SELECT COALESCE(SUM(hours), 0) FROM shifts WHERE user_id=? AND shift_date=?",
                    (user_id, shift_date),
                ).fetchone()[0]
                if duplicate:
                    conflicts.append(f"{shift_date} 已有相同机台、成员和班次")
                elif float(daily_hours or 0) + hours > max_daily_hours:
                    conflicts.append(f"{shift_date} 累计 {float(daily_hours or 0) + hours:g} 小时，超过上限 {max_daily_hours:g} 小时")
            if conflicts:
                detail = "；".join(conflicts[:6])
                if len(conflicts) > 6:
                    detail += f"；另有 {len(conflicts) - 6} 天冲突"
                raise AppError(409, f"排班未保存：{detail}")
            created_ids = []
            for shift_date in dates:
                cursor = conn.execute(
                    "INSERT INTO shifts(machine_id, user_id, shift_type, shift_date, hours, note, created_by, created_at) VALUES(?,?,?,?,?,?,?,?)",
                    (machine_id, user_id, shift_type, shift_date, hours, data.get("note") or "", admin["id"], now_iso()),
                )
                created_ids.append(cursor.lastrowid)
            write_audit(conn, admin, "shift.create", "shift", created_ids[0] if len(created_ids) == 1 else None, "排班已保存", {"dates": dates, "count": len(created_ids), "user_id": user_id}, self.client_address[0])
        return {"message": "排班已保存", "shifts": self.list_shifts({})}

    def delete_shift(self, shift_id):
        admin = self.require_admin()
        with connect() as conn:
            org_where, org_params = self.organization_current_user_filter(conn, "u", admin)
            shift = conn.execute(
                f"SELECT s.* FROM shifts s JOIN users u ON u.id=s.user_id WHERE s.id=? AND {org_where}",
                [shift_id, *org_params],
            ).fetchone()
            if not shift:
                raise AppError(404, "排班不存在")
            conn.execute("DELETE FROM shifts WHERE id=?", (shift_id,))
            write_audit(conn, admin, "shift.delete", "shift", shift_id, "排班已删除", {"shift_date": shift["shift_date"], "user_id": shift["user_id"]}, self.client_address[0])
        return {"message": "排班已删除", "shifts": self.list_shifts({})}

    def shift_dashboard(self, query):
        where, params = date_filter(query, "s.shift_date")
        with connect() as conn:
            org_where, org_params = self.organization_current_user_filter(conn, "u")
            by_user = rows_to_list(
                conn.execute(
                    f"""
                    SELECT u.id, u.display_name, SUM(s.hours) AS hours, COUNT(*) AS shift_count
                    FROM shifts s
                    JOIN users u ON u.id = s.user_id
                    WHERE {where} AND {org_where}
                    GROUP BY u.id
                    ORDER BY hours DESC
                    """,
                    [*params, *org_params],
                ).fetchall()
            )
            by_machine = rows_to_list(
                conn.execute(
                    f"""
                    SELECT m.name AS machine_name, SUM(s.hours) AS hours, COUNT(*) AS shift_count
                    FROM shifts s
                    JOIN machines m ON m.id = s.machine_id
                    JOIN users u ON u.id=s.user_id
                    WHERE {where} AND {org_where}
                    GROUP BY m.id
                    ORDER BY m.name
                    """,
                    [*params, *org_params],
                ).fetchall()
            )
        return {"by_user": by_user, "by_machine": by_machine}

    def list_thank_you(self, query, viewer=None):
        where, params = date_filter(query, "v.week_start")
        with connect() as conn:
            giver_where, giver_params = self.organization_current_user_filter(conn, "giver", viewer)
            receiver_where, receiver_params = self.organization_current_user_filter(conn, "receiver", viewer)
            relation_where = f"({giver_where} AND {receiver_where})"
            relation_params = [*giver_params, *receiver_params]
            votes = rows_to_list(
                conn.execute(
                    f"""
                    SELECT v.*, giver.display_name AS voter_name, receiver.display_name AS receiver_name,
                           giver.org_unit_id AS voter_org_unit_id, giver_org.name AS voter_org_name,
                           receiver.org_unit_id AS receiver_org_unit_id, receiver_org.name AS receiver_org_name
                    FROM thank_you_votes v
                    JOIN users giver ON giver.id = v.voter_id
                    JOIN users receiver ON receiver.id = v.receiver_id
                    LEFT JOIN org_units giver_org ON giver_org.id=giver.org_unit_id
                    LEFT JOIN org_units receiver_org ON receiver_org.id=receiver.org_unit_id
                    WHERE {where} AND {relation_where}
                    ORDER BY v.week_start DESC, v.created_at DESC
                    """,
                    [*params, *relation_params],
                ).fetchall()
            )
        for vote in votes:
            vote["cross_team"] = vote["voter_org_unit_id"] != vote["receiver_org_unit_id"]
        return votes

    def create_thank_you(self, user):
        data = read_json(self)
        raw_receiver_ids = data.get("receiver_ids")
        if raw_receiver_ids is None:
            raw_receiver_ids = [data.get("receiver_id")]
        if not isinstance(raw_receiver_ids, list):
            raw_receiver_ids = [raw_receiver_ids]
        receiver_ids = []
        for raw_id in raw_receiver_ids:
            try:
                receiver_id = int(raw_id)
            except (TypeError, ValueError):
                continue
            if receiver_id not in receiver_ids:
                receiver_ids.append(receiver_id)
        if not receiver_ids:
            raise AppError(400, "请选择感谢对象")
        if user["id"] in receiver_ids:
            raise AppError(400, "不能给自己点赞")
        start = week_start(data.get("week_start") or today_iso())
        evidence = (data.get("evidence") or "").strip()
        if len(evidence) < 5:
            raise AppError(400, "请写下具体事实依据")
        with connect() as conn:
            org_where, org_params = self.organization_current_user_filter(conn, "u", user)
            giver = conn.execute(
                f"SELECT u.id FROM users u WHERE u.id=? AND u.active=1 AND {org_where}",
                [user["id"], *org_params],
            ).fetchone()
            if not giver:
                raise AppError(403, "只能在本人所属的当前团队送出感谢")
            weekly_limit = get_int_setting(conn, "thank_you_weekly_limit", 3, minimum=1, maximum=20)
            count = conn.execute("SELECT COUNT(*) FROM thank_you_votes WHERE voter_id=? AND week_start=?", (user["id"], start)).fetchone()[0]
            remaining = weekly_limit - count
            if remaining <= 0 or len(receiver_ids) > remaining:
                raise AppError(400, f"本周最多点赞 {weekly_limit} 人，当前还可感谢 {max(remaining, 0)} 人")
            placeholders = ",".join("?" for _ in receiver_ids)
            active_receivers = rows_to_list(
                conn.execute(
                    f"""
                    SELECT u.id, u.display_name FROM users u
                    LEFT JOIN user_types t ON t.key=u.user_type
                    WHERE u.active=1 AND COALESCE(t.include_in_thanks, 1)=1
                      AND u.id IN ({placeholders}) AND {org_where}
                    """,
                    [*receiver_ids, *org_params],
                ).fetchall()
            )
            active_receiver_ids = {row["id"] for row in active_receivers}
            if len(active_receiver_ids) != len(receiver_ids):
                raise AppError(400, "感谢对象不存在、已停用或不在当前团队")
            existing = rows_to_list(
                conn.execute(
                    f"""
                    SELECT v.receiver_id, u.display_name
                    FROM thank_you_votes v
                    JOIN users u ON u.id = v.receiver_id
                    WHERE v.voter_id=? AND v.week_start=? AND v.receiver_id IN ({placeholders})
                    """,
                    [user["id"], start, *receiver_ids],
                ).fetchall()
            )
            if existing:
                names = "、".join(row["display_name"] for row in existing)
                raise AppError(400, f"本周已经感谢过：{names}")
            created_at = now_iso()
            for receiver_id in receiver_ids:
                conn.execute(
                    "INSERT INTO thank_you_votes(voter_id, receiver_id, week_start, evidence, created_at) VALUES(?,?,?,?,?)",
                    (user["id"], receiver_id, start, evidence, created_at),
                )
            write_audit(conn, user, "thank_you.create", "thank_you", None, "Thank You 已送达", {"receiver_ids": receiver_ids, "week_start": start}, self.client_address[0])
        return {"message": "Thank You 已送达", "votes": self.list_thank_you({"from": [start], "to": [start]})}

    def can_manage_thank_vote(self, vote, user):
        if user["role"] == "admin":
            return True
        return vote["voter_id"] == user["id"] and str(vote["created_at"] or "")[:10] == today_iso()

    def update_thank_you(self, vote_id, user):
        data = read_json(self)
        evidence = (data.get("evidence") or "").strip()
        if len(evidence) < 5:
            raise AppError(400, "请写下具体事实依据")
        with connect() as conn:
            giver_where, giver_params = self.organization_current_user_filter(conn, "giver", user)
            receiver_where, receiver_params = self.organization_current_user_filter(conn, "receiver", user)
            vote = conn.execute(
                f"""
                SELECT v.* FROM thank_you_votes v
                JOIN users giver ON giver.id=v.voter_id
                JOIN users receiver ON receiver.id=v.receiver_id
                WHERE v.id=? AND {giver_where} AND {receiver_where}
                """,
                [vote_id, *giver_params, *receiver_params],
            ).fetchone()
            if not vote:
                raise AppError(404, "感谢记录不存在")
            if not self.can_manage_thank_vote(vote, user):
                raise AppError(403, "仅可编辑当天自己送出的感谢")
            conn.execute("UPDATE thank_you_votes SET evidence=? WHERE id=?", (evidence, vote_id))
            write_audit(conn, user, "thank_you.update", "thank_you", vote_id, "Thank You 记录已更新", {"week_start": vote["week_start"]}, self.client_address[0])
        return {"message": "感谢记录已更新"}

    def delete_thank_you(self, vote_id, user):
        with connect() as conn:
            giver_where, giver_params = self.organization_current_user_filter(conn, "giver", user)
            receiver_where, receiver_params = self.organization_current_user_filter(conn, "receiver", user)
            vote = conn.execute(
                f"""
                SELECT v.*, giver.display_name AS voter_name, receiver.display_name AS receiver_name
                FROM thank_you_votes v
                JOIN users giver ON giver.id = v.voter_id
                JOIN users receiver ON receiver.id = v.receiver_id
                WHERE v.id=? AND {giver_where} AND {receiver_where}
                """,
                [vote_id, *giver_params, *receiver_params],
            ).fetchone()
            if not vote:
                raise AppError(404, "感谢记录不存在")
            if not self.can_manage_thank_vote(vote, user):
                raise AppError(403, "仅可删除当天自己送出的感谢")
            conn.execute("DELETE FROM thank_you_votes WHERE id=?", (vote_id,))
            write_audit(
                conn,
                user,
                "thank_you.delete",
                "thank_you",
                vote_id,
                "Thank You 记录已删除",
                {
                    "voter_id": vote["voter_id"],
                    "receiver_id": vote["receiver_id"],
                    "week_start": vote["week_start"],
                    "voter_name": vote["voter_name"],
                    "receiver_name": vote["receiver_name"],
                },
                self.client_address[0],
            )
        return {"message": "感谢记录已删除"}

    def thank_you_dashboard(self, query, viewer=None):
        where, params = date_filter(query, "v.week_start")
        with connect() as conn:
            org_where, org_params = self.organization_current_user_filter(conn, "receiver", viewer)
            giver_where, giver_params = self.organization_current_user_filter(conn, "giver", viewer)
            stars = rows_to_list(
                conn.execute(
                    f"""
                    SELECT receiver.id, receiver.display_name, COUNT(*) AS thanks
                    FROM thank_you_votes v
                    JOIN users receiver ON receiver.id = v.receiver_id
                    JOIN users giver ON giver.id = v.voter_id
                    LEFT JOIN user_types t ON t.key=receiver.user_type
                    WHERE {where} AND receiver.active=1 AND COALESCE(t.include_in_thanks, 1)=1
                      AND {org_where} AND {giver_where}
                    GROUP BY receiver.id
                    ORDER BY thanks DESC, receiver.display_name
                    """,
                    [*params, *org_params, *giver_params],
                ).fetchall()
            )
            weekly = rows_to_list(
                conn.execute(
                    f"""
                    SELECT v.week_start, COUNT(*) AS thanks
                    FROM thank_you_votes v
                    JOIN users receiver ON receiver.id=v.receiver_id
                    JOIN users giver ON giver.id=v.voter_id
                    LEFT JOIN user_types t ON t.key=receiver.user_type
                    WHERE {where} AND receiver.active=1 AND COALESCE(t.include_in_thanks, 1)=1
                      AND {org_where} AND {giver_where}
                    GROUP BY v.week_start
                    ORDER BY v.week_start
                    """,
                    [*params, *org_params, *giver_params],
                ).fetchall()
            )
        return {"stars": stars, "weekly": weekly}

    def list_reminders(self, user):
        if not user:
            raise AppError(401, "请先登录")
        today = dt.date.today()
        soon = (today + dt.timedelta(days=3)).isoformat()
        today_value = today.isoformat()
        with connect() as conn:
            reminders = []
            morning_rows = rows_to_list(
                conn.execute(
                    """
                    SELECT id, title, status, priority, blocker, due_date, item_date, updated_at
                    FROM morning_items
                    WHERE owner_id=? AND active=1 AND status!='done'
                      AND item_date=?
                      AND (status='risk' OR priority='high' OR (due_date IS NOT NULL AND due_date<=?))
                    ORDER BY CASE WHEN status='risk' THEN 0 ELSE 1 END, due_date, id
                    """,
                    (user["id"], today_value, soon),
                ).fetchall()
            )
            for item in morning_rows:
                overdue = bool(item.get("due_date") and item["due_date"] < today_value)
                reminders.append({
                    "key": f"morning:{item['id']}:{item.get('updated_at') or ''}",
                    "type": "morning",
                    "level": "danger" if overdue or item["status"] == "risk" else "warning",
                    "title": item["title"],
                    "detail": item.get("blocker") or (f"截止 {item['due_date']}" if item.get("due_date") else "高优先级事项待推进"),
                    "date": item.get("due_date") or item["item_date"],
                    "page": "morning",
                })
            meeting_rows = rows_to_list(
                conn.execute(
                    """
                    SELECT i.id, i.title, i.status, i.due_date, m.meeting_date, m.title AS meeting_title
                    FROM meeting_items i
                    JOIN meetings m ON m.id=i.meeting_id
                    WHERE i.owner_id=? AND i.deleted_at IS NULL AND i.status!='done'
                      AND (
                        (i.due_date IS NOT NULL AND i.due_date<=?)
                        OR (m.meeting_date>=? AND m.meeting_date<=?)
                      )
                    ORDER BY COALESCE(i.due_date, m.meeting_date), i.id
                    """,
                    (user["id"], soon, today_value, soon),
                ).fetchall()
            )
            for item in meeting_rows:
                due_date = item.get("due_date") or item["meeting_date"]
                overdue = bool(item.get("due_date") and item["due_date"] < today_value)
                reminders.append({
                    "key": f"meeting-item:{item['id']}:{item.get('due_date') or ''}:{item['status']}",
                    "type": "meeting",
                    "level": "danger" if overdue else "info",
                    "title": item["title"],
                    "detail": f"{item['meeting_title']} · {'已逾期' if overdue else '行动项待处理'}",
                    "date": due_date,
                    "page": "meetings",
                })
            shift_rows = rows_to_list(
                conn.execute(
                    """
                    SELECT s.id, s.shift_date, s.shift_type, m.name AS machine_name
                    FROM shifts s
                    JOIN machines m ON m.id=s.machine_id
                    WHERE s.user_id=? AND s.shift_date>=? AND s.shift_date<=?
                    ORDER BY s.shift_date, s.shift_type
                    """,
                    (user["id"], today_value, soon),
                ).fetchall()
            )
            for shift in shift_rows:
                shift_name = "白班" if shift["shift_type"] == "day" else "夜班"
                reminders.append({
                    "key": f"shift:{shift['id']}:{shift['shift_date']}:{shift['shift_type']}",
                    "type": "shift",
                    "level": "info",
                    "title": f"{shift['machine_name']} · {shift_name}",
                    "detail": "近期排班，请提前确认交接安排",
                    "date": shift["shift_date"],
                    "page": "shifts",
                })
            read_keys = {
                row["reminder_key"]
                for row in conn.execute(
                    "SELECT reminder_key FROM reminder_reads WHERE user_id=?",
                    (user["id"],),
                ).fetchall()
            }
        allowed_pages = set(permissions_for(user).get("modules") or [])
        reminders = [item for item in reminders if item.get("page") in allowed_pages]
        level_order = {"danger": 0, "warning": 1, "info": 2}
        reminders.sort(key=lambda item: (level_order.get(item["level"], 9), item.get("date") or "", item["title"]))
        for reminder in reminders:
            reminder["read"] = reminder["key"] in read_keys
        return {
            "items": reminders,
            "unread": sum(1 for reminder in reminders if not reminder["read"]),
        }

    def mark_reminders_read(self, user):
        if not user:
            raise AppError(401, "请先登录")
        data = read_json(self)
        keys = data.get("keys") or []
        if data.get("all"):
            keys = [item["key"] for item in self.list_reminders(user)["items"]]
        if isinstance(keys, str):
            keys = [keys]
        if not isinstance(keys, list):
            raise AppError(400, "提醒标识格式不正确")
        keys = [str(key)[:240] for key in keys if str(key).strip()]
        with connect() as conn:
            for key in keys:
                conn.execute(
                    """
                    INSERT INTO reminder_reads(user_id, reminder_key, read_at)
                    VALUES(?,?,?)
                    ON CONFLICT(user_id, reminder_key) DO UPDATE SET read_at=excluded.read_at
                    """,
                    (user["id"], key, now_iso()),
                )
        return self.list_reminders(user)


