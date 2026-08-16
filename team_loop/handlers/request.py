from ..permissions import *


class RequestHandlerMixin:
    def do_GET(self):
        self.handle_request("GET")

    def do_POST(self):
        self.handle_request("POST")

    def do_PATCH(self):
        self.handle_request("PATCH")

    def do_DELETE(self):
        self.handle_request("DELETE")

    def log_message(self, fmt, *args):
        print("%s - %s" % (self.address_string(), fmt % args))

    def apply_forwarded_request_context(self):
        self.forwarded_https = False
        peer_ip = getattr(self, "_direct_peer_ip", self.client_address[0])
        self._direct_peer_ip = peer_ip
        self.client_address = (peer_ip, self.client_address[1])
        if not TRUST_PROXY or peer_ip not in {"127.0.0.1", "::1"}:
            return
        forwarded_proto = (self.headers.get("X-Forwarded-Proto") or "").split(",", 1)[0].strip().lower()
        self.forwarded_https = forwarded_proto == "https"
        forwarded_for = (self.headers.get("X-Forwarded-For") or "").split(",", 1)[0].strip()
        try:
            normalized_ip = str(ipaddress.ip_address(forwarded_for))
        except ValueError:
            return
        self.client_address = (normalized_ip, self.client_address[1])

    def request_is_https(self):
        return bool(getattr(self, "forwarded_https", False))

    def require_https_transport(self, purpose="该操作"):
        if REQUIRE_HTTPS and not self.request_is_https():
            raise AppError(426, f"{purpose}只允许通过 HTTPS 访问，请使用正式 HTTPS 域名")

    def handle_request(self, method):
        self.apply_forwarded_request_context()
        parsed = urlparse(self.path)
        try:
            if parsed.path.startswith("/api/") and method in {"POST", "PATCH", "DELETE"}:
                self.require_https_transport("登录和数据写入")
            if parsed.path.startswith("/api/") and DEPLOY_ENV != "gray":
                ensure_daily_backup()
            if parsed.path in ("/api/sso/login", "/api/sso/callback") and method == "GET":
                sso_query = parse_qs(parsed.query)
                return_to = self.sso_return_target(parsed.path, sso_query)
                try:
                    self.require_https_transport("企业 SSO 登录")
                    if parsed.path == "/api/sso/login":
                        self.start_sso_login(sso_query)
                    else:
                        self.complete_sso_login(sso_query)
                except AppError as exc:
                    self.send_redirect(append_sso_notice(return_to, "sso_error", exc.message))
                except Exception:
                    traceback.print_exc()
                    message = "企业 SSO 登录处理失败，请联系管理员查看服务日志"
                    self.send_redirect(append_sso_notice(return_to, "sso_error", message))
                return
            if parsed.path == "/api/backups/download" and method == "GET":
                self.send_backup_file(parse_qs(parsed.query))
                return
            link_open = parsed.path.strip("/").split("/")
            if len(link_open) == 4 and link_open[:2] == ["api", "links"] and link_open[3] == "open" and method == "GET":
                self.send_link_redirect(int(link_open[2]))
                return
            moment_image = parsed.path.strip("/").split("/")
            if len(moment_image) == 3 and moment_image[:2] == ["api", "team-moment-images"] and method == "GET":
                self.send_team_moment_image(int(moment_image[2]))
                return
            if parsed.path.startswith("/api/"):
                result = self.route_api(method, parsed.path, parse_qs(parsed.query))
                self.send_json(result)
            else:
                self.serve_static(parsed.path)
        except AppError as exc:
            self.send_json({"error": exc.message}, exc.status)
        except json.JSONDecodeError:
            self.send_json({"error": "请求体不是合法 JSON"}, 400)
        except Exception as exc:
            self.send_json({"error": str(exc)}, 500)

    def serve_static(self, path):
        if path in ("", "/") or path.startswith("/org/"):
            file_path = STATIC_DIR / "index.html"
        else:
            safe = Path(path.lstrip("/"))
            file_path = (STATIC_DIR / safe).resolve()
            if STATIC_DIR.resolve() not in file_path.parents and file_path != STATIC_DIR.resolve():
                raise AppError(403, "禁止访问该路径")
        if not file_path.exists() or not file_path.is_file():
            raise AppError(404, "文件不存在")
        mime = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
        content = file_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        self.send_header("Connection", "close")
        self.close_connection = True
        self.end_headers()
        # Large JavaScript bundles can be truncated by the Windows socket stack
        # when they are written in one send while the browser loads assets in
        # parallel. Small fixed-size writes keep the response length reliable.
        for offset in range(0, len(content), 64 * 1024):
            self.wfile.write(content[offset:offset + 64 * 1024])
        self.wfile.flush()

    def organization_context(self, conn, user=None):
        units = organization_rows(conn)
        if not units:
            return {
                "selected": None,
                "accessible": [],
                "visible_ids": [],
                "ancestor_ids": [],
                "inherited_ids": [],
                "collaboration_ids": [],
            }
        by_id = {unit["id"]: unit for unit in units}
        by_path = {unit["path"].lower(): unit for unit in units}
        root = next((unit for unit in units if not unit.get("parent_id")), units[0])

        def descendants(unit_id):
            result = {unit_id}
            changed = True
            while changed:
                changed = False
                for unit in units:
                    if unit.get("parent_id") in result and unit["id"] not in result:
                        result.add(unit["id"])
                        changed = True
            return result

        def ancestors(unit_id):
            result = []
            seen = set()
            current = by_id.get(unit_id)
            while current and current["id"] not in seen:
                result.append(current["id"])
                seen.add(current["id"])
                current = by_id.get(current.get("parent_id"))
            return result

        user_unit = by_id.get((user or {}).get("org_unit_id")) or root
        if user and user.get("role") == "admin":
            accessible_ids = {unit["id"] for unit in units}
        elif user_unit["visibility_mode"] == "all":
            accessible_ids = {unit["id"] for unit in units}
        elif user_unit["visibility_mode"] == "subtree":
            accessible_ids = descendants(user_unit["id"])
        else:
            accessible_ids = {user_unit["id"]}

        requested = (self.headers.get("X-Team-Org-Path") or "").strip().strip("/").lower()
        if requested.startswith("org/"):
            requested = requested[4:]
        selected = by_path.get(requested) if requested else user_unit
        if not selected or selected["id"] not in accessible_ids:
            selected = user_unit

        if selected["visibility_mode"] == "all":
            visible_ids = {unit["id"] for unit in units}
        elif selected["visibility_mode"] == "subtree":
            visible_ids = descendants(selected["id"])
        else:
            visible_ids = {selected["id"]}
        visible_ids &= accessible_ids
        ancestor_ids = ancestors(selected["id"])
        collaboration_root_id = ancestor_ids[-1] if ancestor_ids else selected["id"]
        collaboration_ids = descendants(collaboration_root_id)
        accessible = [unit for unit in units if unit["id"] in accessible_ids]
        return {
            "selected": selected,
            "accessible": accessible,
            "visible_ids": sorted(visible_ids),
            "ancestor_ids": ancestor_ids,
            "inherited_ids": [unit_id for unit_id in ancestor_ids if unit_id not in visible_ids],
            "collaboration_ids": sorted(collaboration_ids),
        }

    def organization_user_filter(self, conn, user_alias="u", user=None):
        context = self.organization_context(conn, user if user is not None else getattr(self, "api_user", None))
        visible_ids = context["visible_ids"]
        if not visible_ids:
            return "1=0", []
        placeholders = ",".join("?" for _ in visible_ids)
        return f"{user_alias}.org_unit_id IN ({placeholders})", visible_ids

    def organization_current_user_filter(self, conn, user_alias="u", user=None):
        """Limit people-centric modules to direct members of the selected unit."""
        context = self.organization_context(conn, user if user is not None else getattr(self, "api_user", None))
        selected = context.get("selected") or {}
        selected_id = selected.get("id")
        if not selected_id:
            return "1=0", []
        return f"{user_alias}.org_unit_id=?", [selected_id]

    def organization_entity_filter(self, conn, column, user=None, inherit_ancestors=False):
        context = self.organization_context(conn, user if user is not None else getattr(self, "api_user", None))
        visible_ids = set(context["visible_ids"])
        if inherit_ancestors:
            visible_ids.update(context["ancestor_ids"])
        visible_ids = sorted(visible_ids)
        if not visible_ids:
            return "1=0", []
        placeholders = ",".join("?" for _ in visible_ids)
        return f"{column} IN ({placeholders})", visible_ids

    def organization_collaboration_user_filter(self, conn, user_alias="u", user=None):
        context = self.organization_context(conn, user if user is not None else getattr(self, "api_user", None))
        collaboration_ids = context["collaboration_ids"]
        if not collaboration_ids:
            return "1=0", []
        placeholders = ",".join("?" for _ in collaboration_ids)
        return f"{user_alias}.org_unit_id IN ({placeholders})", collaboration_ids

    def require_org_unit_access(self, conn, org_unit_id, user=None):
        context = self.organization_context(conn, user if user is not None else getattr(self, "api_user", None))
        if org_unit_id not in context["visible_ids"]:
            raise AppError(404, "记录不存在或无权访问")
        return context

    def require_current_org_unit_access(self, conn, org_unit_id, user=None):
        context = self.organization_context(conn, user if user is not None else getattr(self, "api_user", None))
        selected_id = (context.get("selected") or {}).get("id")
        if not selected_id or org_unit_id != selected_id:
            raise AppError(404, "当前团队下未找到该成员内容")
        return context

    def require_team_post_read_access(self, conn, post_id, user=None):
        post = conn.execute(
            "SELECT id, org_unit_id, category FROM team_posts WHERE id=? AND deleted_at IS NULL",
            (post_id,),
        ).fetchone()
        if not post:
            raise AppError(404, "讨论主题不存在")
        context = self.organization_context(conn, user if user is not None else getattr(self, "api_user", None))
        direct = post["org_unit_id"] in context["visible_ids"]
        inherited_announcement = post["category"] == "announcement" and post["org_unit_id"] in context["ancestor_ids"]
        if not direct and not inherited_announcement:
            raise AppError(404, "讨论主题不存在或无权访问")
        return post

    def require_team_moment_access(self, conn, moment_id, user=None, write=False):
        moment = conn.execute(
            "SELECT id, org_unit_id, title FROM team_moments WHERE id=? AND deleted_at IS NULL",
            (moment_id,),
        ).fetchone()
        if not moment:
            raise AppError(404, "团队时刻不存在")
        context = self.organization_context(conn, user if user is not None else getattr(self, "api_user", None))
        allowed_ids = set(context["visible_ids"])
        if not write:
            allowed_ids.update(context["ancestor_ids"])
        if moment["org_unit_id"] not in allowed_ids:
            raise AppError(404, "团队时刻不存在或无权访问")
        return moment

    def require_meeting_access(self, conn, meeting_id, user=None):
        meeting = conn.execute("SELECT id, org_unit_id FROM meetings WHERE id=?", (meeting_id,)).fetchone()
        if not meeting:
            raise AppError(404, "Meeting not found")
        self.require_org_unit_access(conn, meeting["org_unit_id"], user)
        return meeting

    def require_meeting_item_access(self, conn, item_id, user=None):
        item = conn.execute(
            """
            SELECT i.id, i.meeting_id, m.org_unit_id
            FROM meeting_items i
            JOIN meetings m ON m.id=i.meeting_id
            WHERE i.id=?
            """,
            (item_id,),
        ).fetchone()
        if not item:
            raise AppError(404, "Agenda item not found")
        self.require_org_unit_access(conn, item["org_unit_id"], user)
        return item

    def organization_context_payload(self, user):
        with connect() as conn:
            context = self.organization_context(conn, user)
        return {
            "selected": context["selected"],
            "accessible": context["accessible"],
        }

    def send_redirect(self, location, headers=None):
        self.send_response(302)
        self.send_header("Location", location)
        self.send_header("Content-Length", "0")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.close_connection = True
        self.end_headers()

    def send_link_redirect(self, link_id):
        user = self.current_user(required=False)
        self.require_module(user, "links")
        with connect() as conn:
            link = conn.execute("SELECT id, title, url, invalid FROM links WHERE id=? AND deleted_at IS NULL", (link_id,)).fetchone()
            if not link:
                raise AppError(404, "链接不存在")
            if link["invalid"]:
                raise AppError(410, "链接已标记失效，已阻止打开")
            conn.execute(
                "UPDATE links SET click_count=COALESCE(click_count, 0)+1, last_clicked_at=? WHERE id=?",
                (now_iso(), link_id),
            )
        self.send_response(302)
        self.send_header("Location", link["url"])
        self.send_header("Content-Length", "0")
        self.send_header("Connection", "close")
        self.close_connection = True
        self.end_headers()

    def send_backup_file(self, query):
        self.require_admin()
        filename = (query.get("file") or [""])[0]
        if not filename or "/" in filename or "\\" in filename or not filename.endswith(".db"):
            raise AppError(400, "备份文件名不合法")
        file_path = (BACKUP_DIR / filename).resolve()
        if BACKUP_DIR.resolve() not in file_path.parents or not file_path.exists():
            raise AppError(404, "备份文件不存在")
        content = file_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Connection", "close")
        self.close_connection = True
        self.end_headers()
        self.wfile.write(content)
        self.wfile.flush()

    def send_team_moment_image(self, image_id):
        user = self.current_user(required=False)
        self.require_module(user, "moments", "view")
        self.api_user = user
        with connect() as conn:
            image = conn.execute(
                """
                SELECT i.id, i.filename, i.mime_type, i.image_data, i.moment_id
                FROM team_moment_images i
                JOIN team_moments m ON m.id=i.moment_id
                WHERE i.id=? AND m.deleted_at IS NULL
                """,
                (image_id,),
            ).fetchone()
            if not image:
                raise AppError(404, "图片不存在")
            self.require_team_moment_access(conn, image["moment_id"], user)
            content = bytes(image["image_data"])
        self.send_response(200)
        self.send_header("Content-Type", image["mime_type"])
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Content-Disposition", f'inline; filename="moment-{image_id}"')
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'none'; sandbox")
        self.send_header("Connection", "close")
        self.close_connection = True
        self.end_headers()
        self.wfile.write(content)
        self.wfile.flush()

    def current_user(self, required=True):
        cookies = parse_cookies(self.headers.get("Cookie"))
        token = cookies.get("weekly_session")
        digest = token_digest(token)
        now = dt.datetime.now().replace(microsecond=0)
        with connect() as conn:
            session = conn.execute(
                """
                SELECT s.id, s.user_id, s.last_seen_at, s.expires_at
                FROM auth_sessions s
                WHERE s.token_hash=? AND s.revoked_at IS NULL
                """,
                (digest,),
            ).fetchone() if token else None
            if session and (parse_iso_datetime(session["expires_at"]) or now) <= now:
                conn.execute("UPDATE auth_sessions SET revoked_at=? WHERE id=?", (now_iso(), session["id"]))
                session = None
            user = None
            if session:
                user = conn.execute(
                    """
                    SELECT u.id, u.username, u.employee_id, u.display_name, u.role, u.user_type, u.auth_source,
                           u.classification_pending, u.suggested_org_unit_id,
                           suggested_org.name AS suggested_org_unit_name,
                           t.name AS user_type_name,
                           u.org_unit_id, o.name AS org_unit_name, o.slug AS org_unit_slug,
                           COALESCE(t.include_in_members, 1) AS eligible_members,
                           COALESCE(t.include_in_morning, 1) AS eligible_morning,
                           COALESCE(t.include_in_rules, 1) AS eligible_rules,
                           COALESCE(t.include_in_thanks, 1) AS eligible_thanks,
                           u.active, u.created_at
                    FROM users u
                    LEFT JOIN user_types t ON t.key = u.user_type
                    LEFT JOIN org_units o ON o.id = u.org_unit_id
                    LEFT JOIN org_units suggested_org ON suggested_org.id = u.suggested_org_unit_id
                    WHERE u.id=? AND u.active=1
                    """,
                    (session["user_id"],),
                ).fetchone()
                if user:
                    self.current_session_id = session["id"]
                    last_seen = parse_iso_datetime(session["last_seen_at"])
                    if not last_seen or (now - last_seen).total_seconds() >= 60:
                        timeout = get_int_setting(conn, "session_timeout_minutes", 480, minimum=15, maximum=43200)
                        conn.execute(
                            "UPDATE auth_sessions SET last_seen_at=?, expires_at=? WHERE id=?",
                            (now.isoformat(), (now + dt.timedelta(minutes=timeout)).isoformat(), session["id"]),
                        )
                else:
                    conn.execute("UPDATE auth_sessions SET revoked_at=? WHERE id=?", (now_iso(), session["id"]))
        if not user:
            if required:
                raise AppError(401, "登录状态已失效，请重新登录")
            return None
        return dict(user)

    def require_admin(self):
        user = self.current_user()
        if user["role"] != "admin":
            raise AppError(403, "仅管理员可操作")
        return user

    def require_internal_user(self, user=None):
        return user or self.current_user()

    def is_public_read_api(self, method, path):
        return method == "GET" and self.module_for_path(path) in MODULE_KEYS

    def module_for_path(self, path):
        if path.startswith("/api/user-types") or path.startswith("/api/users") or path.startswith("/api/org-units"):
            return "users"
        if path.startswith("/api/members") or path.startswith("/api/team-posts"):
            return "members"
        if path.startswith("/api/team-moments") or path.startswith("/api/team-moment-images"):
            return "moments"
        if path.startswith("/api/archive"):
            return "archive"
        if path.startswith("/api/morning-items"):
            return "morning"
        if path.startswith("/api/process-"):
            return "processes"
        if path.startswith("/api/rules") or path.startswith("/api/scores") or path.startswith("/api/dashboards/red-black"):
            return "rules"
        if path.startswith("/api/meetings") or path.startswith("/api/meeting-"):
            return "meetings"
        if path.startswith("/api/links") or path.startswith("/api/link-categories"):
            return "links"
        if path.startswith("/api/machines") or path.startswith("/api/shifts") or path.startswith("/api/dashboards/shifts"):
            return "shifts"
        if path.startswith("/api/thank-you") or path.startswith("/api/dashboards/thank-you"):
            return "thanks"
        if path.startswith("/api/settings") or path.startswith("/api/sso/diagnose") or path.startswith("/api/audit-logs") or path.startswith("/api/backups") or path.startswith("/api/recycle-bin"):
            return "system"
        if path.startswith("/api/team-replies"):
            return "members"
        return None

    def require_module(self, user, module_key, action="view"):
        if not module_key:
            return
        if not user and action != "view":
            raise AppError(401, "请先登录")
        if user and user.get("role") == "admin":
            return
        if module_key not in MODULE_KEYS:
            raise AppError(403, "当前账号无权访问该模块")
        action = action if action in PERMISSION_ACTIONS else "view"
        column = {
            "view": "can_view",
            "create": "can_create",
            "edit": "can_edit",
            "delete": "can_delete",
        }[action]
        with connect() as conn:
            row = conn.execute(
                f"""
                SELECT can_view, {column} AS allowed
                FROM module_permissions
                WHERE user_type_key=? AND module_key=?
                """,
                ((user.get("user_type") if user else GUEST_USER_TYPE_KEY) or DEFAULT_USER_TYPE_KEY, module_key),
            ).fetchone()
        if not row or not row["can_view"] or not row["allowed"]:
            if not user:
                raise AppError(403, "访客无权查看该模块")
            action_name = {"view": "查看", "create": "新增", "edit": "编辑", "delete": "删除"}[action]
            raise AppError(403, f"当前用户类型无权{action_name}该模块内容")

    def health(self):
        try:
            with connect() as conn:
                conn.execute("SELECT 1").fetchone()
                check = conn.execute("PRAGMA quick_check").fetchone()[0]
        except sqlite3.Error as exc:
            raise AppError(503, f"数据库检查失败：{exc}") from exc
        if check != "ok":
            raise AppError(503, f"数据库完整性检查失败：{check}")
        return {
            "status": "ok",
            "environment": DEPLOY_ENV,
            "release": RELEASE_ID,
            "database": "ok",
            "time": now_iso(),
        }

    def route_api(self, method, path, query):
        if path == "/api/health" and method == "GET":
            return self.health()
        if path == "/api/login" and method == "POST":
            return self.login()
        if path == "/api/logout" and method == "POST":
            return self.logout()
        if path == "/api/me" and method == "GET":
            user = self.current_user(required=False)
            return {"user": user, "permissions": permissions_for(user), "settings": self.public_settings(), "organization": self.organization_context_payload(user)}
        if path == "/api/org-context" and method == "GET":
            user = self.current_user(required=False)
            return self.organization_context_payload(user)
        if path == "/api/sessions" and method == "GET":
            return self.list_sessions(self.current_user())
        if len(path.strip("/").split("/")) == 3 and path.startswith("/api/sessions/") and method == "DELETE":
            return self.revoke_session(int(path.rsplit("/", 1)[1]), self.current_user())

        user = self.current_user(required=not self.is_public_read_api(method, path))
        self.api_user = user
        parts = path.strip("/").split("/")
        action = {"GET": "view", "POST": "create", "PATCH": "edit", "DELETE": "delete"}.get(method, "view")
        self.require_module(user, self.module_for_path(path), action)

        if path == "/api/team-posts":
            if method == "POST":
                return self.create_team_post(user)
        if len(parts) == 4 and parts[:2] == ["api", "team-posts"] and parts[3] == "replies" and method == "POST":
            return self.create_team_post_reply(int(parts[2]), user)
        if len(parts) == 4 and parts[:2] == ["api", "team-posts"] and parts[3] == "reactions" and method == "POST":
            return self.toggle_team_post_reaction(int(parts[2]), user)
        if len(parts) == 4 and parts[:2] == ["api", "team-replies"] and parts[3] == "reactions" and method == "POST":
            return self.toggle_team_reply_reaction(int(parts[2]), user)
        if len(parts) == 3 and parts[:2] == ["api", "team-replies"] and method == "DELETE":
            return self.delete_team_post_reply(int(parts[2]), user)

        if path == "/api/team-moments":
            if method == "GET":
                return {"moments": self.list_team_moments(user, query)}
            if method == "POST":
                return self.create_team_moment(user)
        if len(parts) == 3 and parts[:2] == ["api", "team-moments"]:
            if method == "PATCH":
                return self.update_team_moment(int(parts[2]), user)
            if method == "DELETE":
                return self.delete_team_moment(int(parts[2]), user)

        if path == "/api/me/password" and method == "PATCH":
            return self.change_own_password(user)

        if path == "/api/archive/years" and method == "GET":
            return self.archive_years(user)
        if path == "/api/archive/search" and method == "GET":
            return self.search_archive(user, query)

        if path == "/api/user-types":
            if method == "GET":
                return self.list_user_types()
            if method == "POST":
                return self.create_user_type()
        if path == "/api/org-units":
            if method == "GET":
                return {"units": self.list_org_units()}
            if method == "POST":
                return self.create_org_unit()
        if len(parts) == 3 and parts[:2] == ["api", "org-units"]:
            if method == "PATCH":
                return self.update_org_unit(int(parts[2]))
            if method == "DELETE":
                return self.delete_org_unit(int(parts[2]))
        if len(parts) == 4 and parts[:2] == ["api", "user-types"] and parts[3] == "permissions" and method == "PATCH":
            return self.update_user_type_permissions(parts[2])
        if len(parts) == 4 and parts[:2] == ["api", "user-types"] and parts[3] == "impact" and method == "POST":
            return self.user_type_impact(parts[2])
        if len(parts) == 3 and parts[:2] == ["api", "user-types"] and method == "DELETE":
            return self.delete_user_type(parts[2])

        if path == "/api/users":
            if method == "GET":
                return {"users": self.list_users()}
            if method == "POST":
                return self.create_user()
        if path == "/api/users/bulk-type" and method == "PATCH":
            return self.bulk_update_user_type(user)
        if path == "/api/users/bulk-org" and method == "PATCH":
            return self.bulk_update_user_org(user)
        if path == "/api/users/bulk-suggested-org" and method == "PATCH":
            return self.bulk_apply_suggested_org(user)
        if path == "/api/users/bulk-delete" and method == "DELETE":
            return self.bulk_delete_users(user)
        if len(parts) == 3 and parts[:2] == ["api", "users"] and method == "PATCH":
            return self.update_user(int(parts[2]))
        if len(parts) == 3 and parts[:2] == ["api", "users"] and method == "DELETE":
            return self.delete_user(int(parts[2]), user)

        if path == "/api/members":
            if method == "GET":
                return {"members": self.list_members(user)}
            if method == "POST":
                return self.create_member()
        if path == "/api/members/order" and method == "PATCH":
            return self.update_member_order()
        if len(parts) == 3 and parts[:2] == ["api", "members"] and method == "PATCH":
            return self.update_member(int(parts[2]))
        if len(parts) == 4 and parts[:2] == ["api", "members"] and parts[3] == "posts" and method == "POST":
            return self.create_member_post(int(parts[2]), user)
        if path == "/api/team-posts":
            if method == "GET":
                return {"posts": self.list_team_posts(user)}
            if method == "POST":
                return self.create_team_post(user)
        if len(parts) == 3 and parts[:2] == ["api", "team-posts"]:
            if method == "GET":
                return self.get_team_post(int(parts[2]), user)
            if method == "PATCH":
                return self.update_team_post(int(parts[2]), user)
            if method == "DELETE":
                return self.delete_team_post(int(parts[2]), user)
        if len(parts) == 4 and parts[:2] == ["api", "team-posts"] and parts[3] == "replies" and method == "POST":
            return self.create_team_post_reply(int(parts[2]), user)
        if len(parts) == 4 and parts[:2] == ["api", "team-posts"] and parts[3] == "reactions" and method == "POST":
            return self.toggle_team_post_reaction(int(parts[2]), user)
        if len(parts) == 4 and parts[:2] == ["api", "team-replies"] and parts[3] == "reactions" and method == "POST":
            return self.toggle_team_reply_reaction(int(parts[2]), user)
        if len(parts) == 3 and parts[:2] == ["api", "team-replies"] and method == "DELETE":
            return self.delete_team_post_reply(int(parts[2]), user)

        if path == "/api/morning-items":
            if method == "GET":
                return self.list_morning_items(query)
            if method == "POST":
                return self.create_morning_item(user)
        if path == "/api/morning-items/version" and method == "GET":
            return self.morning_items_version(query)
        if path == "/api/morning-items/order" and method == "PATCH":
            return self.update_morning_order(user)
        if len(parts) == 4 and parts[:2] == ["api", "morning-items"] and parts[3] == "history" and method == "GET":
            return self.list_morning_item_history(int(parts[2]))
        if len(parts) == 3 and parts[:2] == ["api", "morning-items"] and method == "PATCH":
            return self.update_morning_item(int(parts[2]), user)
        if len(parts) == 3 and parts[:2] == ["api", "morning-items"] and method == "DELETE":
            return self.delete_morning_item(int(parts[2]), user)

        if path == "/api/process-templates":
            if method == "GET":
                return {"templates": self.list_process_templates(user)}
            if method == "POST":
                return self.create_process_template(user)
        if len(parts) == 3 and parts[:2] == ["api", "process-templates"]:
            if method == "PATCH":
                return self.update_process_template(int(parts[2]), user)
            if method == "DELETE":
                return self.delete_process_template(int(parts[2]), user)
        if path == "/api/process-instances":
            if method == "GET":
                return {"instances": self.list_process_instances(user, query)}
            if method == "POST":
                return self.create_process_instance(user)
        if len(parts) == 3 and parts[:2] == ["api", "process-instances"]:
            if method == "PATCH":
                return self.update_process_instance(int(parts[2]), user)
            if method == "DELETE":
                return self.delete_process_instance(int(parts[2]), user)
        if len(parts) == 3 and parts[:2] == ["api", "process-instance-items"] and method == "PATCH":
            return self.update_process_instance_item(int(parts[2]), user)

        if path == "/api/rules":
            if method == "GET":
                return {"rules": self.list_rules(query)}
            if method == "POST":
                return self.create_rule()

        if path == "/api/scores":
            if method == "GET":
                return {"scores": self.list_scores(query)}
            if method == "POST":
                return self.create_score()
        if len(parts) == 3 and parts[:2] == ["api", "scores"] and method == "PATCH":
            return self.update_score(int(parts[2]))

        if path == "/api/dashboards/red-black" and method == "GET":
            return self.red_black_dashboard(query)

        if path == "/api/meetings":
            if method == "GET":
                return {
                    "meetings": self.list_meetings(query),
                    "attendance_users": self.list_current_organization_users(user),
                }
            if method == "POST":
                return self.create_meeting(user)
        if path == "/api/meetings/bulk-generate" and method == "POST":
            return self.bulk_generate_meetings()
        if len(parts) == 3 and parts[:2] == ["api", "meetings"] and method == "PATCH":
            return self.update_meeting(int(parts[2]))
        if len(parts) == 4 and parts[:2] == ["api", "meetings"] and parts[3] == "topics" and method == "PATCH":
            return self.update_meeting_topics(int(parts[2]))
        if len(parts) == 4 and parts[:2] == ["api", "meetings"] and parts[3] == "copy-agenda" and method == "POST":
            return self.copy_previous_meeting_agenda(int(parts[2]))
        if len(parts) == 4 and parts[:2] == ["api", "meetings"] and parts[3] == "agenda-options" and method == "POST":
            return self.add_meeting_preset_items(int(parts[2]))
        if path == "/api/meeting-topics":
            if method == "GET":
                return self.list_meeting_topics()
        if path == "/api/meeting-topic-types" and method == "POST":
            return self.create_meeting_topic_type()
        if len(parts) == 3 and parts[:2] == ["api", "meeting-topic-types"] and method == "DELETE":
            return self.delete_meeting_topic_type(int(parts[2]))
        if path == "/api/meeting-topic-options" and method == "POST":
            return self.create_meeting_topic_option()
        if len(parts) == 3 and parts[:2] == ["api", "meeting-topic-options"] and method == "PATCH":
            return self.update_meeting_topic_option(int(parts[2]))
        if len(parts) == 3 and parts[:2] == ["api", "meeting-topic-options"] and method == "DELETE":
            return self.delete_meeting_topic_option(int(parts[2]))
        if len(parts) == 4 and parts[:2] == ["api", "meetings"] and parts[3] == "items" and method == "POST":
            return self.create_meeting_item(int(parts[2]), user)
        if len(parts) == 5 and parts[:2] == ["api", "meetings"] and parts[3:] == ["items", "reorder"] and method == "POST":
            return self.reorder_meeting_items(int(parts[2]))
        if len(parts) == 4 and parts[:2] == ["api", "meetings"] and parts[3] == "attendance" and method == "POST":
            return self.upsert_attendance(int(parts[2]))
        if len(parts) == 3 and parts[:2] == ["api", "meeting-items"] and method == "PATCH":
            return self.update_meeting_item(int(parts[2]))
        if len(parts) == 3 and parts[:2] == ["api", "meeting-items"] and method == "DELETE":
            return self.delete_meeting_item(int(parts[2]), user)
        if len(parts) == 4 and parts[:2] == ["api", "meeting-items"] and parts[3] == "carry-forward" and method == "POST":
            return self.carry_forward_meeting_item(int(parts[2]))

        if path == "/api/links":
            if method == "GET":
                return {"links": self.list_links()}
            if method == "POST":
                return self.create_link()
        if len(parts) == 3 and parts[:2] == ["api", "links"]:
            if method == "PATCH":
                return self.update_link(int(parts[2]), user)
            if method == "DELETE":
                return self.delete_link(int(parts[2]), user)
        if path == "/api/link-categories":
            if method == "GET":
                return {"categories": self.list_link_categories()}
            if method == "POST":
                return self.create_link_category()

        if path == "/api/machines":
            if method == "GET":
                return {"machines": self.list_machines()}
            if method == "POST":
                return self.create_machine()
        if len(parts) == 3 and parts[:2] == ["api", "machines"] and method == "DELETE":
            return self.delete_machine(int(parts[2]))

        if path == "/api/shifts":
            if method == "GET":
                return {
                    "shifts": self.list_shifts(query),
                    "users": self.list_current_organization_users(user),
                }
            if method == "POST":
                return self.create_shift()
        if len(parts) == 3 and parts[:2] == ["api", "shifts"] and method == "DELETE":
            return self.delete_shift(int(parts[2]))
        if path == "/api/dashboards/shifts" and method == "GET":
            return self.shift_dashboard(query)

        if path == "/api/thank-you":
            if method == "GET":
                return {"votes": self.list_thank_you(query, user), "users": self.list_participating_users("thanks", user)}
            if method == "POST":
                return self.create_thank_you(user)
        if len(parts) == 3 and parts[:2] == ["api", "thank-you"]:
            if method == "PATCH":
                return self.update_thank_you(int(parts[2]), user)
            if method == "DELETE":
                return self.delete_thank_you(int(parts[2]), user)
        if path == "/api/dashboards/thank-you" and method == "GET":
            return self.thank_you_dashboard(query, user)

        if path == "/api/reminders" and method == "GET":
            return self.list_reminders(user)
        if path == "/api/reminders/read" and method == "PATCH":
            return self.mark_reminders_read(user)

        if path == "/api/recycle-bin" and method == "GET":
            return {"items": self.list_recycle_bin()}
        if len(parts) == 4 and parts[:2] == ["api", "recycle-bin"] and parts[3] == "restore" and method == "POST":
            return self.restore_recycle_item(int(parts[2]))
        if len(parts) == 3 and parts[:2] == ["api", "recycle-bin"] and method == "DELETE":
            return self.purge_recycle_item(int(parts[2]))

        if path == "/api/settings":
            if method == "GET":
                return {"settings": self.list_settings()}
            if method == "PATCH":
                return self.update_settings()
        if path == "/api/sso/diagnose" and method == "POST":
            return self.diagnose_sso()

        if path == "/api/audit-logs" and method == "GET":
            return {"logs": self.list_audit_logs(query)}

        if path == "/api/backups":
            if method == "GET":
                return {"backups": self.list_backups()}
            if method == "POST":
                return self.create_manual_backup()
        if path == "/api/backups/verify" and method == "POST":
            return self.verify_backup()
        if path == "/api/backups/restore" and method == "POST":
            return self.restore_backup()

        raise AppError(404, "接口不存在")


