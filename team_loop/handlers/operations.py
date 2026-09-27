import re
import uuid

from ..permissions import *


def norm_image_ids_in(content):
    """Image ids referenced by `[[img:<id>]]` markers, deduped in first-appearance order.

    The marker carries a server-issued integer and nothing else — no URL, no HTML — which
    is what keeps the clause body renderable without reaching for `innerHTML`.
    """
    ids = []
    for raw in re.findall(NORM_IMAGE_MARKER, str(content or "")):
        image_id = int(raw)
        if image_id not in ids:
            ids.append(image_id)
    return ids


DUTY_DEFAULT_START = "08:30"
DUTY_DEFAULT_END = "18:00"
DUTY_CLOCK_PATTERN = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


def normalize_duty_clock(value, fallback):
    """Validate a HH:MM duty time, falling back to the default when blank."""
    text = str(value or "").strip()
    if not text:
        return fallback
    if not DUTY_CLOCK_PATTERN.match(text):
        raise AppError(400, f"值班时间格式不正确：{text}，请使用 HH:MM")
    return text


def duty_minutes(value):
    match = DUTY_CLOCK_PATTERN.match(str(value or "").strip())
    if not match:
        return 0
    return int(match.group(1)) * 60 + int(match.group(2))


def duty_hours(start_time, end_time):
    """Duty length in hours; a slot ending at or before its start wraps past midnight."""
    start = duty_minutes(start_time)
    end = duty_minutes(end_time)
    span = end - start
    if span <= 0:
        span += 24 * 60
    return round(span / 60.0, 2)


NORM_OTHER_CHAPTER_NAME = "其他"


def parse_norm_date(value, label):
    """Normalize an optional ISO date, returning None when blank."""
    text = str(value or "").strip()[:10]
    if not text:
        return None
    try:
        dt.date.fromisoformat(text)
    except ValueError:
        raise AppError(400, f"{label}格式不正确：{value}")
    return text


def norm_state(row):
    """Effective state of one norm: active / scheduled / expired / pending / abolished."""
    status = str(row.get("status") or "active")
    if status == "abolished":
        return "abolished"
    if status == "pending":
        return "pending"
    today = today_iso()
    if row.get("effective_to") and str(row["effective_to"]) < today:
        return "expired"
    if row.get("effective_from") and str(row["effective_from"]) > today:
        return "scheduled"
    return "active"


