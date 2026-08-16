from ..permissions import *


class CollaborationHandlerMixin:
    def list_team_moments(self, user=None, query=None):
        query = query or {}
        year = (query.get("year") or [""])[0].strip()
        keyword = (query.get("keyword") or [""])[0].strip()
        if year and (len(year) != 4 or not year.isdigit()):
            raise AppError(400, "年份格式不正确")
        if len(keyword) > 80:
            raise AppError(400, "搜索关键词最多 80 个字符")
        with connect() as conn:
            org_where, org_params = self.organization_current_entity_filter(conn, "m.org_unit_id", user)
            where = ["m.deleted_at IS NULL", org_where]
            params = list(org_params)
            if year:
                where.append("substr(m.event_date, 1, 4)=?")
                params.append(year)
            if keyword:
                where.append("(m.title LIKE ? OR m.story LIKE ? OR COALESCE(o.name, '') LIKE ? OR u.display_name LIKE ?)")
                like = f"%{keyword}%"
                params.extend([like, like, like, like])
            moments = rows_to_list(conn.execute(
                f"""
                SELECT m.id, m.org_unit_id, m.title, m.story, m.category, m.event_date,
                       m.created_by, m.created_at, m.updated_at,
                       u.display_name AS created_by_name, o.name AS org_unit_name
                FROM team_moments m
                JOIN users u ON u.id=m.created_by
                LEFT JOIN org_units o ON o.id=m.org_unit_id
                WHERE {' AND '.join(where)}
                ORDER BY m.event_date DESC, m.id DESC
                LIMIT 300
                """,
                params,
            ).fetchall())
            moment_ids = [item["id"] for item in moments]
            images_by_moment = {moment_id: [] for moment_id in moment_ids}
            if moment_ids:
                placeholders = ",".join("?" for _ in moment_ids)
                images = rows_to_list(conn.execute(
                    f"""
                    SELECT id, moment_id, filename, mime_type, sort_order, created_at
                    FROM team_moment_images
                    WHERE moment_id IN ({placeholders})
                    ORDER BY moment_id, sort_order, id
                    """,
                    moment_ids,
                ).fetchall())
                for image in images:
                    cache_version = "".join(character for character in str(image.get("created_at") or "") if character.isdigit())
                    image["url"] = f"/api/team-moment-images/{image['id']}?v={cache_version or image['id']}"
                    images_by_moment[image["moment_id"]].append(image)
        for moment in moments:
            moment["images"] = images_by_moment.get(moment["id"], [])
            moment["inherited"] = False
            moment["mine"] = bool(user and moment["created_by"] == user["id"])
        return moments

    def normalize_team_moment_payload(self, data, partial=False):
        payload = {}
        if not partial or "title" in data:
            title = str(data.get("title") or "").strip()
            if not title or len(title) > 100:
                raise AppError(400, "标题为必填项，最多 100 个字符")
            payload["title"] = title
        if not partial or "story" in data:
            story = str(data.get("story") or "").strip()
            if not story or len(story) > 5000:
                raise AppError(400, "事迹为必填项，最多 5000 个字符")
            payload["story"] = story
        if not partial or "event_date" in data:
            event_date = str(data.get("event_date") or "").strip()
            try:
                dt.date.fromisoformat(event_date)
            except ValueError as exc:
                raise AppError(400, "事件日期格式不正确") from exc
            payload["event_date"] = event_date
        if not partial or "category" in data:
            category = str(data.get("category") or "milestone").strip().lower()
            if category not in TEAM_MOMENT_CATEGORIES:
                raise AppError(400, "团队时刻分类不正确")
            payload["category"] = category
        return payload

    def create_team_moment(self, user):
        data = read_json(self)
        payload = self.normalize_team_moment_payload(data)
        raw_images = data.get("images") or []
        if not isinstance(raw_images, list) or len(raw_images) > TEAM_MOMENT_MAX_IMAGES:
            raise AppError(400, f"每条团队时刻最多上传 {TEAM_MOMENT_MAX_IMAGES} 张图片")
        images = [decode_team_moment_image(value, index) for index, value in enumerate(raw_images)]
        with connect() as conn:
            context = self.organization_context(conn, user)
            selected = context.get("selected")
            if not selected or selected["id"] not in context["visible_ids"]:
                raise AppError(403, "当前团队不可新增团队时刻")
            created_at = now_iso()
            cursor = conn.execute(
                """
                INSERT INTO team_moments(org_unit_id, title, story, category, event_date, created_by, created_at, updated_at)
                VALUES(?,?,?,?,?,?,?,?)
                """,
                (selected["id"], payload["title"], payload["story"], payload["category"], payload["event_date"], user["id"], created_at, created_at),
            )
            moment_id = cursor.lastrowid
            for index, image in enumerate(images):
                conn.execute(
                    """
                    INSERT INTO team_moment_images(moment_id, filename, mime_type, image_data, sort_order, created_at)
                    VALUES(?,?,?,?,?,?)
                    """,
                    (moment_id, image["filename"], image["mime_type"], image["data"], index, created_at),
                )
            write_audit(conn, user, "team_moment.create", "team_moment", moment_id, "团队时刻已发布", {"title": payload["title"], "image_count": len(images)}, self.client_address[0])
        return {"message": "团队时刻已发布", "moments": self.list_team_moments(user)}

    def update_team_moment(self, moment_id, user):
        data = read_json(self)
        payload = self.normalize_team_moment_payload(data, partial=True)
        raw_images = data.get("new_images") or []
        remove_ids = data.get("remove_image_ids") or []
        if not isinstance(raw_images, list) or not isinstance(remove_ids, list):
            raise AppError(400, "图片更新格式不正确")
        images = [decode_team_moment_image(value, index) for index, value in enumerate(raw_images)]
        try:
            remove_ids = sorted({int(value) for value in remove_ids})
        except (TypeError, ValueError) as exc:
            raise AppError(400, "待删除图片标识不正确") from exc
        with connect() as conn:
            self.require_team_moment_access(conn, moment_id, user, write=True)
            existing_images = conn.execute("SELECT id FROM team_moment_images WHERE moment_id=? ORDER BY sort_order, id", (moment_id,)).fetchall()
            existing_ids = {row["id"] for row in existing_images}
            if any(image_id not in existing_ids for image_id in remove_ids):
                raise AppError(400, "待删除图片不属于当前团队时刻")
            remaining_count = len(existing_ids) - len(remove_ids) + len(images)
            if remaining_count > TEAM_MOMENT_MAX_IMAGES:
                raise AppError(400, f"每条团队时刻最多保留 {TEAM_MOMENT_MAX_IMAGES} 张图片")
            fields = [f"{key}=?" for key in payload]
            values = list(payload.values())
            fields.append("updated_at=?")
            values.extend([now_iso(), moment_id])
            conn.execute(f"UPDATE team_moments SET {', '.join(fields)} WHERE id=?", values)
            if remove_ids:
                placeholders = ",".join("?" for _ in remove_ids)
                conn.execute(f"DELETE FROM team_moment_images WHERE moment_id=? AND id IN ({placeholders})", [moment_id, *remove_ids])
            start_order = conn.execute("SELECT COALESCE(MAX(sort_order), -1)+1 FROM team_moment_images WHERE moment_id=?", (moment_id,)).fetchone()[0]
            for index, image in enumerate(images):
                conn.execute(
                    "INSERT INTO team_moment_images(moment_id, filename, mime_type, image_data, sort_order, created_at) VALUES(?,?,?,?,?,?)",
                    (moment_id, image["filename"], image["mime_type"], image["data"], start_order + index, now_iso()),
                )
            write_audit(conn, user, "team_moment.update", "team_moment", moment_id, "团队时刻已更新", {"fields": list(payload), "added_images": len(images), "removed_images": len(remove_ids)}, self.client_address[0])
        return {"message": "团队时刻已更新", "moments": self.list_team_moments(user)}

    def delete_team_moment(self, moment_id, user):
        with connect() as conn:
            moment = self.require_team_moment_access(conn, moment_id, user, write=True)
            conn.execute("UPDATE team_moments SET deleted_at=?, deleted_by=? WHERE id=?", (now_iso(), user["id"], moment_id))
            add_recycle_record(conn, "team_moment", moment_id, moment["title"], user)
            write_audit(conn, user, "team_moment.delete", "team_moment", moment_id, "团队时刻已移入回收站", {}, self.client_address[0])
        return {"message": "团队时刻已移入回收站", "moments": self.list_team_moments(user)}

    def list_team_posts(self, user=None):
        with connect() as conn:
            context = self.organization_context(conn, user)
            org_where, org_params = self.organization_entity_filter(conn, "p.org_unit_id", user)
            inherited_ids = context["inherited_ids"]
            if inherited_ids:
                inherited_placeholders = ",".join("?" for _ in inherited_ids)
                inherited_where = f"p.category='announcement' AND p.org_unit_id IN ({inherited_placeholders})"
            else:
                inherited_where = "1=0"
            posts = rows_to_list(
                conn.execute(
                    f"""
                    SELECT p.*, u.display_name, u.username, o.name AS org_unit_name
                    FROM team_posts p
                    JOIN users u ON u.id = p.user_id
                    LEFT JOIN org_units o ON o.id=p.org_unit_id
                    WHERE p.deleted_at IS NULL AND ({org_where} OR ({inherited_where}))
                    ORDER BY p.pinned DESC, COALESCE(p.updated_at, p.created_at) DESC, p.id DESC
                    """,
                    [*org_params, *inherited_ids],
                ).fetchall()
            )
            if not posts:
                return []
            post_ids = [post["id"] for post in posts]
            placeholders = ",".join("?" for _ in post_ids)
            replies = rows_to_list(
                conn.execute(
                    f"""
                    SELECT r.*, u.display_name
                    FROM team_post_replies r
                    JOIN users u ON u.id = r.user_id
                    WHERE r.post_id IN ({placeholders}) AND r.deleted_at IS NULL
                    ORDER BY r.created_at ASC, r.id ASC
                    """,
                    post_ids,
                ).fetchall()
            )
            reaction_params = [user["id"] if user else -1, *post_ids]
            reactions = rows_to_list(
                conn.execute(
                    f"""
                    SELECT post_id, reaction, COUNT(*) AS count,
                           SUM(CASE WHEN user_id=? THEN 1 ELSE 0 END) AS mine
                    FROM team_post_reactions
                    WHERE post_id IN ({placeholders})
                    GROUP BY post_id, reaction
                    """,
                    reaction_params,
                ).fetchall()
            )
            reply_ids = [reply["id"] for reply in replies]
            reply_reactions = []
            if reply_ids:
                reply_placeholders = ",".join("?" for _ in reply_ids)
                reply_reactions = rows_to_list(
                    conn.execute(
                        f"""
                        SELECT reply_id, reaction, COUNT(*) AS count,
                               SUM(CASE WHEN user_id=? THEN 1 ELSE 0 END) AS mine
                        FROM team_reply_reactions
                        WHERE reply_id IN ({reply_placeholders})
                        GROUP BY reply_id, reaction
                        """,
                        [user["id"] if user else -1, *reply_ids],
                    ).fetchall()
                )
        reaction_rank = {reaction: index for index, reaction in enumerate(TEAM_REACTIONS)}
        reaction_map = {}
        for reaction in reactions:
            reaction_map.setdefault(reaction["post_id"], []).append({
                "reaction": reaction["reaction"],
                "count": reaction["count"],
                "mine": bool(reaction["mine"]),
            })
        reply_reaction_map = {}
        for reaction in reply_reactions:
            reply_reaction_map.setdefault(reaction["reply_id"], []).append({
                "reaction": reaction["reaction"],
                "count": reaction["count"],
                "mine": bool(reaction["mine"]),
            })
        reply_lookup = {}
        root_replies = {}
        reply_count_map = {}
        latest_reply_map = {}
        for reply in replies:
            reply["reactions"] = sorted(
                reply_reaction_map.get(reply["id"], []),
                key=lambda item: (reaction_rank.get(item["reaction"], 99), -int(item["count"] or 0), item["reaction"]),
            )
            reply["replies"] = []
            reply["mine"] = bool(user and reply["user_id"] == user["id"])
            reply_lookup[reply["id"]] = reply
            reply_count_map[reply["post_id"]] = reply_count_map.get(reply["post_id"], 0) + 1
            latest_reply_map[reply["post_id"]] = reply
        for reply in replies:
            parent = reply_lookup.get(reply.get("parent_reply_id"))
            if parent and parent["post_id"] == reply["post_id"]:
                parent["replies"].append(reply)
            else:
                root_replies.setdefault(reply["post_id"], []).append(reply)
        for post in posts:
            post["inherited"] = post["org_unit_id"] not in context["visible_ids"]
            post["replies"] = root_replies.get(post["id"], [])
            post["mine"] = bool(user and post["user_id"] == user["id"])
            post["reply_count"] = reply_count_map.get(post["id"], 0)
            latest_reply = latest_reply_map.get(post["id"])
            post["last_reply_at"] = latest_reply.get("created_at") if latest_reply else None
            post["last_reply_name"] = latest_reply.get("display_name") if latest_reply else None
            post["reactions"] = sorted(
                reaction_map.get(post["id"], []),
                key=lambda item: (reaction_rank.get(item["reaction"], 99), -int(item["count"] or 0), item["reaction"]),
            )
        return posts

    def get_team_post(self, post_id, user=None):
        with connect() as conn:
            self.require_team_post_read_access(conn, post_id, user)
            conn.execute("UPDATE team_posts SET view_count=view_count+1 WHERE id=?", (post_id,))
        result = next((item for item in self.list_team_posts(user) if item["id"] == post_id), None)
        if not result:
            raise AppError(404, "讨论主题不存在")
        return {"post": result}

    def create_team_post(self, user):
        data = read_json(self)
        category = str(data.get("category") or "general").strip()
        if category not in TEAM_POST_CATEGORIES:
            raise AppError(400, "讨论分类不正确")
        if category == "announcement" and user.get("role") != "admin":
            raise AppError(403, "仅管理员可发布团队公告")
        kind = "roast" if category == "roast" else "comment"
        title = (data.get("title") or "").strip()
        content = (data.get("content") or "").strip()
        if not title:
            title = content[:40]
        if not title:
            raise AppError(400, "主题标题不能为空")
        if len(title) > 80:
            raise AppError(400, "主题标题最多 80 字")
        if not content:
            raise AppError(400, "内容不能为空")
        if len(content) > 2000:
            raise AppError(400, "讨论内容最多 2000 字")
        created_at = now_iso()
        with connect() as conn:
            org_context = self.organization_context(conn, user)
            org_unit_id = org_context["selected"]["id"] if org_context["selected"] else user.get("org_unit_id")
            cursor = conn.execute(
                """
                INSERT INTO team_posts(user_id, kind, title, category, status, pinned, view_count, content, org_unit_id, updated_at, created_at)
                VALUES(?,?,?,?, 'open', 0, 0, ?, ?, ?, ?)
                """,
                (user["id"], kind, title, category, content, org_unit_id, created_at, created_at),
            )
            write_audit(conn, user, "team_post.create", "team_post", cursor.lastrowid, "团队讨论主题已发布", {"title": title, "category": category}, self.client_address[0])
        return {"message": "已发布", "posts": self.list_team_posts(user)}

    def update_team_post(self, post_id, user):
        data = read_json(self)
        with connect() as conn:
            post = conn.execute("SELECT * FROM team_posts WHERE id=? AND deleted_at IS NULL", (post_id,)).fetchone()
            if not post:
                raise AppError(404, "讨论主题不存在")
            self.require_org_unit_access(conn, post["org_unit_id"], user)
            is_admin = user.get("role") == "admin"
            is_owner = post["user_id"] == user["id"]
            if not is_admin and not is_owner:
                raise AppError(403, "只能修改自己发布的主题")
            fields = []
            values = []
            if "title" in data:
                title = str(data.get("title") or "").strip()
                if not title or len(title) > 80:
                    raise AppError(400, "主题标题需为 1 至 80 字")
                fields.append("title=?")
                values.append(title)
            if "content" in data:
                content = str(data.get("content") or "").strip()
                if not content or len(content) > 2000:
                    raise AppError(400, "讨论内容需为 1 至 2000 字")
                fields.append("content=?")
                values.append(content)
            if "category" in data:
                category = str(data.get("category") or "").strip()
                if category not in TEAM_POST_CATEGORIES:
                    raise AppError(400, "讨论分类不正确")
                if category == "announcement" and not is_admin:
                    raise AppError(403, "仅管理员可发布团队公告")
                fields.extend(["category=?", "kind=?"])
                values.extend([category, "roast" if category == "roast" else "comment"])
            if "status" in data:
                status = str(data.get("status") or "").strip()
                if status not in TEAM_POST_STATUSES:
                    raise AppError(400, "讨论状态不正确")
                fields.append("status=?")
                values.append(status)
            if "pinned" in data:
                if not is_admin:
                    raise AppError(403, "仅管理员可置顶主题")
                fields.append("pinned=?")
                values.append(1 if data.get("pinned") else 0)
            if not fields:
                raise AppError(400, "没有可更新字段")
            fields.append("updated_at=?")
            values.append(now_iso())
            values.append(post_id)
            conn.execute(f"UPDATE team_posts SET {', '.join(fields)} WHERE id=?", values)
            write_audit(conn, user, "team_post.update", "team_post", post_id, "团队讨论主题已更新", {"fields": list(data.keys())}, self.client_address[0])
        return {"message": "主题已更新", "posts": self.list_team_posts(user)}

    def delete_team_post(self, post_id, user):
        with connect() as conn:
            post = conn.execute(
                "SELECT id, user_id, title, deleted_at, org_unit_id FROM team_posts WHERE id=?",
                (post_id,),
            ).fetchone()
            if not post:
                raise AppError(404, "讨论主题不存在")
            self.require_org_unit_access(conn, post["org_unit_id"], user)
            if post["user_id"] != user["id"] and user.get("role") != "admin":
                raise AppError(403, "只能删除自己发布的主题")
            if post["deleted_at"]:
                raise AppError(400, "讨论主题已经在回收站中")
            conn.execute(
                "UPDATE team_posts SET deleted_at=?, deleted_by=? WHERE id=?",
                (now_iso(), user["id"], post_id),
            )
            add_recycle_record(
                conn,
                "team_post",
                post_id,
                (post["title"] or "团队讨论")[:60],
                user,
                {},
            )
            write_audit(
                conn,
                user,
                "team_post.delete",
                "team_post",
                post_id,
                "团队讨论主题已删除",
                {},
                self.client_address[0],
            )
        return {"message": "讨论主题已移入回收站", "posts": self.list_team_posts(user)}

    def create_team_post_reply(self, post_id, user):
        data = read_json(self)
        content = (data.get("content") or "").strip()
        if not content:
            raise AppError(400, "回复内容不能为空")
        if len(content) > 200:
            raise AppError(400, "回复最多 200 字")
        parent_reply_id = data.get("parent_reply_id") or None
        if parent_reply_id is not None:
            try:
                parent_reply_id = int(parent_reply_id)
            except (TypeError, ValueError):
                raise AppError(400, "回复层级不正确")
        with connect() as conn:
            self.require_team_post_read_access(conn, post_id, user)
            if parent_reply_id is not None:
                parent = conn.execute(
                    "SELECT id FROM team_post_replies WHERE id=? AND post_id=? AND deleted_at IS NULL",
                    (parent_reply_id, post_id),
                ).fetchone()
                if not parent:
                    raise AppError(404, "被回复的内容不存在")
            conn.execute(
                "INSERT INTO team_post_replies(post_id, parent_reply_id, user_id, content, created_at) VALUES(?,?,?,?,?)",
                (post_id, parent_reply_id, user["id"], content, now_iso()),
            )
            conn.execute("UPDATE team_posts SET updated_at=? WHERE id=?", (now_iso(), post_id))
            write_audit(conn, user, "team_reply.create", "team_post", post_id, "团队讨论新增回复", {"parent_reply_id": parent_reply_id}, self.client_address[0])
        return {"message": "已回复", "posts": self.list_team_posts(user)}

    def toggle_team_post_reaction(self, post_id, user):
        data = read_json(self)
        reaction = str(data.get("reaction") or "+1").strip()
        if not reaction or len(reaction) > 24 or any(ord(char) < 32 for char in reaction):
            raise AppError(400, "回应内容不支持")
        with connect() as conn:
            self.require_team_post_read_access(conn, post_id, user)
            existing = conn.execute(
                "SELECT id FROM team_post_reactions WHERE post_id=? AND user_id=? AND reaction=?",
                (post_id, user["id"], reaction),
            ).fetchone()
            if existing:
                conn.execute("DELETE FROM team_post_reactions WHERE id=?", (existing["id"],))
            else:
                conn.execute(
                    "INSERT INTO team_post_reactions(post_id, user_id, reaction, created_at) VALUES(?,?,?,?)",
                    (post_id, user["id"], reaction, now_iso()),
                )
        return {"message": "已更新回应", "posts": self.list_team_posts(user)}

    def toggle_team_reply_reaction(self, reply_id, user):
        data = read_json(self)
        reaction = str(data.get("reaction") or "+1").strip()
        if not reaction or len(reaction) > 24 or any(ord(char) < 32 for char in reaction):
            raise AppError(400, "回应内容不支持")
        with connect() as conn:
            reply = conn.execute(
                """
                SELECT r.id, r.post_id
                FROM team_post_replies r
                JOIN team_posts p ON p.id = r.post_id
                WHERE r.id=? AND r.deleted_at IS NULL AND p.deleted_at IS NULL
                """,
                (reply_id,),
            ).fetchone()
            if not reply:
                raise AppError(404, "回复不存在")
            self.require_team_post_read_access(conn, reply["post_id"], user)
            existing = conn.execute(
                "SELECT id FROM team_reply_reactions WHERE reply_id=? AND user_id=? AND reaction=?",
                (reply_id, user["id"], reaction),
            ).fetchone()
            if existing:
                conn.execute("DELETE FROM team_reply_reactions WHERE id=?", (existing["id"],))
            else:
                conn.execute(
                    "INSERT INTO team_reply_reactions(reply_id, user_id, reaction, created_at) VALUES(?,?,?,?)",
                    (reply_id, user["id"], reaction, now_iso()),
                )
        return {"message": "已更新回应", "posts": self.list_team_posts(user)}

    def delete_team_post_reply(self, reply_id, user):
        with connect() as conn:
            reply = conn.execute(
                """
                SELECT r.id, r.user_id, r.content, r.deleted_at, r.post_id
                FROM team_post_replies r
                JOIN team_posts p ON p.id=r.post_id
                WHERE r.id=?
                """,
                (reply_id,),
            ).fetchone()
            if not reply:
                raise AppError(404, "回复不存在")
            self.require_team_post_read_access(conn, reply["post_id"], user)
            if reply["user_id"] != user["id"] and user.get("role") != "admin":
                raise AppError(403, "只能删除自己的回复")
            if reply["deleted_at"]:
                raise AppError(400, "回复已经在回收站中")
            descendant_ids = [
                row["id"]
                for row in conn.execute(
                    """
                    WITH RECURSIVE descendants(id) AS (
                        SELECT id FROM team_post_replies WHERE id=?
                        UNION ALL
                        SELECT child.id
                        FROM team_post_replies child
                        JOIN descendants parent ON child.parent_reply_id=parent.id
                    )
                    SELECT id FROM descendants
                    """,
                    (reply_id,),
                ).fetchall()
            ]
            placeholders = ",".join("?" for _ in descendant_ids)
            deleted_at = now_iso()
            conn.execute(
                f"UPDATE team_post_replies SET deleted_at=?, deleted_by=? WHERE id IN ({placeholders})",
                [deleted_at, user["id"], *descendant_ids],
            )
            add_recycle_record(
                conn,
                "team_reply",
                reply_id,
                (reply["content"] or "团队回复")[:60],
                user,
                {"reply_ids": descendant_ids},
            )
            write_audit(
                conn,
                user,
                "team_reply.delete",
                "team_post_reply",
                reply_id,
                "团队对话回复已删除",
                {"deleted_count": len(descendant_ids)},
                self.client_address[0],
            )
        return {"message": "回复已移入回收站", "posts": self.list_team_posts(user)}

    def list_morning_items(self, query):
        item_date = (query.get("date") or [today_iso()])[0] or today_iso()
        try:
            dt.date.fromisoformat(item_date)
        except ValueError:
            raise AppError(400, "日期格式不正确")
        with connect() as conn:
            carried_count = ensure_morning_carryover(conn, item_date)
            actor = getattr(self, "api_user", None)
            target_user_id = (query.get("user_id") or [None])[0]
            org_where, org_params = self.organization_workbench_user_filter(
                conn, "owner", actor, target_user_id
            )
            items = rows_to_list(
                conn.execute(
                    f"""
                    SELECT i.*, owner.display_name AS owner_name, owner.username AS owner_account,
                           owner.morning_sort_order AS owner_sort_order, updater.display_name AS updated_by_name,
                           COALESCE(root.item_date, i.item_date) AS start_date
                    FROM morning_items i
                    JOIN users owner ON owner.id = i.owner_id
                    LEFT JOIN user_types owner_type ON owner_type.key=owner.user_type
                    LEFT JOIN users updater ON updater.id = i.updated_by
                    LEFT JOIN morning_items root ON root.id = COALESCE(i.root_id, i.id)
                    WHERE i.active=1 AND i.item_date=? AND COALESCE(owner_type.include_in_morning, 1)=1 AND {org_where}
                    ORDER BY CASE WHEN owner.morning_sort_order=0 THEN 2147483647 ELSE owner.morning_sort_order END,
                             owner.display_name, CASE i.status WHEN 'risk' THEN 0 WHEN 'doing' THEN 1 WHEN 'todo' THEN 2 ELSE 3 END, i.updated_at DESC
                    """,
                    [item_date, *org_params],
                ).fetchall()
            )
            retained_date = previous_workday(item_date)
            retained_items = rows_to_list(
                conn.execute(
                    f"""
                    SELECT i.*, owner.display_name AS owner_name, owner.username AS owner_account,
                           owner.morning_sort_order AS owner_sort_order, updater.display_name AS updated_by_name,
                           COALESCE(root.item_date, i.item_date) AS start_date
                    FROM morning_items i
                    JOIN users owner ON owner.id = i.owner_id
                    LEFT JOIN user_types owner_type ON owner_type.key=owner.user_type
                    LEFT JOIN users updater ON updater.id = i.updated_by
                    LEFT JOIN morning_items root ON root.id = COALESCE(i.root_id, i.id)
                    WHERE i.active=1
                      AND i.item_date=?
                      AND i.status='done'
                      AND COALESCE(owner_type.include_in_morning, 1)=1
                      AND {org_where}
                      AND NOT EXISTS (
                          SELECT 1
                          FROM morning_items current_item
                          WHERE current_item.active=1
                            AND current_item.item_date=?
                            AND COALESCE(current_item.root_id, current_item.id)=COALESCE(i.root_id, i.id)
                      )
                      AND NOT EXISTS (
                          SELECT 1
                          FROM morning_items same_day_newer
                          WHERE same_day_newer.active=1
                            AND same_day_newer.item_date=i.item_date
                            AND COALESCE(same_day_newer.root_id, same_day_newer.id)=COALESCE(i.root_id, i.id)
                            AND same_day_newer.id>i.id
                      )
                    ORDER BY CASE WHEN owner.morning_sort_order=0 THEN 2147483647 ELSE owner.morning_sort_order END,
                             owner.display_name, i.updated_at DESC
                    """,
                    [retained_date, *org_params, item_date],
                ).fetchall()
            )
            for item in items:
                item["retained_from_previous_workday"] = False
            for item in retained_items:
                item["retained_from_previous_workday"] = True
                item["retained_from_date"] = retained_date
            items.extend(retained_items)
            items.sort(key=lambda item: item.get("updated_at") or "", reverse=True)
            items.sort(
                key=lambda item: (
                    int(item.get("owner_sort_order") or 2147483647),
                    item.get("owner_name") or "",
                    {"risk": 0, "doing": 1, "todo": 2, "done": 3}.get(item.get("status"), 4),
                )
            )
            for item in items:
                start_date = item.get("start_date") or item["item_date"]
                try:
                    item["duration_days"] = (dt.date.fromisoformat(item["item_date"]) - dt.date.fromisoformat(start_date)).days + 1
                except ValueError:
                    item["duration_days"] = 1
            users = rows_to_list(
                conn.execute(
                    f"""
                    SELECT u.id, u.username, u.display_name, u.user_type, u.morning_sort_order,
                           COALESCE(t.name, u.user_type) AS user_type_name
                    FROM users u
                    LEFT JOIN user_types t ON t.key = u.user_type
                    WHERE u.active=1 AND COALESCE(t.include_in_morning, 1)=1 AND {org_where.replace('owner.', 'u.')}
                    ORDER BY CASE WHEN u.morning_sort_order=0 THEN 2147483647 ELSE u.morning_sort_order END,
                             t.sort_order, u.display_name, u.id
                    """,
                    org_params,
                ).fetchall()
            )
            version_token = self._morning_version_token(conn, item_date, org_where, org_params)
        return {
            "date": item_date,
            "today": today_iso(),
            "read_only": is_past_date(item_date),
            "carried_count": carried_count,
            "retained_completed_count": len(retained_items),
            "retained_from_date": retained_date,
            "items": items,
            "users": users,
            "version_token": version_token,
        }

    def _morning_version_token(self, conn, item_date, org_where, org_params):
        retained_date = previous_workday(item_date)
        item_state = conn.execute(
            f"""
            SELECT COUNT(*) AS item_count,
                   COALESCE(MAX(i.updated_at), '') AS latest_update,
                   COALESCE(SUM(i.version), 0) AS version_sum
            FROM morning_items i
            JOIN users owner ON owner.id=i.owner_id
            LEFT JOIN user_types owner_type ON owner_type.key=owner.user_type
            WHERE i.active=1 AND i.item_date IN (?, ?)
              AND COALESCE(owner_type.include_in_morning, 1)=1 AND {org_where}
            """,
            [item_date, retained_date, *org_params],
        ).fetchone()
        user_rows = conn.execute(
            f"""
            SELECT owner.id, owner.morning_sort_order
            FROM users owner
            LEFT JOIN user_types owner_type ON owner_type.key=owner.user_type
            WHERE owner.active=1 AND COALESCE(owner_type.include_in_morning, 1)=1 AND {org_where}
            ORDER BY CASE WHEN owner.morning_sort_order=0 THEN 2147483647 ELSE owner.morning_sort_order END,
                     owner.display_name, owner.id
            """,
            org_params,
        ).fetchall()
        order_state = ",".join(f"{row['id']}:{row['morning_sort_order']}" for row in user_rows)
        return f"{item_state['item_count']}:{item_state['latest_update']}:{item_state['version_sum']}:{order_state}"

    def morning_items_version(self, query):
        item_date = (query.get("date") or [today_iso()])[0] or today_iso()
        try:
            dt.date.fromisoformat(item_date)
        except ValueError:
            raise AppError(400, "日期格式不正确")
        with connect() as conn:
            org_where, org_params = self.organization_current_user_filter(conn, "owner")
            token = self._morning_version_token(conn, item_date, org_where, org_params)
        return {"date": item_date, "version_token": token}

    def update_morning_order(self, user):
        admin = self.require_admin()
        data = read_json(self)
        raw_ids = data.get("user_ids") or []
        if not isinstance(raw_ids, list):
            raise AppError(400, "早例会排序格式不正确")
        try:
            user_ids = [int(user_id) for user_id in raw_ids]
        except (TypeError, ValueError):
            raise AppError(400, "早例会排序包含无效成员")
        if len(user_ids) != len(set(user_ids)):
            raise AppError(400, "早例会排序不能包含重复成员")
        with connect() as conn:
            org_where, org_params = self.organization_current_user_filter(conn, "u", admin)
            eligible_ids = {
                row["id"] for row in conn.execute(
                    f"""
                    SELECT u.id FROM users u
                    LEFT JOIN user_types t ON t.key=u.user_type
                    WHERE u.active=1 AND COALESCE(t.include_in_morning, 1)=1 AND {org_where}
                    """,
                    org_params,
                ).fetchall()
            }
            if set(user_ids) != eligible_ids:
                raise AppError(400, "排序名单与当前团队早例会成员不一致，请刷新后重试")
            for sort_order, user_id in enumerate(user_ids, start=1):
                conn.execute("UPDATE users SET morning_sort_order=? WHERE id=?", (sort_order, user_id))
            write_audit(
                conn, admin, "morning.order", "morning_item", None,
                "早例会成员顺序已更新", {"user_ids": user_ids}, self.client_address[0],
            )
        return {"message": "早例会顺序已更新", **self.list_morning_items({"date": [data.get("date") or today_iso()]})}

    def list_morning_item_history(self, item_id):
        with connect() as conn:
            current = conn.execute(
                """
                SELECT i.*, owner.display_name AS owner_name, owner.username AS owner_account,
                       updater.display_name AS updated_by_name, owner.org_unit_id AS owner_org_unit_id,
                       COALESCE(root.item_date, i.item_date) AS start_date
                FROM morning_items i
                JOIN users owner ON owner.id = i.owner_id
                LEFT JOIN users updater ON updater.id = i.updated_by
                LEFT JOIN morning_items root ON root.id = COALESCE(i.root_id, i.id)
                WHERE i.id=? AND i.active=1
                """,
                (item_id,),
            ).fetchone()
            if not current:
                raise AppError(404, "早例会事项不存在")
            self.require_current_org_unit_access(conn, current["owner_org_unit_id"])
            current_item = dict(current)
            chain_id = current_item.get("root_id") or current_item["id"]
            history = rows_to_list(
                conn.execute(
                    """
                    SELECT i.*, owner.display_name AS owner_name, owner.username AS owner_account,
                           updater.display_name AS updated_by_name,
                           COALESCE(root.item_date, i.item_date) AS start_date
                    FROM morning_items i
                    JOIN users owner ON owner.id = i.owner_id
                    LEFT JOIN users updater ON updater.id = i.updated_by
                    LEFT JOIN morning_items root ON root.id = COALESCE(i.root_id, i.id)
                    WHERE i.active=1 AND COALESCE(i.root_id, i.id)=?
                    ORDER BY i.item_date ASC, i.id ASC
                    """,
                    (chain_id,),
                ).fetchall()
            )
        start_date = current_item.get("start_date") or current_item["item_date"]
        try:
            current_item["duration_days"] = (dt.date.fromisoformat(current_item["item_date"]) - dt.date.fromisoformat(start_date)).days + 1
        except ValueError:
            current_item["duration_days"] = 1

        visible_history = []
        for row in history:
            has_manual_update = not row.get("carry_from_id") or (
                row.get("updated_at") and row.get("created_at") and row["updated_at"] != row["created_at"]
            )
            if not has_manual_update:
                continue
            row_start = row.get("start_date") or row["item_date"]
            try:
                row["duration_days"] = (dt.date.fromisoformat(row["item_date"]) - dt.date.fromisoformat(row_start)).days + 1
            except ValueError:
                row["duration_days"] = 1
            visible_history.append(row)
        return {"item": current_item, "history": visible_history}

    def create_morning_item(self, user):
        data = read_json(self)
        title = (data.get("title") or "").strip()
        if not title:
            raise AppError(400, "事项标题不能为空")
        owner_id = int(data.get("owner_id") or user["id"])
        if user["role"] != "admin" and owner_id != user["id"]:
            raise AppError(403, "只能登记自己的早例会事项")
        status = data.get("status") if data.get("status") in MORNING_STATUSES else "todo"
        priority = data.get("priority") if data.get("priority") in MORNING_PRIORITIES else "normal"
        item_date = data.get("item_date") or today_iso()
        try:
            dt.date.fromisoformat(item_date)
        except ValueError:
            raise AppError(400, "日期格式不正确")
        if is_past_date(item_date):
            raise AppError(400, "已结束日期不能新增早例会事项")
        due_date = data.get("due_date") or item_date
        with connect() as conn:
            org_where, org_params = self.organization_current_user_filter(conn, "u", user)
            owner = conn.execute(
                f"""
                SELECT u.id
                FROM users u
                LEFT JOIN user_types t ON t.key=u.user_type
                WHERE u.id=? AND u.active=1 AND COALESCE(t.include_in_morning, 1)=1 AND {org_where}
                """,
                [owner_id, *org_params],
            ).fetchone()
            if not owner:
                raise AppError(400, "该账号未纳入早例会跟踪名单")
            cursor = conn.execute(
                """
                INSERT INTO morning_items(owner_id, item_date, title, detail, status, priority, blocker, due_date, updated_by, created_at, updated_at, active)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,1)
                """,
                (owner_id, item_date, title, data.get("detail") or "", status, priority, data.get("blocker") or "", due_date, user["id"], now_iso(), now_iso()),
            )
            conn.execute("UPDATE morning_items SET root_id=? WHERE id=?", (cursor.lastrowid, cursor.lastrowid))
            write_audit(conn, user, "morning.create", "morning_item", cursor.lastrowid, "早例会事项已创建", {"owner_id": owner_id, "item_date": item_date}, self.client_address[0])
        return {"message": "早例会事项已创建", **self.list_morning_items({"date": [item_date]})}

    def update_morning_item(self, item_id, user):
        data = read_json(self)
        fields = []
        values = []
        if "title" in data and not (data.get("title") or "").strip():
            raise AppError(400, "事项标题不能为空")
        for date_key in ("item_date", "due_date"):
            if data.get(date_key):
                try:
                    dt.date.fromisoformat(data[date_key])
                except ValueError:
                    raise AppError(400, "日期格式不正确")
                if date_key == "item_date" and is_past_date(data[date_key]):
                    raise AppError(400, "已结束日期不能修改")
        for key in ("title", "detail", "blocker", "due_date", "item_date"):
            if key in data:
                fields.append(f"{key}=?")
                values.append((data.get(key) or "").strip() if key == "title" else data.get(key) or "")
        if "status" in data:
            if data["status"] not in MORNING_STATUSES:
                raise AppError(400, "事项状态不正确")
            fields.append("status=?")
            values.append(data["status"])
        if "priority" in data:
            if data["priority"] not in MORNING_PRIORITIES:
                raise AppError(400, "优先级不正确")
            fields.append("priority=?")
            values.append(data["priority"])
        if "owner_id" in data and user["role"] == "admin":
            fields.append("owner_id=?")
            values.append(int(data["owner_id"]))
        if not fields:
            raise AppError(400, "没有可更新字段")
        expected_version = data.get("expected_version")
        fields.extend(["updated_by=?", "updated_at=?", "version=version+1"])
        values.extend([user["id"], now_iso()])
        with connect() as conn:
            item = conn.execute("SELECT * FROM morning_items WHERE id=? AND active=1", (item_id,)).fetchone()
            if not item:
                raise AppError(404, "早例会事项不存在")
            owner = conn.execute("SELECT org_unit_id FROM users WHERE id=?", (item["owner_id"],)).fetchone()
            self.require_current_org_unit_access(conn, owner["org_unit_id"] if owner else None, user)
            if is_past_date(item["item_date"]):
                raise AppError(400, "已结束日期不能修改")
            if user["role"] != "admin" and item["owner_id"] != user["id"]:
                raise AppError(403, "只能更新自己的早例会事项")
            if "owner_id" in data and user["role"] == "admin":
                org_where, org_params = self.organization_current_user_filter(conn, "u", user)
                eligible_owner = conn.execute(
                    f"""
                    SELECT u.id FROM users u
                    LEFT JOIN user_types t ON t.key=u.user_type
                    WHERE u.id=? AND u.active=1 AND COALESCE(t.include_in_morning, 1)=1 AND {org_where}
                    """,
                    [int(data["owner_id"]), *org_params],
                ).fetchone()
                if not eligible_owner:
                    raise AppError(400, "该账号未纳入早例会跟踪名单")
            if expected_version is not None and int(expected_version) != int(item["version"]):
                raise AppError(409, "该事项已被其他人更新，请刷新后查看最新进展再修改")
            updated = conn.execute(
                f"UPDATE morning_items SET {', '.join(fields)} WHERE id=? AND version=?",
                [*values, item_id, item["version"]],
            )
            if updated.rowcount != 1:
                raise AppError(409, "该事项已被其他人更新，请刷新后重试")
            write_audit(conn, user, "morning.update", "morning_item", item_id, "早例会事项已更新", {"fields": list(data.keys())}, self.client_address[0])
            date_row = conn.execute("SELECT item_date FROM morning_items WHERE id=?", (item_id,)).fetchone()
        return {"message": "早例会事项已更新", **self.list_morning_items({"date": [date_row["item_date"]]})}

    def delete_morning_item(self, item_id, user):
        data = read_json(self)
        expected_version = data.get("expected_version")
        with connect() as conn:
            item = conn.execute("SELECT * FROM morning_items WHERE id=? AND active=1", (item_id,)).fetchone()
            if not item:
                raise AppError(404, "早例会事项不存在")
            owner = conn.execute("SELECT org_unit_id FROM users WHERE id=?", (item["owner_id"],)).fetchone()
            self.require_current_org_unit_access(conn, owner["org_unit_id"] if owner else None, user)
            if is_past_date(item["item_date"]):
                raise AppError(400, "已结束日期不能删除")
            if user["role"] != "admin" and item["owner_id"] != user["id"]:
                raise AppError(403, "只能删除自己的早例会事项")
            if expected_version is not None and int(expected_version) != int(item["version"]):
                raise AppError(409, "该事项已被其他人更新，请刷新后确认后再删除")
            chain_id = item["root_id"] or item["id"]
            updated_at = now_iso()
            cursor = conn.execute(
                """
                UPDATE morning_items
                SET active=0, updated_by=?, updated_at=?, version=version+1
                WHERE active=1
                  AND item_date>=?
                  AND COALESCE(root_id, id)=?
                """,
                (user["id"], updated_at, item["item_date"], chain_id),
            )
            write_audit(
                conn,
                user,
                "morning.delete",
                "morning_item",
                item_id,
                "早例会事项已删除",
                {"item_date": item["item_date"], "chain_id": chain_id, "affected": cursor.rowcount},
                self.client_address[0],
            )
        return {"message": "早例会事项已删除", **self.list_morning_items({"date": [item["item_date"]]})}

    def normalize_process_template_items(self, raw_items):
        if not isinstance(raw_items, list) or not raw_items:
            raise AppError(400, "流程模板至少需要一个 Checklist")
        if len(raw_items) > 60:
            raise AppError(400, "单个流程模板最多包含 60 个 Checklist")
        items = []
        seen_keys = set()
        required_by_key = {}
        for index, raw in enumerate(raw_items):
            if not isinstance(raw, dict):
                raise AppError(400, "Checklist 格式不正确")
            title = str(raw.get("title") or "").strip()
            if not title:
                raise AppError(400, f"第 {index + 1} 个 Checklist 标题不能为空")
            if len(title) > 120:
                raise AppError(400, f"第 {index + 1} 个 Checklist 标题不能超过 120 字")
            description = str(raw.get("description") or "").strip()
            if len(description) > 500:
                raise AppError(400, f"第 {index + 1} 个 Checklist 说明不能超过 500 字")
            item_key = str(raw.get("key") or f"step-{index + 1}").strip()
            if not item_key or len(item_key) > 64:
                raise AppError(400, f"第 {index + 1} 个 Checklist 标识不正确")
            if item_key in seen_keys:
                raise AppError(400, "Checklist 标识不能重复")
            parent_key = str(raw.get("parent_key") or "").strip() or None
            if parent_key and parent_key not in seen_keys:
                raise AppError(400, f"第 {index + 1} 个 Checklist 的上一步必须位于它之前")
            required = 0 if raw.get("required") is False else 1
            if required and parent_key and not required_by_key.get(parent_key):
                raise AppError(400, "必做步骤不能依赖可选步骤")
            items.append({
                "key": item_key,
                "parent_key": parent_key,
                "title": title,
                "description": description,
                "required": required,
                "sort_order": index + 1,
            })
            seen_keys.add(item_key)
            required_by_key[item_key] = required
        if not any(item["required"] for item in items):
            raise AppError(400, "流程模板至少需要一个必做 Checklist")
        return items

    def replace_process_template_items(self, conn, template_id, items):
        conn.execute("DELETE FROM process_template_items WHERE template_id=?", (template_id,))
        inserted_ids = {}
        for item in items:
            parent_item_id = inserted_ids.get(item["parent_key"]) if item["parent_key"] else None
            cursor = conn.execute(
                """
                INSERT INTO process_template_items(
                    template_id, parent_item_id, title, description, required, sort_order
                ) VALUES(?,?,?,?,?,?)
                """,
                (
                    template_id,
                    parent_item_id,
                    item["title"],
                    item["description"],
                    item["required"],
                    item["sort_order"],
                ),
            )
            inserted_ids[item["key"]] = cursor.lastrowid

    def list_process_templates(self, user):
        if not user:
            raise AppError(401, "请先登录后使用流程中心")
        with connect() as conn:
            context = self.organization_context(conn, user)
            org_where, org_params = self.organization_entity_filter(
                conn,
                "t.org_unit_id",
                user,
                inherit_ancestors=True,
            )
            templates = rows_to_list(
                conn.execute(
                    f"""
                    SELECT t.*, o.name AS org_unit_name, creator.display_name AS created_by_name,
                           (SELECT COUNT(*) FROM process_instances p WHERE p.template_id=t.id AND p.active=1) AS instance_count
                    FROM process_templates t
                    JOIN org_units o ON o.id=t.org_unit_id
                    JOIN users creator ON creator.id=t.created_by
                    WHERE t.active=1 AND {org_where}
                    ORDER BY CASE WHEN t.org_unit_id=? THEN 0 ELSE 1 END, t.updated_at DESC, t.id DESC
                    """,
                    [*org_params, context["selected"]["id"]],
                ).fetchall()
            )
            template_ids = [template["id"] for template in templates]
            item_map = {}
            if template_ids:
                placeholders = ",".join("?" for _ in template_ids)
                template_items = rows_to_list(
                    conn.execute(
                        f"""
                        SELECT *
                        FROM process_template_items
                        WHERE template_id IN ({placeholders})
                        ORDER BY template_id, sort_order, id
                        """,
                        template_ids,
                    ).fetchall()
                )
                for item in template_items:
                    item["required"] = bool(item["required"])
                    item_map.setdefault(item["template_id"], []).append(item)
        visible_ids = set(context["visible_ids"])
        for template in templates:
            template["items"] = item_map.get(template["id"], [])
            template["inherited"] = template["org_unit_id"] not in visible_ids
            template["can_manage"] = bool(
                template["org_unit_id"] == context["selected"]["id"]
                and (user["role"] == "admin" or template["created_by"] == user["id"])
            )
        return templates

    def create_process_template(self, user):
        data = read_json(self)
        name = str(data.get("name") or "").strip()
        description = str(data.get("description") or "").strip()
        if not name:
            raise AppError(400, "流程模板名称不能为空")
        if len(name) > 80:
            raise AppError(400, "流程模板名称不能超过 80 字")
        if len(description) > 1000:
            raise AppError(400, "流程模板说明不能超过 1000 字")
        items = self.normalize_process_template_items(data.get("items"))
        with connect() as conn:
            context = self.organization_context(conn, user)
            org_unit_id = context["selected"]["id"] if context.get("selected") else user.get("org_unit_id")
            self.require_org_unit_access(conn, org_unit_id, user)
            duplicate = conn.execute(
                "SELECT id FROM process_templates WHERE org_unit_id=? AND active=1 AND LOWER(name)=LOWER(?)",
                (org_unit_id, name),
            ).fetchone()
            if duplicate:
                raise AppError(400, "当前团队已存在同名流程模板")
            created_at = now_iso()
            cursor = conn.execute(
                """
                INSERT INTO process_templates(org_unit_id, name, description, active, version, created_by, created_at, updated_at)
                VALUES(?,?,?,?,?,?,?,?)
                """,
                (org_unit_id, name, description, 1, 1, user["id"], created_at, created_at),
            )
            template_id = cursor.lastrowid
            self.replace_process_template_items(conn, template_id, items)
            write_audit(
                conn,
                user,
                "process_template.create",
                "process_template",
                template_id,
                "流程模板已创建",
                {"name": name, "checklist_count": len(items), "org_unit_id": org_unit_id},
                self.client_address[0],
            )
        return {"message": "流程模板已创建", "templates": self.list_process_templates(user)}

    def update_process_template(self, template_id, user):
        data = read_json(self)
        with connect() as conn:
            template = conn.execute(
                "SELECT * FROM process_templates WHERE id=? AND active=1",
                (template_id,),
            ).fetchone()
            if not template:
                raise AppError(404, "流程模板不存在")
            self.require_current_org_unit_access(conn, template["org_unit_id"], user)
            if user["role"] != "admin" and template["created_by"] != user["id"]:
                raise AppError(403, "只能修改自己创建的流程模板")
            expected_version = data.get("expected_version")
            if expected_version is not None and int(expected_version) != int(template["version"]):
                raise AppError(409, "流程模板已被其他人修改，请刷新后重试")
            name = str(data.get("name", template["name"]) or "").strip()
            description = str(data.get("description", template["description"]) or "").strip()
            if not name:
                raise AppError(400, "流程模板名称不能为空")
            if len(name) > 80 or len(description) > 1000:
                raise AppError(400, "流程模板名称或说明过长")
            items = None
            if "items" in data:
                items = self.normalize_process_template_items(data.get("items"))
            duplicate = conn.execute(
                """
                SELECT id FROM process_templates
                WHERE org_unit_id=? AND active=1 AND LOWER(name)=LOWER(?) AND id<>?
                """,
                (template["org_unit_id"], name, template_id),
            ).fetchone()
            if duplicate:
                raise AppError(400, "当前团队已存在同名流程模板")
            updated = conn.execute(
                """
                UPDATE process_templates
                SET name=?, description=?, updated_at=?, version=version+1
                WHERE id=? AND version=?
                """,
                (name, description, now_iso(), template_id, template["version"]),
            )
            if updated.rowcount != 1:
                raise AppError(409, "流程模板已被其他人修改，请刷新后重试")
            if items is not None:
                self.replace_process_template_items(conn, template_id, items)
            write_audit(
                conn,
                user,
                "process_template.update",
                "process_template",
                template_id,
                "流程模板已更新",
                {"name": name, "checklist_count": len(items) if items is not None else None},
                self.client_address[0],
            )
        return {"message": "流程模板已更新", "templates": self.list_process_templates(user)}

    def delete_process_template(self, template_id, user):
        with connect() as conn:
            template = conn.execute(
                "SELECT * FROM process_templates WHERE id=? AND active=1",
                (template_id,),
            ).fetchone()
            if not template:
                raise AppError(404, "流程模板不存在")
            self.require_current_org_unit_access(conn, template["org_unit_id"], user)
            if user["role"] != "admin" and template["created_by"] != user["id"]:
                raise AppError(403, "只能停用自己创建的流程模板")
            instance_count = conn.execute(
                "SELECT COUNT(*) FROM process_instances WHERE template_id=?",
                (template_id,),
            ).fetchone()[0]
            conn.execute(
                "UPDATE process_templates SET active=0, updated_at=?, version=version+1 WHERE id=?",
                (now_iso(), template_id),
            )
            write_audit(
                conn,
                user,
                "process_template.delete",
                "process_template",
                template_id,
                "流程模板已停用",
                {"name": template["name"], "historical_instances": instance_count},
                self.client_address[0],
            )
        return {
            "message": "流程模板已停用，已生成的个人流程不受影响",
            "templates": self.list_process_templates(user),
        }

    def list_process_instances(self, user, query):
        if not user:
            raise AppError(401, "请先登录后使用流程中心")
        status = str((query.get("status") or ["active"])[0] or "active")
        if status not in {"active", "completed", "all"}:
            status = "active"
        scope = str((query.get("scope") or ["mine"])[0] or "mine")
        if user["role"] != "admin":
            scope = "mine"
        with connect() as conn:
            org_where, org_params = self.organization_entity_filter(conn, "p.org_unit_id", user)
            clauses = ["p.active=1", org_where]
            params = list(org_params)
            if scope == "mine":
                clauses.append("p.owner_id=?")
                params.append(user["id"])
            if status != "all":
                clauses.append("p.status=?")
                params.append(status)
            instances = rows_to_list(
                conn.execute(
                    f"""
                    SELECT p.*, t.name AS template_name, owner.display_name AS owner_name,
                           creator.display_name AS created_by_name, o.name AS org_unit_name,
                           COUNT(i.id) AS checklist_total,
                           SUM(CASE WHEN i.completed=1 THEN 1 ELSE 0 END) AS checklist_completed,
                           SUM(CASE WHEN i.required=1 THEN 1 ELSE 0 END) AS required_total,
                           SUM(CASE WHEN i.required=1 AND i.completed=1 THEN 1 ELSE 0 END) AS required_completed
                    FROM process_instances p
                    LEFT JOIN process_templates t ON t.id=p.template_id
                    JOIN users owner ON owner.id=p.owner_id
                    JOIN users creator ON creator.id=p.created_by
                    JOIN org_units o ON o.id=p.org_unit_id
                    LEFT JOIN process_instance_items i ON i.instance_id=p.id
                    WHERE {' AND '.join(clauses)}
                    GROUP BY p.id
                    ORDER BY CASE p.status WHEN 'active' THEN 0 WHEN 'completed' THEN 1 ELSE 2 END,
                             CASE WHEN p.due_date IS NULL OR p.due_date='' THEN 1 ELSE 0 END,
                             p.due_date, p.updated_at DESC, p.id DESC
                    """,
                    params,
                ).fetchall()
            )
            instance_ids = [instance["id"] for instance in instances]
            item_map = {}
            if instance_ids:
                placeholders = ",".join("?" for _ in instance_ids)
                items = rows_to_list(
                    conn.execute(
                        f"""
                        SELECT i.*, completer.display_name AS completed_by_name
                        FROM process_instance_items i
                        LEFT JOIN users completer ON completer.id=i.completed_by
                        WHERE i.instance_id IN ({placeholders})
                        ORDER BY i.instance_id, i.sort_order, i.id
                        """,
                        instance_ids,
                    ).fetchall()
                )
                for item in items:
                    item["required"] = bool(item["required"])
                    item["completed"] = bool(item["completed"])
                    item_map.setdefault(item["instance_id"], []).append(item)
        for instance in instances:
            instance["checklist_total"] = int(instance.get("checklist_total") or 0)
            instance["checklist_completed"] = int(instance.get("checklist_completed") or 0)
            instance["required_total"] = int(instance.get("required_total") or 0)
            instance["required_completed"] = int(instance.get("required_completed") or 0)
            instance["progress"] = round(
                (instance["required_completed"] / instance["required_total"]) * 100
            ) if instance["required_total"] else 0
            instance["items"] = item_map.get(instance["id"], [])
            instance["overdue"] = bool(
                instance["status"] == "active"
                and instance.get("due_date")
                and instance["due_date"] < today_iso()
            )
            instance["can_edit"] = user["role"] == "admin" or instance["owner_id"] == user["id"]
        return instances

    def create_process_instance(self, user):
        data = read_json(self)
        try:
            template_id = int(data.get("template_id"))
        except (TypeError, ValueError):
            raise AppError(400, "请选择流程模板")
        due_date = str(data.get("due_date") or "").strip()
        if due_date:
            try:
                dt.date.fromisoformat(due_date)
            except ValueError:
                raise AppError(400, "截止日期格式不正确")
        with connect() as conn:
            template = conn.execute(
                "SELECT * FROM process_templates WHERE id=? AND active=1",
                (template_id,),
            ).fetchone()
            if not template:
                raise AppError(404, "流程模板不存在或已停用")
            context = self.organization_context(conn, user)
            allowed_template_orgs = set(context["visible_ids"]) | set(context["ancestor_ids"])
            if template["org_unit_id"] not in allowed_template_orgs:
                raise AppError(404, "流程模板不存在或无权访问")
            items = rows_to_list(
                conn.execute(
                    """
                    SELECT * FROM process_template_items
                    WHERE template_id=?
                    ORDER BY sort_order, id
                    """,
                    (template_id,),
                ).fetchall()
            )
            if not items:
                raise AppError(400, "该流程模板没有可执行的 Checklist")
            title = str(data.get("title") or template["name"]).strip()
            if not title:
                title = template["name"]
            if len(title) > 120:
                raise AppError(400, "个人流程名称不能超过 120 字")
            created_at = now_iso()
            cursor = conn.execute(
                """
                INSERT INTO process_instances(
                    template_id, org_unit_id, owner_id, title, status, due_date,
                    started_at, active, version, created_by, created_at, updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    template_id,
                    user["org_unit_id"],
                    user["id"],
                    title,
                    "active",
                    due_date or None,
                    created_at,
                    1,
                    1,
                    user["id"],
                    created_at,
                    created_at,
                ),
            )
            instance_id = cursor.lastrowid
            snapshot_ids = {}
            for item in items:
                parent_item_id = snapshot_ids.get(item["parent_item_id"]) if item["parent_item_id"] else None
                item_cursor = conn.execute(
                    """
                    INSERT INTO process_instance_items(
                        instance_id, template_item_id, parent_item_id, title, description,
                        required, sort_order, completed, version
                    ) VALUES(?,?,?,?,?,?,?,0,1)
                    """,
                    (
                        instance_id,
                        item["id"],
                        parent_item_id,
                        item["title"],
                        item["description"],
                        item["required"],
                        item["sort_order"],
                    ),
                )
                snapshot_ids[item["id"]] = item_cursor.lastrowid
            write_audit(
                conn,
                user,
                "process_instance.create",
                "process_instance",
                instance_id,
                "个人流程已创建",
                {"template_id": template_id, "title": title, "checklist_count": len(items)},
                self.client_address[0],
            )
        return {
            "message": "已根据模板生成个人流程",
            "instances": self.list_process_instances(user, {"scope": ["mine"], "status": ["active"]}),
        }

    def require_process_instance_access(self, conn, instance_id, user):
        instance = conn.execute(
            "SELECT * FROM process_instances WHERE id=? AND active=1",
            (instance_id,),
        ).fetchone()
        if not instance:
            raise AppError(404, "个人流程不存在")
        if user["role"] == "admin":
            self.require_org_unit_access(conn, instance["org_unit_id"], user)
        elif instance["owner_id"] != user["id"]:
            raise AppError(404, "个人流程不存在或无权访问")
        return instance

    def update_process_instance(self, instance_id, user):
        data = read_json(self)
        fields = []
        values = []
        if "title" in data:
            title = str(data.get("title") or "").strip()
            if not title:
                raise AppError(400, "个人流程名称不能为空")
            if len(title) > 120:
                raise AppError(400, "个人流程名称不能超过 120 字")
            fields.append("title=?")
            values.append(title)
        if "due_date" in data:
            due_date = str(data.get("due_date") or "").strip()
            if due_date:
                try:
                    dt.date.fromisoformat(due_date)
                except ValueError:
                    raise AppError(400, "截止日期格式不正确")
            fields.append("due_date=?")
            values.append(due_date or None)
        if not fields:
            raise AppError(400, "没有可更新字段")
        with connect() as conn:
            instance = self.require_process_instance_access(conn, instance_id, user)
            expected_version = data.get("expected_version")
            if expected_version is not None and int(expected_version) != int(instance["version"]):
                raise AppError(409, "个人流程已被更新，请刷新后重试")
            fields.extend(["updated_at=?", "version=version+1"])
            values.append(now_iso())
            updated = conn.execute(
                f"UPDATE process_instances SET {', '.join(fields)} WHERE id=? AND version=?",
                [*values, instance_id, instance["version"]],
            )
            if updated.rowcount != 1:
                raise AppError(409, "个人流程已被更新，请刷新后重试")
            write_audit(
                conn,
                user,
                "process_instance.update",
                "process_instance",
                instance_id,
                "个人流程已更新",
                {"fields": [key for key in ("title", "due_date") if key in data]},
                self.client_address[0],
            )
        return {"message": "个人流程已更新"}

    def delete_process_instance(self, instance_id, user):
        with connect() as conn:
            instance = self.require_process_instance_access(conn, instance_id, user)
            conn.execute(
                """
                UPDATE process_instances
                SET active=0, status='cancelled', updated_at=?, version=version+1
                WHERE id=?
                """,
                (now_iso(), instance_id),
            )
            write_audit(
                conn,
                user,
                "process_instance.delete",
                "process_instance",
                instance_id,
                "个人流程已取消",
                {"title": instance["title"]},
                self.client_address[0],
            )
        return {"message": "个人流程已取消"}

    def update_process_instance_item(self, item_id, user):
        data = read_json(self)
        if "completed" not in data:
            raise AppError(400, "请指定 Checklist 完成状态")
        completed = bool(data.get("completed"))
        with connect() as conn:
            item = conn.execute(
                """
                SELECT i.*, p.owner_id, p.org_unit_id, p.status AS instance_status,
                       p.active AS instance_active
                FROM process_instance_items i
                JOIN process_instances p ON p.id=i.instance_id
                WHERE i.id=?
                """,
                (item_id,),
            ).fetchone()
            if not item or not item["instance_active"]:
                raise AppError(404, "Checklist 不存在")
            if user["role"] == "admin":
                self.require_org_unit_access(conn, item["org_unit_id"], user)
            elif item["owner_id"] != user["id"]:
                raise AppError(404, "Checklist 不存在或无权操作")
            expected_version = data.get("expected_version")
            if expected_version is not None and int(expected_version) != int(item["version"]):
                raise AppError(409, "Checklist 已被更新，请刷新后重试")
            if completed and item["parent_item_id"]:
                parent = conn.execute(
                    """
                    SELECT completed
                    FROM process_instance_items
                    WHERE id=? AND instance_id=?
                    """,
                    (item["parent_item_id"], item["instance_id"]),
                ).fetchone()
                if not parent or not parent["completed"]:
                    raise AppError(409, "请先完成该步骤的上一步")
            updated = conn.execute(
                """
                UPDATE process_instance_items
                SET completed=?, completed_at=?, completed_by=?, version=version+1
                WHERE id=? AND version=?
                """,
                (
                    1 if completed else 0,
                    now_iso() if completed else None,
                    user["id"] if completed else None,
                    item_id,
                    item["version"],
                ),
            )
            if updated.rowcount != 1:
                raise AppError(409, "Checklist 已被更新，请刷新后重试")
            reset_descendants = 0
            if not completed:
                descendants = conn.execute(
                    """
                    WITH RECURSIVE descendants(id) AS (
                        SELECT id
                        FROM process_instance_items
                        WHERE parent_item_id=? AND instance_id=?
                        UNION ALL
                        SELECT child.id
                        FROM process_instance_items child
                        JOIN descendants parent ON child.parent_item_id=parent.id
                        WHERE child.instance_id=?
                    )
                    SELECT id FROM descendants
                    """,
                    (item_id, item["instance_id"], item["instance_id"]),
                ).fetchall()
                descendant_ids = [row["id"] for row in descendants]
                if descendant_ids:
                    placeholders = ",".join("?" for _ in descendant_ids)
                    reset = conn.execute(
                        f"""
                        UPDATE process_instance_items
                        SET completed=0, completed_at=NULL, completed_by=NULL, version=version+1
                        WHERE id IN ({placeholders}) AND completed=1
                        """,
                        descendant_ids,
                    )
                    reset_descendants = reset.rowcount
            totals = conn.execute(
                """
                SELECT SUM(CASE WHEN required=1 THEN 1 ELSE 0 END) AS required_total,
                       SUM(CASE WHEN required=1 AND completed=1 THEN 1 ELSE 0 END) AS required_completed
                FROM process_instance_items
                WHERE instance_id=?
                """,
                (item["instance_id"],),
            ).fetchone()
            all_completed = bool(
                totals["required_total"]
                and totals["required_total"] == (totals["required_completed"] or 0)
            )
            new_status = "completed" if all_completed else "active"
            conn.execute(
                """
                UPDATE process_instances
                SET status=?, completed_at=?, updated_at=?, version=version+1
                WHERE id=?
                """,
                (
                    new_status,
                    now_iso() if all_completed else None,
                    now_iso(),
                    item["instance_id"],
                ),
            )
            write_audit(
                conn,
                user,
                "process_checklist.update",
                "process_instance_item",
                item_id,
                "流程 Checklist 已更新",
                {
                    "instance_id": item["instance_id"],
                    "completed": completed,
                    "instance_status": new_status,
                    "reset_descendants": reset_descendants,
                },
                self.client_address[0],
            )
        return {
            "message": (
                "Checklist 已完成"
                if completed
                else (
                    f"Checklist 已恢复，并同步撤销 {reset_descendants} 个下游步骤"
                    if reset_descendants
                    else "Checklist 已恢复为未完成"
                )
            ),
            "instance_status": new_status,
            "reset_descendants": reset_descendants,
        }