def build_norm_markdown(title, chapters, extra_lines=None):
    """Render one category document into plain Markdown."""
    chapters = chapters or []
    lines = [f"# {title}", ""]
    meta = [f"- 条款数量：{sum(len(chapter.get('articles') or []) for chapter in chapters)}"]
    for item in extra_lines or []:
        meta.append(item)
    meta.append(f"- 导出时间：{now_iso()}")
    lines.extend(meta)
    lines.append("")
    single = len(chapters) == 1
    if chapters and not single:
        lines.append("## 目录")
        lines.append("")
        for chapter in chapters:
            lines.append(f"- {str(chapter.get('no', '')).strip()} {str(chapter.get('name', '')).strip()}".rstrip())
        lines.append("")
    for chapter in chapters:
        if not single:
            lines.append(f"## {str(chapter.get('no', '')).strip()} {str(chapter.get('name', '')).strip()}".rstrip())
            lines.append("")
        if chapter.get("description"):
            lines.append(str(chapter["description"]))
            lines.append("")
        for article in chapter.get("articles") or []:
            lines.append(f"### {str(article.get('no', '')).strip()} {str(article.get('title', '')).strip()}".rstrip())
            if article.get("content"):
                lines.append("")
                lines.append(str(article["content"]))
            details = []
            if article.get("scope"):
                details.append(f"适用范围：{article['scope']}")
            if article.get("source"):
                details.append(f"来源：{article['source']}")
            if article.get("effective_from"):
                details.append(f"生效日期：{article['effective_from']}")
            if article.get("created_by_name"):
                details.append(f"记录人：{article['created_by_name']}")
            if details:
                lines.append("")
                for detail in details:
                    lines.append(f"- {detail}")
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


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
            target_user_id = (query.get("user_id") or [None])[0]
            org_where, org_params = self.organization_workbench_user_filter(conn, "u", user, target_user_id)
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
            meeting = conn.execute("SELECT id, status, org_unit_id FROM meetings WHERE id=?", (meeting_id,)).fetchone()
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
            meeting = conn.execute(
                "SELECT id, status, org_unit_id FROM meetings WHERE id=?",
                (meeting_id,),
            ).fetchone()
            if not meeting:
                raise AppError(404, "会议不存在")
            if meeting["status"] in ("completed", "archived"):
                raise AppError(400, "已结束会议不能调整主题，请先重新开启")
            active = {
                row["id"]
                for row in conn.execute(
                    "SELECT id FROM meeting_topic_types WHERE active=1 AND org_unit_id=? AND id IN ({})".format(",".join("?" for _ in normalized) or "NULL"),
                    [meeting["org_unit_id"], *normalized],
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
                    WHERE o.active=1 AND t.active=1 AND t.org_unit_id=?
                    ORDER BY o.sort_order, o.id
                    """,
                    (org_unit_id,),
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
            org_where, org_params = self.organization_current_entity_filter(conn, "t.org_unit_id")
            types = rows_to_list(
                conn.execute(
                    f"SELECT t.* FROM meeting_topic_types t WHERE t.active=1 AND {org_where} ORDER BY t.sort_order, t.id",
                    org_params,
                ).fetchall()
            )
            options = rows_to_list(
                conn.execute(
                    f"""
                    SELECT o.*, u.display_name AS owner_name
                    FROM meeting_topic_options o
                    JOIN meeting_topic_types t ON t.id=o.type_id
                    LEFT JOIN users u ON u.id = o.owner_id
                    WHERE o.active=1 AND t.active=1 AND {org_where}
                    ORDER BY o.sort_order, o.id
                    """,
                    org_params,
                ).fetchall()
            )
        option_map = {}
        for option in options:
            option_map.setdefault(option["type_id"], []).append(option)
        for topic_type in types:
            topic_type["options"] = option_map.get(topic_type["id"], [])
        return {"types": types}

    def create_meeting_topic_type(self):
        admin = self.require_admin()
        data = read_json(self)
        name = str(data.get("name") or "").strip()
        if not name:
            raise AppError(400, "议题类型名称不能为空")
        with connect() as conn:
            context = self.organization_context(conn, admin)
            org_unit_id = context["selected"]["id"]
            try:
                cursor = conn.execute(
                    "INSERT INTO meeting_topic_types(org_unit_id, name, color, sort_order, active) VALUES(?,?,?,?,1)",
                    (org_unit_id, name, data.get("color") or "#3370ff", int(data.get("sort_order") or 0)),
                )
            except sqlite3.IntegrityError as exc:
                raise AppError(400, "当前团队已存在同名议题类型") from exc
            write_audit(conn, admin, "meeting_topic_type.create", "meeting_topic_type", cursor.lastrowid, "议题类型已创建", {"name": name, "org_unit_id": org_unit_id}, self.client_address[0])
        return {"message": "议题类型已创建", **self.list_meeting_topics()}

    def delete_meeting_topic_type(self, type_id):
        admin = self.require_admin()
        with connect() as conn:
            org_where, org_params = self.organization_current_entity_filter(conn, "org_unit_id", admin)
            topic_type = conn.execute(
                f"SELECT id, name FROM meeting_topic_types WHERE id=? AND active=1 AND {org_where}",
                [type_id, *org_params],
            ).fetchone()
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
        org_where, org_params = self.organization_user_filter(conn, "u", user)
        owner = conn.execute(
            f"SELECT u.id FROM users u WHERE u.id=? AND u.active=1 AND {org_where}",
            [owner_id, *org_params],
        ).fetchone()
        if owner:
            return owner_id
        if strict:
            raise AppError(400, "责任人不属于当前团队或下级团队")
        return None

    def create_meeting_topic_option(self):
        admin = self.require_admin()
        data = read_json(self)
        recurrence_type, recurrence_value, recurrence_weeks = normalize_recurrence(data)
        with connect() as conn:
            org_where, org_params = self.organization_current_entity_filter(conn, "t.org_unit_id", admin)
            topic_type = conn.execute(
                f"SELECT t.id FROM meeting_topic_types t WHERE t.id=? AND t.active=1 AND {org_where}",
                [data.get("type_id"), *org_params],
            ).fetchone()
            if not topic_type:
                raise AppError(404, "当前团队下未找到该议题类型")
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
            org_where, org_params = self.organization_current_entity_filter(conn, "t.org_unit_id", admin)
            option = conn.execute(
                f"""
                SELECT o.id FROM meeting_topic_options o
                JOIN meeting_topic_types t ON t.id=o.type_id
                WHERE o.id=? AND o.active=1 AND {org_where}
                """,
                [option_id, *org_params],
            ).fetchone()
            if not option:
                raise AppError(404, "当前团队下未找到该预设议题")
            if "type_id" in data:
                target_type = conn.execute(
                    f"SELECT t.id FROM meeting_topic_types t WHERE t.id=? AND t.active=1 AND {org_where}",
                    [data.get("type_id"), *org_params],
                ).fetchone()
                if not target_type:
                    raise AppError(404, "目标议题类型不属于当前团队")
            if "owner_id" in data:
                owner_index = fields.index("owner_id=?")
                values[owner_index] = self.current_meeting_owner_id(conn, data.get("owner_id"), admin)
            conn.execute(f"UPDATE meeting_topic_options SET {', '.join(fields)} WHERE id=?", values)
            write_audit(conn, admin, "meeting_topic_option.update", "meeting_topic_option", option_id, "预设议题已更新", {"fields": list(data.keys())}, self.client_address[0])
        return {"message": "预设议题已更新", **self.list_meeting_topics()}

    def delete_meeting_topic_option(self, option_id):
        admin = self.require_admin()
        with connect() as conn:
            org_where, org_params = self.organization_current_entity_filter(conn, "t.org_unit_id", admin)
            option = conn.execute(
                f"""
                SELECT o.id FROM meeting_topic_options o
                JOIN meeting_topic_types t ON t.id=o.type_id
                WHERE o.id=? AND o.active=1 AND {org_where}
                """,
                [option_id, *org_params],
            ).fetchone()
            if not option:
                raise AppError(404, "当前团队下未找到该预设议题")
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
                    WHERE o.id=? AND t.org_unit_id=(SELECT org_unit_id FROM meetings WHERE id=?)
                    """,
                    (option_id, meeting_id),
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
                topic_type = conn.execute(
                    "SELECT name FROM meeting_topic_types WHERE id=? AND org_unit_id=(SELECT org_unit_id FROM meetings WHERE id=?)",
                    (type_id, meeting_id),
                ).fetchone()
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
            meeting = conn.execute("SELECT id, status, org_unit_id FROM meetings WHERE id=?", (meeting_id,)).fetchone()
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
            owner_where, owner_params = self.organization_user_filter(conn, "u", actor)
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
                    WHERE o.id=? AND o.active=1 AND t.active=1 AND t.org_unit_id=?
                    """,
                    (requested_item["option_id"], meeting["org_unit_id"]),
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

    def list_machines(self, viewer=None):
        with connect() as conn:
            org_where, org_params = self.organization_current_entity_filter(conn, "m.org_unit_id", viewer)
            return rows_to_list(
                conn.execute(f"SELECT m.* FROM machines m WHERE {org_where} ORDER BY m.name", org_params).fetchall()
            )

    def create_machine(self):
        admin = self.require_admin()
        data = read_json(self)
        name = str(data.get("name") or "").strip()
        if not name:
            raise AppError(400, "机台名称不能为空")
        with connect() as conn:
            context = self.organization_context(conn, admin)
            org_unit_id = context["selected"]["id"]
            try:
                cursor = conn.execute(
                    "INSERT INTO machines(org_unit_id, name, description) VALUES(?,?,?)",
                    (org_unit_id, name, data.get("description") or ""),
                )
            except sqlite3.IntegrityError as exc:
                raise AppError(400, "当前团队已存在同名机台") from exc
            write_audit(conn, admin, "machine.create", "machine", cursor.lastrowid, "机台已创建", {"name": name, "org_unit_id": org_unit_id}, self.client_address[0])
        return {"message": "机台已创建", "machines": self.list_machines(admin)}

    def delete_machine(self, machine_id):
        admin = self.require_admin()
        with connect() as conn:
            org_where, org_params = self.organization_current_entity_filter(conn, "m.org_unit_id", admin)
            machine = conn.execute(
                f"SELECT m.* FROM machines m WHERE m.id=? AND {org_where}",
                [machine_id, *org_params],
            ).fetchone()
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
        return {"message": "机台已删除", "machines": self.list_machines(admin)}

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
            machine_where, machine_params = self.organization_current_entity_filter(conn, "m.org_unit_id", admin)
            default_hours = get_float_setting(conn, "shift_default_hours", 12, minimum=0.5, maximum=24)
            max_daily_hours = get_float_setting(conn, "shift_max_daily_hours", 24, minimum=1, maximum=48)
            hours = float(data.get("hours") or default_hours)
            if hours <= 0 or hours > 24:
                raise AppError(400, "单条排班工时需要在 0 到 24 小时之间")
            machine = conn.execute(
                f"SELECT m.id, m.name FROM machines m WHERE m.id=? AND {machine_where}",
                [machine_id, *machine_params],
            ).fetchone()
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
            actor = self.current_user(required=False)
            target_user_id = (query.get("user_id") or [None])[0]
            org_where, org_params = self.organization_workbench_user_filter(conn, "u", actor, target_user_id)
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

    def list_duty_rosters(self, query):
        where, params = date_filter(query, "d.duty_date")
        with connect() as conn:
            org_where, org_params = self.organization_current_user_filter(conn, "u")
            return rows_to_list(
                conn.execute(
                    f"""
                    SELECT d.*, u.display_name
                    FROM duty_rosters d
                    JOIN users u ON u.id = d.user_id
                    WHERE {where} AND {org_where}
                    ORDER BY d.duty_date DESC, d.start_time, u.display_name
                    """,
                    [*params, *org_params],
                ).fetchall()
            )

    def list_duty_today(self, day=None):
        """Duty list for one day, already ordered by start time for the page header."""
        target = str(day or today_iso())[:10]
        with connect() as conn:
            org_where, org_params = self.organization_current_user_filter(conn, "u")
            return rows_to_list(
                conn.execute(
                    f"""
                    SELECT d.*, u.display_name
                    FROM duty_rosters d
                    JOIN users u ON u.id = d.user_id
                    WHERE d.duty_date=? AND {org_where}
                    ORDER BY d.start_time, u.display_name
                    """,
                    [target, *org_params],
                ).fetchall()
            )

    def create_duty_roster(self):
        admin = self.require_admin()
        data = read_json(self)
        dates = data.get("duty_dates")
        if isinstance(dates, str):
            dates = [item.strip() for item in dates.replace("\n", ",").split(",") if item.strip()]
        if not dates:
            start = data.get("duty_start_date") or data.get("duty_date") or today_iso()
            end = data.get("duty_end_date") or start
            dates = date_range(start, end)
        dates = list(dict.fromkeys(str(item).strip() for item in dates if str(item).strip()))
        if not dates:
            raise AppError(400, "请至少选择一个值班日期")
        user_id = int(data.get("user_id") or 0)
        start_time = normalize_duty_clock(data.get("start_time"), DUTY_DEFAULT_START)
        end_time = normalize_duty_clock(data.get("end_time"), DUTY_DEFAULT_END)
        note = (data.get("note") or "").strip()
        with connect() as conn:
            context = self.organization_context(conn, admin)
            org_unit_id = (context.get("selected") or {}).get("id")
            if not org_unit_id:
                raise AppError(400, "当前团队不存在，无法安排值班")
            org_where, org_params = self.organization_current_user_filter(conn, "u", admin)
            member = conn.execute(
                f"SELECT id, display_name FROM users u WHERE u.id=? AND active=1 AND {org_where}",
                [user_id, *org_params],
            ).fetchone()
            if not member:
                raise AppError(404, "值班成员不存在或不在当前团队")
            conflicts = []
            for duty_date in dates:
                try:
                    dt.date.fromisoformat(duty_date)
                except ValueError:
                    raise AppError(400, f"值班日期格式不正确：{duty_date}")
                duplicate = conn.execute(
                    "SELECT id FROM duty_rosters WHERE org_unit_id=? AND user_id=? AND duty_date=? AND start_time=?",
                    (org_unit_id, user_id, duty_date, start_time),
                ).fetchone()
                if duplicate:
                    conflicts.append(f"{duty_date} 该成员同一时段已有值班")
            if conflicts:
                detail = "；".join(conflicts[:6])
                if len(conflicts) > 6:
                    detail += f"；另有 {len(conflicts) - 6} 天冲突"
                raise AppError(409, f"值班未保存：{detail}")
            created_ids = []
            for duty_date in dates:
                cursor = conn.execute(
                    """
                    INSERT INTO duty_rosters(org_unit_id, user_id, duty_date, start_time, end_time, note, created_by, created_at)
                    VALUES(?,?,?,?,?,?,?,?)
                    """,
                    (org_unit_id, user_id, duty_date, start_time, end_time, note, admin["id"], now_iso()),
                )
                created_ids.append(cursor.lastrowid)
            write_audit(
                conn,
                admin,
                "duty.create",
                "duty_roster",
                created_ids[0] if len(created_ids) == 1 else None,
                "问题定位值班已保存",
                {"dates": dates, "count": len(created_ids), "user_id": user_id, "start_time": start_time, "end_time": end_time},
                self.client_address[0],
            )
        return {"message": "值班已保存", "duties": self.list_duty_rosters({})}

    def delete_duty_roster(self, duty_id):
        admin = self.require_admin()
        with connect() as conn:
            org_where, org_params = self.organization_current_user_filter(conn, "u", admin)
            duty = conn.execute(
                f"SELECT d.* FROM duty_rosters d JOIN users u ON u.id=d.user_id WHERE d.id=? AND {org_where}",
                [duty_id, *org_params],
            ).fetchone()
            if not duty:
                raise AppError(404, "值班记录不存在")
            conn.execute("DELETE FROM duty_rosters WHERE id=?", (duty_id,))
            write_audit(
                conn,
                admin,
                "duty.delete",
                "duty_roster",
                duty_id,
                "问题定位值班已删除",
                {"duty_date": duty["duty_date"], "user_id": duty["user_id"]},
                self.client_address[0],
            )
        return {"message": "值班已删除", "duties": self.list_duty_rosters({})}

    def duty_dashboard(self, query):
        """Per-member duty tally: days on duty and total hours, for the ranking panel."""
        where, params = date_filter(query, "d.duty_date")
        with connect() as conn:
            org_where, org_params = self.organization_current_user_filter(conn, "u")
            rows = conn.execute(
                f"""
                SELECT d.user_id, u.display_name, d.duty_date, d.start_time, d.end_time
                FROM duty_rosters d
                JOIN users u ON u.id = d.user_id
                WHERE {where} AND {org_where}
                ORDER BY d.duty_date, d.start_time
                """,
                [*params, *org_params],
            ).fetchall()
        tally = {}
        for row in rows:
            entry = tally.setdefault(
                row["user_id"],
                {"id": row["user_id"], "display_name": row["display_name"], "duty_count": 0, "hours": 0.0},
            )
            entry["duty_count"] += 1
            entry["hours"] = round(entry["hours"] + duty_hours(row["start_time"], row["end_time"]), 2)
        by_user = sorted(
            tally.values(),
            key=lambda item: (-item["duty_count"], -item["hours"], item["display_name"] or ""),
        )
        return {"by_user": by_user}

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
            target_user_id = (query.get("user_id") or [None])[0]
            org_where, org_params = self.organization_workbench_user_filter(conn, "receiver", viewer, target_user_id)
            if viewer and viewer.get("role") == "admin" and target_user_id not in (None, "", 0, "0"):
                giver_where, giver_params = "1=1", []
            else:
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

    # ---- 团队规范：分类 -> 条目 -> 自动成文 -> 版本发布 ----

    def norm_document_title(self, conn):
        team_name = (get_setting_value(conn, "app_team_name", "") or "").strip()
        return f"{team_name}规范" if team_name else "团队规范"

    def can_delete_norm_category(self, category, user):
        """目录归属：自己建的自己可以删，管理员可以删任何目录。

        预置分类由系统播种，created_by 为空，只有管理员能删——它们不是"没人建的"，而是
        "全团队共用的"，不该被第一个想整理目录的人顺手删掉。
        """
        if not user:
            return False
        if user.get("role") == "admin":
            return True
        return int(category["created_by"] or 0) == int(user["id"])

    def can_rename_norm_category(self, category, user):
        """改名跟删除同源：都是"我建的东西我自己管"，管理员兜底。

        刻意不做成管理员专属——创建人连自己刚打错的目录名都改不了，只能删了重建，而带着
        条款的目录根本删不掉（非空目录 409），等于把自己锁死。规则与 can_delete 逐字相同，
        免得同一行上出现"改名可以、删除不行"这种看着像 bug 的组合。
        """
        return self.can_delete_norm_category(category, user)

    def list_norm_categories(self):
        user = getattr(self, "api_user", None)
        with connect() as conn:
            where, params = self.organization_current_entity_filter(conn, "c.org_unit_id", user)
            rows = rows_to_list(
                conn.execute(
                    f"""
                    SELECT c.*, u.display_name AS created_by_name,
                           (SELECT COUNT(*) FROM norms n
                             WHERE n.category_id=c.id AND n.deleted_at IS NULL) AS norm_count,
                           (SELECT COUNT(*) FROM norm_categories ch
                             WHERE ch.parent_id=c.id) AS child_count
                    FROM norm_categories c
                    LEFT JOIN norm_categories p ON p.id=c.parent_id
                    LEFT JOIN users u ON u.id=c.created_by
                    WHERE {where}
                    ORDER BY COALESCE(p.sort_order, c.sort_order), c.parent_id IS NOT NULL, c.sort_order, c.id
                    """,
                    params,
                ).fetchall()
            )
        # can_delete / can_rename 由后端算：前端只画"点下去真会成功"的按钮，规则不重复实现。
        for row in rows:
            row["can_delete"] = self.can_delete_norm_category(row, user)
            row["can_rename"] = self.can_rename_norm_category(row, user)
        return rows

    def norm_category_name_taken(self, conn, org_unit_id, parent_id, name, exclude_id=None):
        """Duplicate names are scoped to the same parent shelf, not to the whole team."""
        sql = """
            SELECT id FROM norm_categories
            WHERE org_unit_id=? AND COALESCE(parent_id, 0)=? AND name=?
        """
        params = [org_unit_id, parent_id or 0, name]
        if exclude_id:
            sql += " AND id<>?"
            params.append(exclude_id)
        return conn.execute(sql, params).fetchone()

    def resolve_norm_parent(self, conn, raw_value, org_unit_id, category_id=None):
        """Resolve the optional parent shelf; empty or 0 means a top-level category.

        The tree is capped at two levels, so a parent must itself be top-level. Without this
        guard a sub-shelf could be nested under another sub-shelf and produce a third level
        that neither the navigation nor the per-category documents model.
        """
        if raw_value in (None, "", 0, "0"):
            return None
        try:
            parent_id = int(raw_value)
        except (TypeError, ValueError):
            raise AppError(400, "上级目录参数不正确")
        if category_id and parent_id == int(category_id):
            raise AppError(400, "不能把目录挂到自己下面")
        parent = conn.execute(
            "SELECT id, name, parent_id, active FROM norm_categories WHERE id=? AND org_unit_id=?",
            (parent_id, org_unit_id),
        ).fetchone()
        if not parent:
            raise AppError(404, "上级目录不存在")
        if parent["parent_id"]:
            raise AppError(400, f"「{parent['name']}」已经是二级目录，规范分类最多两级")
        if not parent["active"]:
            raise AppError(400, f"上级目录「{parent['name']}」已停用，请选择其他目录")
        return parent_id

    def require_current_org_unit_id(self, conn, user, purpose):
        context = self.organization_context(conn, user)
        org_unit_id = (context.get("selected") or {}).get("id")
        if not org_unit_id:
            raise AppError(400, f"当前团队不存在，无法{purpose}")
        return org_unit_id

    def create_norm_category(self):
        """任何能进「团队规范」的登录用户都可以建目录（一级或二级）。

        模块级 create 权限在路由层已经把访客挡在外面，这里记下创建人，供后续删除时判断归属。
        """
        actor = getattr(self, "api_user", None) or self.current_user()
        data = read_json(self)
        name = (data.get("name") or "").strip()
        if not name:
            raise AppError(400, "请填写分类名称")
        if len(name) > 24:
            raise AppError(400, "分类名称不超过 24 字")
        description = (data.get("description") or "").strip()
        with connect() as conn:
            org_unit_id = self.require_current_org_unit_id(conn, actor, "新增规范分类")
            parent_id = self.resolve_norm_parent(conn, data.get("parent_id"), org_unit_id)
            if self.norm_category_name_taken(conn, org_unit_id, parent_id, name):
                raise AppError(409, f"该层级下已有分类「{name}」")
            sort_order = conn.execute(
                """
                SELECT COALESCE(MAX(sort_order), 0) + 1 FROM norm_categories
                WHERE org_unit_id=? AND COALESCE(parent_id, 0)=?
                """,
                (org_unit_id, parent_id or 0),
            ).fetchone()[0]
            cursor = conn.execute(
                """
                INSERT INTO norm_categories(org_unit_id, parent_id, name, description, sort_order, active, created_by, created_at)
                VALUES(?,?,?,?,?,1,?,?)
                """,
                (org_unit_id, parent_id, name, description, sort_order, actor["id"], now_iso()),
            )
            write_audit(conn, actor, "norm_category.create", "norm_category", cursor.lastrowid, "规范分类已新增", {"name": name, "parent_id": parent_id}, self.client_address[0])
        return {"message": "分类已新增", "categories": self.list_norm_categories()}

    def update_norm_category(self, category_id):
        """改名：创建人改自己建的，管理员改任何目录。

        「换上级目录」与「停用」仍然只有管理员能做——这两件动的是"目录摆在哪、别人还能
        不能看到这份文档"，跟"给我自己建的东西换个名字"不是一回事，所以留在右侧管理面板，
        不跟着改名一起下放。
        """
        actor = getattr(self, "api_user", None) or self.current_user()
        data = read_json(self)
        with connect() as conn:
            org_unit_id = self.require_current_org_unit_id(conn, actor, "维护规范分类")
            category = conn.execute(
                "SELECT * FROM norm_categories WHERE id=? AND org_unit_id=?",
                (category_id, org_unit_id),
            ).fetchone()
            if not category:
                raise AppError(404, "规范分类不存在")
            if not self.can_rename_norm_category(category, actor):
                raise AppError(403, "只能修改自己创建的目录，其他目录请联系管理员处理")
            is_admin = bool(actor and actor.get("role") == "admin")
            # 非管理员只能碰名字和说明；带上层级/停用字段一律拒绝，不静默忽略——
            # 静默忽略会让人以为"我点过停用了"，而实际什么都没发生。
            if not is_admin and ("parent_id" in data or "active" in data):
                raise AppError(403, "只有管理员能调整目录层级或停用目录")
            name = (data.get("name") or category["name"]).strip()
            if not name:
                raise AppError(400, "请填写分类名称")
            if len(name) > 24:
                raise AppError(400, "分类名称不超过 24 字")
            parent_id = category["parent_id"]
            if "parent_id" in data:
                parent_id = self.resolve_norm_parent(conn, data.get("parent_id"), org_unit_id, category_id)
                children = conn.execute(
                    "SELECT COUNT(*) FROM norm_categories WHERE parent_id=?",
                    (category_id,),
                ).fetchone()[0]
                if children and parent_id is not None:
                    raise AppError(409, f"「{category['name']}」下还有 {children} 个子目录，移进去会变成三级目录")
            if name != category["name"] or parent_id != category["parent_id"]:
                if self.norm_category_name_taken(conn, org_unit_id, parent_id, name, category_id):
                    raise AppError(409, f"该层级下已有分类「{name}」")
            # 只改名字的 PATCH 不带 description，这时要保留原值，否则改个名会把说明清空。
            raw_description = data["description"] if "description" in data else category["description"]
            description = str(raw_description or "").strip()
            active = 1 if str(data.get("active", category["active"])).lower() not in {"0", "false", "no"} else 0
            if not active and category["active"]:
                used = conn.execute(
                    "SELECT COUNT(*) FROM norms WHERE category_id=? AND deleted_at IS NULL",
                    (category_id,),
                ).fetchone()[0]
                if used:
                    raise AppError(409, f"该分类下还有 {used} 条规范，请先移动到其他分类再停用")
                children = conn.execute(
                    "SELECT COUNT(*) FROM norm_categories WHERE parent_id=?",
                    (category_id,),
                ).fetchone()[0]
                if children:
                    raise AppError(409, f"「{category['name']}」下还有 {children} 个子目录，请先移走子目录再停用")
            conn.execute(
                "UPDATE norm_categories SET name=?, description=?, active=?, parent_id=? WHERE id=?",
                (name, description, active, parent_id, category_id),
            )
            write_audit(conn, actor, "norm_category.update", "norm_category", category_id, "规范分类已更新", {"name": name, "active": active, "parent_id": parent_id}, self.client_address[0])
        return {"message": "分类已更新", "categories": self.list_norm_categories()}

    def delete_norm_category(self, category_id):
        """本人建的目录本人可以删，管理员可以删任何目录（含系统预置分类）。"""
        actor = getattr(self, "api_user", None) or self.current_user()
        with connect() as conn:
            org_unit_id = self.require_current_org_unit_id(conn, actor, "删除规范分类")
            category = conn.execute(
                "SELECT * FROM norm_categories WHERE id=? AND org_unit_id=?",
                (category_id, org_unit_id),
            ).fetchone()
            if not category:
                raise AppError(404, "规范分类不存在")
            if not self.can_delete_norm_category(category, actor):
                raise AppError(403, "只能删除自己创建的目录，其他目录请联系管理员处理")
            children = conn.execute(
                "SELECT COUNT(*) FROM norm_categories WHERE parent_id=?",
                (category_id,),
            ).fetchone()[0]
            if children:
                raise AppError(409, f"「{category['name']}」下还有 {children} 个子目录，请先删除或移走子目录")
            used = conn.execute(
                "SELECT COUNT(*) FROM norms WHERE category_id=? AND deleted_at IS NULL",
                (category_id,),
            ).fetchone()[0]
            if used:
                raise AppError(409, f"该分类下还有 {used} 条规范，请先移动到其他分类再删除")
            conn.execute("DELETE FROM norm_categories WHERE id=?", (category_id,))
            write_audit(conn, actor, "norm_category.delete", "norm_category", category_id, "规范分类已删除", {"name": category["name"]}, self.client_address[0])
        return {"message": "分类已删除", "categories": self.list_norm_categories()}

    def list_norms(self, query):
        user = getattr(self, "api_user", None)
        include_abolished = str((query.get("include_abolished") or [""])[0]).lower() in {"1", "true", "yes", "on"}
        keyword = (query.get("q") or [""])[0].strip()
        raw_category = (query.get("category_id") or [""])[0].strip()
        with connect() as conn:
            org_where, org_params = self.organization_current_entity_filter(conn, "n.org_unit_id", user)
            clauses = ["n.deleted_at IS NULL", org_where]
            params = [*org_params]
            if not include_abolished:
                clauses.append("n.status<>'abolished'")
            if raw_category:
                try:
                    category_id = int(raw_category)
                except (TypeError, ValueError):
                    raise AppError(400, "规范分类参数不正确")
                clauses.append("n.category_id=?")
                params.append(category_id)
            if keyword:
                like = f"%{keyword}%"
                clauses.append("(n.title LIKE ? OR n.content LIKE ? OR n.scope LIKE ? OR n.source LIKE ?)")
                params.extend([like, like, like, like])
            rows = rows_to_list(
                conn.execute(
                    f"""
                    SELECT n.*, u.display_name AS created_by_name,
                           c.name AS category_name, c.sort_order AS category_order,
                           c.parent_id AS category_parent_id, pc.name AS category_parent_name
                    FROM norms n
                    LEFT JOIN users u ON u.id=n.created_by
                    LEFT JOIN norm_categories c ON c.id=n.category_id
                    LEFT JOIN norm_categories pc ON pc.id=c.parent_id
                    WHERE {' AND '.join(clauses)}
                    ORDER BY COALESCE(pc.sort_order, c.sort_order, 9999), c.parent_id IS NOT NULL,
                             COALESCE(c.sort_order, 9999), n.sort_order, n.id
                    """,
                    params,
                ).fetchall()
            )
        for row in rows:
            row["state"] = norm_state(row)
        return rows

    def find_norm(self, conn, norm_id, user):
        org_where, org_params = self.organization_current_entity_filter(conn, "n.org_unit_id", user)
        norm = conn.execute(
            f"SELECT * FROM norms n WHERE n.id=? AND n.deleted_at IS NULL AND {org_where}",
            [norm_id, *org_params],
        ).fetchone()
        if not norm:
            raise AppError(404, "规范条目不存在")
        return norm

    def can_edit_norm(self, norm, user):
        if not user:
            return False
        if user.get("role") == "admin":
            return True
        return int(norm["created_by"] or 0) == int(user["id"])

    def resolve_norm_category(self, conn, raw_value, org_unit_id):
        try:
            category_id = int(raw_value or 0)
        except (TypeError, ValueError):
            raise AppError(400, "规范分类参数不正确")
        if not category_id:
            raise AppError(400, "请选择规范分类")
        category = conn.execute(
            "SELECT id, name, active FROM norm_categories WHERE id=? AND org_unit_id=?",
            (category_id, org_unit_id),
        ).fetchone()
        if not category:
            raise AppError(404, "规范分类不存在")
        if not category["active"]:
            raise AppError(400, f"分类「{category['name']}」已停用，请选择其他分类")
        return category_id

    def create_norm(self, user=None):
        actor = user or self.current_user()
        data = read_json(self)
        title = (data.get("title") or "").strip()
        if not title:
            raise AppError(400, "请填写一句话规则，例如「提交代码前必须通过静态检查」")
        if len(title) > 120:
            raise AppError(400, "一句话规则不要超过 120 字")
        content = (data.get("content") or "").strip()
        scope = (data.get("scope") or "").strip()
        source = (data.get("source") or "").strip()
        effective_from = parse_norm_date(data.get("effective_from"), "生效日期") or today_iso()
        effective_to = parse_norm_date(data.get("effective_to"), "失效日期")
        if effective_to and effective_to < effective_from:
            raise AppError(400, "失效日期不能早于生效日期")
        with connect() as conn:
            org_unit_id = self.require_current_org_unit_id(conn, actor, "记录团队规范")
            category_id = self.resolve_norm_category(conn, data.get("category_id"), org_unit_id)
            sort_order = conn.execute(
                "SELECT COALESCE(MAX(sort_order), 0) + 1 FROM norms WHERE org_unit_id=? AND category_id=?",
                (org_unit_id, category_id),
            ).fetchone()[0]
            cursor = conn.execute(
                """
                INSERT INTO norms(org_unit_id, category_id, title, content, scope, source, status,
                                  effective_from, effective_to, sort_order, created_by, updated_by,
                                  created_at, updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    org_unit_id, category_id, title, content, scope, source, "active",
                    effective_from, effective_to, sort_order, actor["id"], actor["id"],
                    now_iso(), now_iso(),
                ),
            )
            norm_id = cursor.lastrowid
            self.bind_norm_images(conn, norm_id, org_unit_id, content)
            write_audit(conn, actor, "norm.create", "norm", norm_id, "团队规范条目已记录", {"title": title, "category_id": category_id}, self.client_address[0])
        return {"message": "规范已记入文档", "norms": self.list_norms({})}

    def update_norm(self, norm_id, user=None):
        actor = user or self.current_user()
        data = read_json(self)
        with connect() as conn:
            norm = self.find_norm(conn, norm_id, actor)
            if not self.can_edit_norm(norm, actor):
                raise AppError(403, "只能修改自己记录的规范条目，或联系管理员处理")
            title = (data.get("title") or norm["title"]).strip()
            if not title:
                raise AppError(400, "请填写一句话规则")
            if len(title) > 120:
                raise AppError(400, "一句话规则不要超过 120 字")
            status = str(data.get("status") or norm["status"] or "active").strip()
            if status not in NORM_STATUSES:
                raise AppError(400, "规范状态不正确")
            if status == "pending" and actor.get("role") != "admin":
                raise AppError(403, "仅管理员可以标记待确认")
            content = (data.get("content") if "content" in data else norm["content"] or "")
            scope = (data.get("scope") if "scope" in data else norm["scope"] or "")
            source = (data.get("source") if "source" in data else norm["source"] or "")
            effective_from = parse_norm_date(
                data.get("effective_from") if "effective_from" in data else norm["effective_from"],
                "生效日期",
            ) or today_iso()
            effective_to = parse_norm_date(
                data.get("effective_to") if "effective_to" in data else norm["effective_to"],
                "失效日期",
            )
            if effective_to and effective_to < effective_from:
                raise AppError(400, "失效日期不能早于生效日期")
            category_id = norm["category_id"]
            if data.get("category_id"):
                category_id = self.resolve_norm_category(conn, data.get("category_id"), norm["org_unit_id"])
            conn.execute(
                """
                UPDATE norms
                SET category_id=?, title=?, content=?, scope=?, source=?, status=?,
                    effective_from=?, effective_to=?, updated_by=?, updated_at=?
                WHERE id=?
                """,
                (
                    category_id, title, str(content or "").strip(), str(scope or "").strip(), str(source or "").strip(),
                    status, effective_from, effective_to, actor["id"], now_iso(), norm_id,
                ),
            )
            self.bind_norm_images(conn, norm_id, norm["org_unit_id"], content)
            write_audit(conn, actor, "norm.update", "norm", norm_id, "团队规范条目已更新", {"title": title, "status": status}, self.client_address[0])
        return {"message": "规范已更新", "norms": self.list_norms({})}

    def delete_norm(self, norm_id, user=None):
        actor = user or self.current_user()
        with connect() as conn:
            norm = self.find_norm(conn, norm_id, actor)
            conn.execute(
                "UPDATE norms SET deleted_at=?, deleted_by=? WHERE id=?",
                (now_iso(), actor["id"], norm_id),
            )
            add_recycle_record(
                conn,
                "norm",
                norm_id,
                norm["title"],
                actor,
                {"title": norm["title"], "category_id": norm["category_id"]},
            )
            write_audit(conn, actor, "norm.delete", "norm", norm_id, "团队规范条目已删除", {"title": norm["title"]}, self.client_address[0])
        return {"message": "规范已删除", "norms": self.list_norms({})}

    def assemble_norm_documents(self, conn, user):
        """One document per category, its clauses numbered from 1 inside that document.

        A category owns a document instead of being a chapter of one big file. Because
        each document stands alone, its clauses are numbered 1, 2, 3 ... within that
        document instead of carrying the category index as a prefix. Every category is
        listed even when empty, because the navigation mirrors the shelves the team
        maintains.

        Categories may sit two levels deep. A sub-shelf is a shelf of its own, not a
        section of its parent: the parent document shows only the clauses filed directly
        under it, so filing a rule under `python研发流程` never leaks it into
        `研发流程`. The tree order is inherited from the shelves so the navigation can
        rebuild the nesting from `parent_id` alone.

        This document is the only place norms are read and edited — there is no separate
        entry list — so each article carries `status` (to fill the edit form) and
        `can_edit` (author plus administrators, from the same `can_edit_norm` that
        `update_norm` enforces) so the client can draw an edit button without re-deriving
        the ownership rule.
        """
        org_where, org_params = self.organization_current_entity_filter(conn, "n.org_unit_id", user)
        cat_where, cat_params = self.organization_current_entity_filter(conn, "c.org_unit_id", user)
        categories = rows_to_list(
            conn.execute(
                f"""
                SELECT c.id, c.parent_id, c.name, c.description, c.sort_order,
                       c.created_by, u.display_name AS created_by_name,
                       (SELECT COUNT(*) FROM norm_categories ch WHERE ch.parent_id=c.id) AS child_count
                FROM norm_categories c
                LEFT JOIN norm_categories p ON p.id=c.parent_id
                LEFT JOIN users u ON u.id=c.created_by
                WHERE {cat_where}
                ORDER BY COALESCE(p.sort_order, c.sort_order), c.parent_id IS NOT NULL, c.sort_order, c.id
                """,
                cat_params,
            ).fetchall()
        )
        articles = rows_to_list(
            conn.execute(
                f"""
                SELECT n.id, n.category_id, n.title, n.content, n.scope, n.source, n.status,
                       n.effective_from, n.effective_to, n.sort_order, n.created_at, n.created_by,
                       u.display_name AS created_by_name
                FROM norms n
                LEFT JOIN users u ON u.id=n.created_by
                WHERE n.deleted_at IS NULL AND n.status='active' AND {org_where}
                  AND (n.effective_to IS NULL OR n.effective_to='' OR n.effective_to >= ?)
                ORDER BY n.sort_order, n.id
                """,
                [*org_params, today_iso()],
            ).fetchall()
        )
        images_by_norm = {}
        article_ids = [row["id"] for row in articles]
        if article_ids:
            placeholders = ",".join("?" for _ in article_ids)
            for row in rows_to_list(
                conn.execute(
                    f"""
                    SELECT id, norm_id, filename, mime_type, byte_size, caption, created_at
                    FROM norm_images
                    WHERE deleted_at IS NULL AND norm_id IN ({placeholders})
                    ORDER BY norm_id, id
                    """,
                    article_ids,
                ).fetchall()
            ):
                # `?v=` makes the URL change whenever the row is rewritten, so the long
                # cache lifetime below cannot serve a stale picture.
                version = "".join(ch for ch in str(row.get("created_at") or "") if ch.isdigit())
                row["url"] = f"/api/norm-images/{row['id']}?v={version or row['id']}"
                images_by_norm.setdefault(row["norm_id"], []).append(row)
        grouped = {}
        for row in articles:
            grouped.setdefault(row["category_id"], []).append(row)
        by_id = {category["id"]: category for category in categories}
        buckets = list(categories)
        known = {category["id"] for category in categories}
        if any(row["category_id"] not in known for row in articles):
            buckets.append(
                {
                    "id": None,
                    "parent_id": None,
                    "name": NORM_OTHER_CHAPTER_NAME,
                    "description": "尚未归入分类的规范条目",
                    "child_count": 0,
                    "created_by": None,
                    "created_by_name": "",
                }
            )
        documents = []
        for category in buckets:
            category_id = category["id"]
            name = category["name"]
            description = category["description"] or ""
            parent = by_id.get(category["parent_id"]) if category.get("parent_id") else None
            chapter = {"name": name, "description": description, "articles": []}
            for article_index, row in enumerate(grouped.get(category_id) or [], start=1):
                chapter["articles"].append(
                    {
                        "no": str(article_index),
                        "id": row["id"],
                        "title": row["title"],
                        "content": row["content"] or "",
                        "scope": row["scope"] or "",
                        "source": row["source"] or "",
                        "status": row["status"],
                        "effective_from": row["effective_from"] or "",
                        "effective_to": row["effective_to"] or "",
                        "created_by_name": row["created_by_name"] or "",
                        "created_at": row["created_at"],
                        # 谁能改这条：作者本人 + 管理员。规则和后端 update_norm 用的是同一个
                        # can_edit_norm()，前端只按这个标记画"编辑"按钮，不拿 created_by 再算一遍。
                        "can_edit": self.can_edit_norm(row, user),
                        # 正文里的 [[img:id]] 标记靠这张表还原成图片；表里没有的 id 说明
                        # 图片已失效，前端据此不画裂图。
                        "images": images_by_norm.get(row["id"], []),
                    }
                )
            title = name if name.endswith("规范") else f"{name}规范"
            documents.append(
                {
                    "category_id": category_id,
                    "parent_id": category.get("parent_id"),
                    "parent_name": parent["name"] if parent else "",
                    "level": 2 if parent else 1,
                    "child_count": int(category.get("child_count") or 0),
                    "name": name,
                    "description": description,
                    "title": title,
                    "created_by_name": category.get("created_by_name") or "",
                    "can_delete": self.can_delete_norm_category(category, user),
                    "can_rename": self.can_rename_norm_category(category, user),
                    "article_count": len(chapter["articles"]),
                    "chapters": [chapter],
                    "markdown": build_norm_markdown(title, [chapter]),
                }
            )
        return documents

    def norm_document(self):
        """Every category as its own document, assembled from `norms` on every read.

        Nothing is frozen here: a document is the live projection of the entries, so
        recording or editing a norm shows up immediately.
        """
        user = getattr(self, "api_user", None)
        with connect() as conn:
            documents = self.assemble_norm_documents(conn, user)
            org_where, org_params = self.organization_current_entity_filter(conn, "n.org_unit_id", user)
            counts = conn.execute(
                f"""
                SELECT COUNT(*) AS total,
                       SUM(CASE WHEN status='active' THEN 1 ELSE 0 END) AS active_count,
                       SUM(CASE WHEN status='pending' THEN 1 ELSE 0 END) AS pending_count,
                       SUM(CASE WHEN status='abolished' THEN 1 ELSE 0 END) AS abolished_count
                FROM norms n
                WHERE n.deleted_at IS NULL AND {org_where}
                """,
                org_params,
            ).fetchone()
            document = {
                "title": self.norm_document_title(conn),
                "generated_at": now_iso(),
                "documents": documents,
                "stats": {
                    "total": int(counts["total"] or 0) if counts else 0,
                    "active": int(counts["active_count"] or 0) if counts else 0,
                    "pending": int(counts["pending_count"] or 0) if counts else 0,
                    "abolished": int(counts["abolished_count"] or 0) if counts else 0,
                    "category_count": len(documents),
                },
            }
        return {"document": document}

    def store_norm_image_file(self, image):
        """Write the bytes under `uploads/norms/YYYY/MM/` and return the relative path.

        The stored name is generated here and never derived from the upload: the original
        filename is kept in the database for display only, so nothing a user types can
        reach the filesystem. Splitting by month keeps any one directory small.
        """
        stamp = dt.datetime.now()
        extension = NORM_IMAGE_TYPES[image["mime_type"]][1]
        relative = f"norms/{stamp:%Y/%m}/{uuid.uuid4().hex}{extension}"
        target = norm_upload_path(relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(image["data"])
        return relative

    def sweep_staged_norm_images(self, conn, keep_hours=24):
        """Drop images that were uploaded but never referenced by a saved clause.

        Runs opportunistically on upload rather than on a timer: abandoning an upload is
        the only thing that creates a staged image, so that is exactly when it is cheapest
        to notice. A file that cannot be removed must not block the upload — the row goes
        either way, otherwise the sweep would retry it on every future upload forever.
        """
        cutoff = (dt.datetime.now() - dt.timedelta(hours=keep_hours)).replace(microsecond=0).isoformat()
        staged = rows_to_list(
            conn.execute(
                """
                SELECT id, stored_path FROM norm_images
                WHERE deleted_at IS NULL AND norm_id IS NULL AND created_at < ?
                """,
                (cutoff,),
            ).fetchall()
        )
        for row in staged:
            try:
                path = norm_upload_path(row["stored_path"])
                if path.is_file():
                    path.unlink()
            except (OSError, AppError):
                pass
            conn.execute("DELETE FROM norm_images WHERE id=?", (row["id"],))

    def create_norm_image(self, user=None):
        """Stage one illustration for a clause. It is bound when the clause is saved."""
        actor = user or self.current_user()
        image = decode_norm_image(read_json(self))
        with connect() as conn:
            org_unit_id = self.require_current_org_unit_id(conn, actor, "上传规范插图")
            stored_path = self.store_norm_image_file(image)
            cursor = conn.execute(
                """
                INSERT INTO norm_images(org_unit_id, stored_path, filename, mime_type, byte_size,
                                        created_by, created_at)
                VALUES(?,?,?,?,?,?,?)
                """,
                (
                    org_unit_id, stored_path, image["filename"], image["mime_type"],
                    len(image["data"]), actor["id"], now_iso(),
                ),
            )
            image_id = cursor.lastrowid
            self.sweep_staged_norm_images(conn)
            write_audit(
                conn, actor, "norm_image.upload", "norm_image", image_id, "规范插图已上传",
                {"filename": image["filename"], "byte_size": len(image["data"])},
                self.client_address[0],
            )
        return {
            "message": "图片已插入",
            "image": {
                "id": image_id,
                "url": f"/api/norm-images/{image_id}",
                "filename": image["filename"],
                "byte_size": len(image["data"]),
                "marker": f"[[img:{image_id}]]",
            },
        }

    def require_norm_image_visible(self, conn, image, user):
        """Reuse the organization-scope filter rather than restating the visibility rule."""
        org_where, org_params = self.organization_current_entity_filter(conn, "i.org_unit_id", user)
        visible = conn.execute(
            f"SELECT 1 FROM norm_images i WHERE i.id=? AND {org_where}",
            [image["id"], *org_params],
        ).fetchone()
        if not visible:
            raise AppError(403, "无权查看该图片")

    def read_norm_image(self, image_id, user):
        """Return (row, bytes) for one illustration, after the module and scope checks.

        Served through its own route on purpose: the static handler performs no auth at
        all, and its `no-store` header would re-send every picture on every scroll.
        """
        with connect() as conn:
            image = conn.execute(
                """
                SELECT id, norm_id, org_unit_id, stored_path, filename, mime_type, byte_size
                FROM norm_images
                WHERE id=? AND deleted_at IS NULL
                """,
                (image_id,),
            ).fetchone()
            if not image:
                raise AppError(404, "图片不存在")
            self.require_norm_image_visible(conn, image, user)
        path = norm_upload_path(image["stored_path"])
        if not path.is_file():
            raise AppError(404, "图片文件已不存在")
        return image, path.read_bytes()

    def bind_norm_images(self, conn, norm_id, org_unit_id, content):
        """Re-point the illustrations a clause references and release the ones it dropped.

        Uploading only stages an image; saving the clause is what makes it count, so a user
        who uploads and then cancels leaves nothing behind but a staged row the sweep
        collects. Dropped images are released rather than deleted, so pasting a marker back
        keeps working; whatever stays unreferenced is swept once the window passes.
        """
        image_ids = norm_image_ids_in(content)
        if len(image_ids) > NORM_IMAGE_MAX_PER_NORM:
            raise AppError(400, f"单条规范最多插入 {NORM_IMAGE_MAX_PER_NORM} 张图片")
        if not image_ids:
            conn.execute("UPDATE norm_images SET norm_id=NULL WHERE norm_id=?", (norm_id,))
            return
        placeholders = ",".join("?" for _ in image_ids)
        available = {
            row["id"]
            for row in conn.execute(
                f"""
                SELECT id FROM norm_images
                WHERE deleted_at IS NULL AND org_unit_id=? AND id IN ({placeholders})
                """,
                [org_unit_id, *image_ids],
            ).fetchall()
        }
        if any(image_id not in available for image_id in image_ids):
            raise AppError(400, "正文里有图片已失效，请重新插入后再保存")
        conn.execute(
            f"UPDATE norm_images SET norm_id=? WHERE id IN ({placeholders})",
            [norm_id, *image_ids],
        )
        conn.execute(
            f"UPDATE norm_images SET norm_id=NULL WHERE norm_id=? AND id NOT IN ({placeholders})",
            [norm_id, *image_ids],
        )


