from ..permissions import *


class AccountsHandlerMixin:
    def sso_redirect_uri(self, config):
        configured = (config.get("redirect_uri") or "").strip()
        if configured:
            return validate_sso_url(configured, "OIDC 回调地址")
        host = (self.headers.get("Host") or "").strip().lower()
        if not re.fullmatch(r"(?:localhost|127\.0\.0\.1)(?::\d{1,5})?", host):
            raise AppError(400, "正式部署必须在系统配置中填写 OIDC 回调地址")
        return f"http://{host}/api/sso/callback"

    def sso_return_target(self, path, query):
        if path == "/api/sso/login":
            return sanitize_sso_return_to((query.get("return_to") or [""])[0])
        state = (query.get("state") or [""])[0]
        if not state:
            return ""
        with connect() as conn:
            row = conn.execute(
                "SELECT return_to FROM sso_login_states WHERE state_hash=?",
                (token_digest(state),),
            ).fetchone()
        return sanitize_sso_return_to(row["return_to"]) if row else ""

    def issue_session(self, conn, user, action, summary, metadata=None, secure_cookie=False):
        user_data = dict(user)
        now = dt.datetime.now().replace(microsecond=0)
        timeout = get_int_setting(conn, "session_timeout_minutes", 480, minimum=15, maximum=43200)
        token = secrets.token_urlsafe(32)
        expires_at = now + dt.timedelta(minutes=timeout)
        cursor = conn.execute(
            """
            INSERT INTO auth_sessions(token_hash, user_id, ip_address, user_agent, created_at, last_seen_at, expires_at)
            VALUES(?,?,?,?,?,?,?)
            """,
            (
                token_digest(token), user_data["id"], self.client_address[0],
                (self.headers.get("User-Agent") or "")[:500], now.isoformat(), now.isoformat(), expires_at.isoformat(),
            ),
        )
        self.current_session_id = cursor.lastrowid
        conn.execute("DELETE FROM auth_sessions WHERE revoked_at IS NOT NULL AND revoked_at<?", ((now - dt.timedelta(days=30)).isoformat(),))
        safe_keys = (
            "id", "username", "employee_id", "display_name", "role", "user_type", "user_type_name",
            "org_unit_id", "org_unit_name", "org_unit_slug",
            "eligible_members", "eligible_morning", "eligible_rules", "eligible_thanks",
            "active", "created_at", "auth_source", "classification_pending",
            "suggested_org_unit_id", "suggested_org_unit_name",
        )
        safe_user = {key: user_data.get(key) for key in safe_keys if key in user_data}
        write_audit(conn, safe_user, action, "session", safe_user["id"], summary, metadata or {}, self.client_address[0])
        secure = "; Secure" if secure_cookie else ""
        cookie = f"weekly_session={token}; Path=/; Max-Age={timeout * 60}; HttpOnly; SameSite=Lax{secure}"
        return safe_user, cookie

    def start_sso_login(self, query=None):
        return_to = sanitize_sso_return_to(((query or {}).get("return_to") or [""])[0])
        with connect() as conn:
            config = sso_configuration(conn)
            if not config["enabled"]:
                raise AppError(400, "企业 SSO 尚未启用")
            if not sso_configuration_ready(config):
                raise AppError(400, "企业 SSO 配置不完整，请联系管理员")
            redirect_uri = self.sso_redirect_uri(config)
            discovery = load_oidc_discovery(config)
            state = secrets.token_urlsafe(32)
            nonce = secrets.token_urlsafe(32)
            verifier = secrets.token_urlsafe(64)
            now = dt.datetime.now().replace(microsecond=0)
            conn.execute("DELETE FROM sso_login_states WHERE expires_at<? OR used_at IS NOT NULL", ((now - dt.timedelta(minutes=10)).isoformat(),))
            conn.execute(
                """
                INSERT INTO sso_login_states(state_hash, nonce, code_verifier, redirect_uri, return_to, created_at, expires_at)
                VALUES(?,?,?,?,?,?,?)
                """,
                (token_digest(state), nonce, verifier, redirect_uri, return_to, now.isoformat(), (now + dt.timedelta(minutes=10)).isoformat()),
            )
        parameters = {
            "response_type": "code",
            "client_id": config["client_id"],
            "redirect_uri": redirect_uri,
            "scope": config["scopes"],
            "state": state,
            "nonce": nonce,
            "code_challenge": base64url_digest(verifier),
            "code_challenge_method": "S256",
        }
        separator = "&" if "?" in discovery["authorization_endpoint"] else "?"
        self.send_redirect(f"{discovery['authorization_endpoint']}{separator}{urlencode(parameters)}")

    def complete_sso_login(self, query):
        provider_error = (query.get("error_description") or query.get("error") or [""])[0]
        if provider_error:
            raise AppError(401, f"企业身份平台拒绝登录：{str(provider_error)[:160]}")
        code = (query.get("code") or [""])[0]
        state = (query.get("state") or [""])[0]
        if not code or not state:
            raise AppError(400, "SSO 回调缺少授权码或状态参数")
        now = dt.datetime.now().replace(microsecond=0)
        with connect() as conn:
            config = sso_configuration(conn)
            row = conn.execute(
                "SELECT * FROM sso_login_states WHERE state_hash=? AND used_at IS NULL",
                (token_digest(state),),
            ).fetchone()
            if not row or (parse_iso_datetime(row["expires_at"]) or now) <= now:
                raise AppError(400, "SSO 登录请求已失效，请重新发起登录")
            conn.execute("UPDATE sso_login_states SET used_at=? WHERE state_hash=?", (now.isoformat(), token_digest(state)))
            redirect_uri = row["redirect_uri"]
            verifier = row["code_verifier"]
            return_to = sanitize_sso_return_to(row["return_to"])
        if not sso_configuration_ready(config):
            raise AppError(400, "企业 SSO 配置已变更，请重新登录")
        discovery = load_oidc_discovery(config)
        token_form = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": config["client_id"],
            "code_verifier": verifier,
        }
        token_headers = {}
        if config["client_secret"]:
            supported = discovery.get("token_endpoint_auth_methods_supported") or []
            if "client_secret_basic" in supported:
                credentials = base64.b64encode(f"{config['client_id']}:{config['client_secret']}".encode("utf-8")).decode("ascii")
                token_headers["Authorization"] = f"Basic {credentials}"
            else:
                token_form["client_secret"] = config["client_secret"]
        tokens = fetch_json(
            discovery["token_endpoint"],
            method="POST",
            form=token_form,
            headers=token_headers,
            purpose="Access Token 接口",
        )
        access_token = str(tokens.get("access_token") or "")
        if not access_token:
            available = "、".join(sorted(str(key) for key in tokens.keys())[:12]) or "无"
            raise AppError(502, f"Access Token 接口未返回 access_token，可用字段：{available}")
        claims = fetch_json(
            discovery["userinfo_endpoint"],
            headers={"Authorization": f"Bearer {access_token}"},
            purpose="UserInfo 接口",
        )
        identity_claims = resolve_sso_identity(claims, config)
        sso_groups = identity_claims["groups"]
        employee_id = identity_claims["employee_id"]
        subject = identity_claims["subject"]
        display_name = identity_claims["display_name"]
        username = employee_id
        if not subject or not employee_id or not display_name or re.search(r"[\x00-\x1f\x7f]", employee_id):
            available = "、".join(sorted(str(key) for key in claims.keys())[:16]) or "无"
            raise AppError(
                400,
                f"UserInfo 无法映射账号。当前工号字段为 {config['username_claim']}，"
                f"顶层可用字段：{available}；可在系统管理中运行映射诊断",
            )
        provider_key = (config.get("issuer_url") or urlparse(discovery["authorization_endpoint"]).netloc).rstrip("/")
        identity = f"{provider_key}|{subject}"
        auth_source = "oauth2" if config.get("mode") == "manual" else "oidc"
        with connect() as conn:
            matched_org = match_sso_org_unit(conn, sso_groups)
            matched_org_id = matched_org["id"] if matched_org else None
            root_org = next(
                (unit for unit in organization_rows(conn) if not unit.get("parent_id")),
                None,
            )
            # SSO groups are an administrator-facing placement suggestion. New accounts
            # remain at the root until an administrator confirms their team.
            provision_org = root_org
            provision_org_id = provision_org["id"] if provision_org else None
            user = conn.execute(
                """
                SELECT u.*, t.name AS user_type_name,
                       o.name AS org_unit_name, o.slug AS org_unit_slug,
                       suggested_org.name AS suggested_org_unit_name,
                       COALESCE(t.include_in_members, 1) AS eligible_members,
                       COALESCE(t.include_in_morning, 1) AS eligible_morning,
                       COALESCE(t.include_in_rules, 1) AS eligible_rules,
                       COALESCE(t.include_in_thanks, 1) AS eligible_thanks
                FROM users u LEFT JOIN user_types t ON t.key=u.user_type
                LEFT JOIN org_units o ON o.id=u.org_unit_id
                LEFT JOIN org_units suggested_org ON suggested_org.id=u.suggested_org_unit_id
                WHERE u.auth_source IN ('oidc', 'oauth2') AND u.external_subject=?
                """,
                (identity,),
            ).fetchone()
            linked_existing = False
            created = False
            if not user:
                existing = conn.execute(
                    "SELECT * FROM users WHERE LOWER(employee_id)=LOWER(?) OR LOWER(username)=LOWER(?) ORDER BY CASE WHEN LOWER(employee_id)=LOWER(?) THEN 0 ELSE 1 END LIMIT 1",
                    (employee_id, employee_id, employee_id),
                ).fetchone()
                if existing:
                    if not existing["active"]:
                        raise AppError(403, "该企业账号对应的系统用户已停用")
                    if existing["external_subject"] and existing["external_subject"] != identity:
                        raise AppError(409, "该系统账号已绑定其他企业身份")
                    conn.execute(
                        "UPDATE users SET auth_source=?, external_subject=?, employee_id=? WHERE id=?",
                        (auth_source, identity, employee_id, existing["id"]),
                    )
                    linked_existing = True
                    user_id = existing["id"]
                else:
                    if not config["auto_provision"]:
                        raise AppError(403, "该企业账号尚未在系统中创建，请联系管理员")
                    user_type = conn.execute(
                        "SELECT key FROM user_types WHERE key=? AND active=1",
                        (GUEST_USER_TYPE_KEY,),
                    ).fetchone()
                    if not user_type:
                        raise AppError(500, "访客权限模板不可用，请联系管理员")
                    salt, password_hash = make_hash(secrets.token_urlsafe(48))
                    cursor = conn.execute(
                        """
                        INSERT INTO users(
                            username, employee_id, salt, password_hash, display_name, role, user_type,
                            org_unit_id, active, created_at, auth_source, external_subject,
                            classification_pending, suggested_org_unit_id, sso_groups_json, sso_last_login_at
                        )
                        VALUES(?,?,?,?,?,?,?,?,1,?,?,?,1,?,?,?)
                        """,
                        (
                            username, employee_id, salt, password_hash, display_name, "user", user_type["key"],
                            provision_org_id, now_iso(), auth_source, identity, matched_org_id,
                            json.dumps(sso_groups, ensure_ascii=False), now.isoformat(),
                        ),
                    )
                    user_id = cursor.lastrowid
                    created = True
                user = conn.execute(
                    """
                    SELECT u.*, t.name AS user_type_name,
                           o.name AS org_unit_name, o.slug AS org_unit_slug,
                           COALESCE(t.include_in_members, 1) AS eligible_members,
                           COALESCE(t.include_in_morning, 1) AS eligible_morning,
                           COALESCE(t.include_in_rules, 1) AS eligible_rules,
                           COALESCE(t.include_in_thanks, 1) AS eligible_thanks
                    FROM users u LEFT JOIN user_types t ON t.key=u.user_type
                    LEFT JOIN org_units o ON o.id=u.org_unit_id
                    WHERE u.id=? AND u.active=1
                    """,
                    (user_id,),
                ).fetchone()
            elif str(user["employee_id"] or "").lower() != employee_id.lower():
                duplicate = conn.execute(
                    "SELECT id FROM users WHERE LOWER(employee_id)=LOWER(?) AND id<>?",
                    (employee_id, user["id"]),
                ).fetchone()
                if duplicate:
                    raise AppError(409, "该工号已关联其他系统用户，请联系管理员处理")
                conn.execute("UPDATE users SET employee_id=?, auth_source=? WHERE id=?", (employee_id, auth_source, user["id"]))
                user = dict(user)
                user["employee_id"] = employee_id
                user["auth_source"] = auth_source
            if not user or not user["active"]:
                raise AppError(403, "企业账号对应的系统用户不可用")
            suggested_org_id = matched_org_id if matched_org_id and matched_org_id != user["org_unit_id"] else None
            conn.execute(
                """
                UPDATE users
                SET suggested_org_unit_id=?, sso_groups_json=?, sso_last_login_at=?
                WHERE id=?
                """,
                (suggested_org_id, json.dumps(sso_groups, ensure_ascii=False), now.isoformat(), user["id"]),
            )
            user = conn.execute(
                """
                SELECT u.*, t.name AS user_type_name,
                       o.name AS org_unit_name, o.slug AS org_unit_slug,
                       suggested_org.name AS suggested_org_unit_name,
                       COALESCE(t.include_in_members, 1) AS eligible_members,
                       COALESCE(t.include_in_morning, 1) AS eligible_morning,
                       COALESCE(t.include_in_rules, 1) AS eligible_rules,
                       COALESCE(t.include_in_thanks, 1) AS eligible_thanks
                FROM users u LEFT JOIN user_types t ON t.key=u.user_type
                LEFT JOIN org_units o ON o.id=u.org_unit_id
                LEFT JOIN org_units suggested_org ON suggested_org.id=u.suggested_org_unit_id
                WHERE u.id=? AND u.active=1
                """,
                (user["id"],),
            ).fetchone()
            safe_user, cookie = self.issue_session(
                conn,
                user,
                "auth.sso_login",
                "用户通过企业 SSO 登录",
                {"created": created, "linked_existing": linked_existing, "provider": provider_key, "employee_id": employee_id, "sso_groups": sso_groups, "org_unit_id": user["org_unit_id"]},
                secure_cookie=redirect_uri.startswith("https://") or self.request_is_https(),
            )
            redirect_org = next(
                (unit for unit in organization_rows(conn) if unit["id"] == user["org_unit_id"]),
                provision_org,
            )
        route = redirect_org["route"] if redirect_org else "/"
        self.send_redirect(append_sso_notice(return_to or route, "sso", "success"), {"Set-Cookie": cookie})

    def login(self):
        data = read_json(self)
        username = (data.get("username") or "").strip()
        password = data.get("password") or ""
        ip_address = self.client_address[0]
        now = dt.datetime.now().replace(microsecond=0)
        with connect() as conn:
            max_attempts = get_int_setting(conn, "login_max_attempts", 5, minimum=3, maximum=20)
            lock_minutes = get_int_setting(conn, "login_lock_minutes", 15, minimum=1, maximum=1440)
            attempt = conn.execute(
                "SELECT * FROM login_attempts WHERE username=? AND ip_address=?",
                (username.lower(), ip_address),
            ).fetchone()
            locked_until = parse_iso_datetime(attempt["locked_until"]) if attempt else None
            if locked_until and locked_until > now:
                remaining = max(1, int((locked_until - now).total_seconds() / 60) + 1)
                raise AppError(429, f"登录失败次数过多，请 {remaining} 分钟后再试")
            user = conn.execute(
                """
                SELECT u.*, t.name AS user_type_name,
                       o.name AS org_unit_name, o.slug AS org_unit_slug,
                       suggested_org.name AS suggested_org_unit_name,
                       COALESCE(t.include_in_members, 1) AS eligible_members,
                       COALESCE(t.include_in_morning, 1) AS eligible_morning,
                       COALESCE(t.include_in_rules, 1) AS eligible_rules,
                       COALESCE(t.include_in_thanks, 1) AS eligible_thanks
                FROM users u
                LEFT JOIN user_types t ON t.key = u.user_type
                LEFT JOIN org_units o ON o.id=u.org_unit_id
                LEFT JOIN org_units suggested_org ON suggested_org.id=u.suggested_org_unit_id
                WHERE LOWER(u.username)=LOWER(?) AND u.active=1
                """,
                (username,),
            ).fetchone()
            if not user or not verify_password(password, user["salt"], user["password_hash"]):
                window_start = parse_iso_datetime(attempt["window_started_at"]) if attempt else None
                if not window_start or (now - window_start).total_seconds() > lock_minutes * 60:
                    failed_count = 1
                    window_start = now
                else:
                    failed_count = int(attempt["failed_count"] or 0) + 1
                next_lock = now + dt.timedelta(minutes=lock_minutes) if failed_count >= max_attempts else None
                conn.execute(
                    """
                    INSERT INTO login_attempts(username, ip_address, failed_count, window_started_at, locked_until, updated_at)
                    VALUES(?,?,?,?,?,?)
                    ON CONFLICT(username, ip_address) DO UPDATE SET
                        failed_count=excluded.failed_count,
                        window_started_at=excluded.window_started_at,
                        locked_until=excluded.locked_until,
                        updated_at=excluded.updated_at
                    """,
                    (username.lower(), ip_address, failed_count, window_start.isoformat(), next_lock.isoformat() if next_lock else None, now.isoformat()),
                )
                conn.commit()
                remaining = max(0, max_attempts - failed_count)
                if next_lock:
                    raise AppError(429, f"登录失败次数过多，账号已临时锁定 {lock_minutes} 分钟")
                raise AppError(401, f"账号或密码错误，还可尝试 {remaining} 次")
            conn.execute("DELETE FROM login_attempts WHERE username=? AND ip_address=?", (username.lower(), ip_address))
            timeout = get_int_setting(conn, "session_timeout_minutes", 480, minimum=15, maximum=43200)
            token = secrets.token_urlsafe(32)
            expires_at = now + dt.timedelta(minutes=timeout)
            cursor = conn.execute(
                """
                INSERT INTO auth_sessions(token_hash, user_id, ip_address, user_agent, created_at, last_seen_at, expires_at)
                VALUES(?,?,?,?,?,?,?)
                """,
                (token_digest(token), user["id"], ip_address, (self.headers.get("User-Agent") or "")[:500], now.isoformat(), now.isoformat(), expires_at.isoformat()),
            )
            self.current_session_id = cursor.lastrowid
            conn.execute("DELETE FROM auth_sessions WHERE revoked_at IS NOT NULL AND revoked_at<?", ((now - dt.timedelta(days=30)).isoformat(),))
            safe_user = {
                key: user[key]
                for key in (
                    "id", "username", "employee_id", "display_name", "role", "user_type", "user_type_name",
                    "org_unit_id", "org_unit_name", "org_unit_slug",
                    "eligible_members", "eligible_morning", "eligible_rules", "eligible_thanks",
                    "active", "created_at", "auth_source", "classification_pending",
                    "suggested_org_unit_id", "suggested_org_unit_name",
                )
            }
            write_audit(conn, safe_user, "auth.login", "session", safe_user["id"], "用户登录", {}, self.client_address[0])
        secure_cookie = "; Secure" if self.request_is_https() else ""
        return {
            "user": safe_user,
            "permissions": permissions_for(safe_user),
            "organization": self.organization_context_payload(safe_user),
            "message": "登录成功",
            "_headers": {"Set-Cookie": f"weekly_session={token}; Path=/; Max-Age={timeout * 60}; HttpOnly; SameSite=Strict{secure_cookie}"},
        }

    def logout(self):
        cookies = parse_cookies(self.headers.get("Cookie"))
        token = cookies.get("weekly_session")
        if token:
            with connect() as conn:
                conn.execute("UPDATE auth_sessions SET revoked_at=? WHERE token_hash=? AND revoked_at IS NULL", (now_iso(), token_digest(token)))
        return {
            "message": "已退出",
            "_headers": {"Set-Cookie": f"weekly_session=; Path=/; Max-Age=0; HttpOnly; SameSite=Strict{'; Secure' if self.request_is_https() else ''}"},
        }

    def list_sessions(self, user):
        now = now_iso()
        with connect() as conn:
            conn.execute("UPDATE auth_sessions SET revoked_at=? WHERE revoked_at IS NULL AND expires_at<=?", (now, now))
            sessions = rows_to_list(conn.execute(
                """
                SELECT id, ip_address, user_agent, created_at, last_seen_at, expires_at
                FROM auth_sessions
                WHERE user_id=? AND revoked_at IS NULL AND expires_at>?
                ORDER BY last_seen_at DESC
                """,
                (user["id"], now),
            ).fetchall())
        current_id = getattr(self, "current_session_id", None)
        for session in sessions:
            session["current"] = session["id"] == current_id
            agent = session.get("user_agent") or "未知设备"
            if "Mobile" in agent or "Android" in agent or "iPhone" in agent:
                session["device"] = "手机浏览器"
            elif "Windows" in agent:
                session["device"] = "Windows 浏览器"
            elif "Macintosh" in agent:
                session["device"] = "Mac 浏览器"
            else:
                session["device"] = "浏览器会话"
        return {"sessions": sessions}

    def revoke_session(self, session_id, user):
        with connect() as conn:
            session = conn.execute(
                "SELECT id, user_id, revoked_at FROM auth_sessions WHERE id=?",
                (session_id,),
            ).fetchone()
            if not session or session["user_id"] != user["id"]:
                raise AppError(404, "会话不存在")
            conn.execute("UPDATE auth_sessions SET revoked_at=? WHERE id=? AND revoked_at IS NULL", (now_iso(), session_id))
            write_audit(conn, user, "auth.session_revoke", "session", session_id, "用户撤销了登录会话", {}, self.client_address[0])
        current = session_id == getattr(self, "current_session_id", None)
        result = {"message": "会话已退出", "current_revoked": current}
        if current:
            result["_headers"] = {"Set-Cookie": "weekly_session=; Path=/; Max-Age=0; HttpOnly; SameSite=Strict"}
        return result

    def change_own_password(self, user):
        data = read_json(self)
        old_password = data.get("old_password") or ""
        new_password = data.get("new_password") or ""
        confirm_password = data.get("confirm_password") or ""
        if not old_password:
            raise AppError(400, "请输入当前密码")
        if len(new_password) < 6:
            raise AppError(400, "新密码至少 6 位")
        if new_password != confirm_password:
            raise AppError(400, "两次输入的新密码不一致")
        with connect() as conn:
            row = conn.execute(
                "SELECT id, salt, password_hash FROM users WHERE id=? AND active=1",
                (user["id"],),
            ).fetchone()
            if not row:
                raise AppError(404, "当前用户不存在")
            if not verify_password(old_password, row["salt"], row["password_hash"]):
                raise AppError(400, "当前密码不正确")
            salt, password_hash = make_hash(new_password)
            conn.execute(
                "UPDATE users SET salt=?, password_hash=? WHERE id=?",
                (salt, password_hash, user["id"]),
            )
            conn.execute(
                "UPDATE auth_sessions SET revoked_at=? WHERE user_id=? AND id<>? AND revoked_at IS NULL",
                (now_iso(), user["id"], getattr(self, "current_session_id", -1)),
            )
            write_audit(conn, user, "user.password", "user", user["id"], "用户修改了自己的密码", {}, self.client_address[0])
        return {"message": "密码已更新，其他设备已退出登录"}

    def send_json(self, data, status=200, headers=None):
        headers = headers or {}
        extra = data.pop("_headers", {}) if isinstance(data, dict) else {}
        headers.update(extra)
        payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Connection", "close")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "same-origin")
        self.close_connection = True
        for key, value in headers.items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(payload)
        self.wfile.flush()

    def list_user_types(self):
        self.require_admin()
        with connect() as conn:
            types = rows_to_list(
                conn.execute(
                    """
                    SELECT t.*, COUNT(CASE WHEN u.active=1 THEN 1 END) AS user_count
                    FROM user_types t
                    LEFT JOIN users u ON u.user_type=t.key
                    WHERE t.active=1
                    GROUP BY t.key
                    ORDER BY CASE WHEN t.key=? THEN 1 ELSE 0 END, t.sort_order, t.key
                    """,
                    (GUEST_USER_TYPE_KEY,),
                ).fetchall()
            )
            permissions = rows_to_list(
                conn.execute(
                    """
                    SELECT user_type_key, module_key, can_view, can_create, can_edit, can_delete
                    FROM module_permissions
                    """
                ).fetchall()
            )
        permission_map = {}
        for permission in permissions:
            permission_map.setdefault(permission["user_type_key"], {})[permission["module_key"]] = {
                "view": bool(permission["can_view"]),
                "create": bool(permission["can_create"]),
                "edit": bool(permission["can_edit"]),
                "delete": bool(permission["can_delete"]),
            }
        for user_type in types:
            user_type["is_guest"] = user_type["key"] == GUEST_USER_TYPE_KEY
            user_type["participation"] = {
                scope: bool(user_type[column])
                for scope, (column, _) in PARTICIPATION_SCOPES.items()
            }
            user_type["permissions"] = permission_map.get(user_type["key"], {})
            user_type["modules"] = sorted(
                module for module, actions in user_type["permissions"].items() if actions.get("view")
            )
            with connect() as conn:
                user_type["assigned_users"] = [row["display_name"] for row in conn.execute(
                    "SELECT display_name FROM users WHERE user_type=? AND active=1 ORDER BY display_name LIMIT 8",
                    (user_type["key"],),
                ).fetchall()]
        return {"types": types, "modules": MODULE_CATALOG}

    def normalize_user_type_participation(self, type_key, raw_participation, current=None):
        current = current or {}
        raw_participation = raw_participation if isinstance(raw_participation, dict) else {}
        normalized = {}
        for scope, (column, _) in PARTICIPATION_SCOPES.items():
            value = raw_participation.get(scope, current.get(column, True))
            normalized[scope] = False if type_key == GUEST_USER_TYPE_KEY else bool(value)
        return normalized

    def normalize_user_type_permissions(self, type_key, raw_permissions):
        if not isinstance(raw_permissions, dict):
            raise AppError(400, "操作权限格式不正确")
        normalized = {}
        for module in MODULE_KEYS:
            actions = raw_permissions.get(module) or {}
            if not isinstance(actions, dict):
                actions = {}
            values = {action: bool(actions.get(action)) for action in PERMISSION_ACTIONS}
            if values["create"] or values["edit"] or values["delete"]:
                values["view"] = True
            if type_key == GUEST_USER_TYPE_KEY:
                values["create"] = False
                values["edit"] = False
                values["delete"] = False
            normalized[module] = values
        if type_key == GUEST_USER_TYPE_KEY:
            normalized["dashboard"] = {action: False for action in PERMISSION_ACTIONS}
            if not any(actions["view"] for actions in normalized.values()):
                raise AppError(400, "访客至少需要保留一个可查看模块")
        return normalized

    def user_type_impact(self, type_key):
        self.require_admin()
        data = read_json(self)
        normalized = self.normalize_user_type_permissions(type_key, data.get("permissions") or {})
        with connect() as conn:
            user_type = conn.execute("SELECT * FROM user_types WHERE key=? AND active=1", (type_key,)).fetchone()
            if not user_type:
                raise AppError(404, "用户类型不存在")
            existing = {
                row["module_key"]: {action: bool(row[f"can_{action}"]) for action in PERMISSION_ACTIONS}
                for row in conn.execute("SELECT * FROM module_permissions WHERE user_type_key=?", (type_key,)).fetchall()
            }
            users = [row["display_name"] for row in conn.execute(
                "SELECT display_name FROM users WHERE user_type=? AND active=1 ORDER BY display_name",
                (type_key,),
            ).fetchall()]
        changed = []
        for module in MODULE_CATALOG:
            before = existing.get(module["key"], {action: False for action in PERMISSION_ACTIONS})
            after = normalized[module["key"]]
            for action in PERMISSION_ACTIONS:
                if before.get(action) != after.get(action):
                    changed.append({
                        "module": module["key"],
                        "module_name": module["name"],
                        "action": action,
                        "enabled": after[action],
                    })
        participation = self.normalize_user_type_participation(
            type_key,
            data.get("participation"),
            dict(user_type),
        )
        participation_changed = []
        for scope, (column, label) in PARTICIPATION_SCOPES.items():
            before = bool(user_type[column])
            after = participation[scope]
            if before != after:
                participation_changed.append({"scope": scope, "name": label, "enabled": after})
        return {
            "user_type": type_key,
            "version": user_type["version"],
            "affected_count": len(users),
            "affected_users": users[:12],
            "changed": changed,
            "participation_changed": participation_changed,
        }

    def create_user_type(self):
        admin = self.require_admin()
        data = read_json(self)
        name = str(data.get("name") or "").strip()
        description = str(data.get("description") or "").strip()
        copy_from = str(data.get("copy_from") or "").strip()
        if not name:
            raise AppError(400, "用户类型名称不能为空")
        if len(name) > 30:
            raise AppError(400, "用户类型名称最多 30 个字符")
        if len(description) > 200:
            raise AppError(400, "用户类型说明最多 200 个字符")
        type_key = f"type_{uuid.uuid4().hex[:10]}"
        with connect() as conn:
            duplicate = conn.execute(
                "SELECT key FROM user_types WHERE active=1 AND lower(name)=lower(?)",
                (name,),
            ).fetchone()
            if duplicate:
                raise AppError(400, "用户类型名称已存在")
            sort_order = conn.execute(
                "SELECT COALESCE(MAX(sort_order), 0) + 10 FROM user_types WHERE key<>?",
                (GUEST_USER_TYPE_KEY,),
            ).fetchone()[0]
            source_type = None
            source_permissions = {}
            if copy_from:
                source = conn.execute(
                    "SELECT * FROM user_types WHERE key=? AND active=1",
                    (copy_from,),
                ).fetchone()
                if not source:
                    raise AppError(400, "复制来源用户类型不存在")
                source_type = source
                source_permissions = {
                    row["module_key"]: row
                    for row in conn.execute(
                        "SELECT * FROM module_permissions WHERE user_type_key=?",
                        (copy_from,),
                    ).fetchall()
                }
            participation_values = [
                int(bool(source_type[column])) if source_type else 1
                for column, _ in PARTICIPATION_SCOPES.values()
            ]
            conn.execute(
                """
                INSERT INTO user_types(
                    key, name, description, sort_order, locked, active,
                    include_in_members, include_in_morning, include_in_rules, include_in_thanks,
                    created_at
                ) VALUES(?,?,?,?,0,1,?,?,?,?,?)
                """,
                (type_key, name, description, sort_order, *participation_values, now_iso()),
            )
            for module_key in MODULE_KEYS:
                source = source_permissions.get(module_key)
                actions = (
                    int(source["can_view"]),
                    int(source["can_create"]),
                    int(source["can_edit"]),
                    int(source["can_delete"]),
                ) if source else (0, 0, 0, 0)
                conn.execute(
                    """
                    INSERT INTO module_permissions(
                        user_type_key, module_key, can_view, can_create, can_edit, can_delete, updated_at
                    ) VALUES(?,?,?,?,?,?,?)
                    """,
                    (type_key, module_key, *actions, now_iso()),
                )
            write_audit(conn, admin, "user_type.create", "user_type", None, "用户类型已创建", {"user_type": type_key, "name": name, "copy_from": copy_from}, self.client_address[0])
        return {"message": "用户类型已创建", **self.list_user_types()}

    def update_user_type_permissions(self, type_key):
        admin = self.require_admin()
        data = read_json(self)
        raw_permissions = data.get("permissions")
        if raw_permissions is None:
            modules = data.get("modules") or []
            if not isinstance(modules, list):
                raise AppError(400, "模块权限格式不正确")
            raw_permissions = {
                module: {action: True for action in PERMISSION_ACTIONS}
                for module in modules if module in MODULE_KEYS
            }
        normalized = self.normalize_user_type_permissions(type_key, raw_permissions)
        expected_version = data.get("expected_version")
        with connect() as conn:
            user_type = conn.execute(
                "SELECT * FROM user_types WHERE key=? AND active=1",
                (type_key,),
            ).fetchone()
            if not user_type:
                raise AppError(404, "用户类型不存在")
            if expected_version is not None and int(expected_version) != int(user_type["version"]):
                raise AppError(409, "该用户类型刚刚被其他管理员修改，请刷新后核对最新权限")
            if type_key != GUEST_USER_TYPE_KEY:
                name = str(data.get("name") or user_type["name"] or "").strip()
                description = str(data.get("description", user_type["description"] or "") or "").strip()
                if not name:
                    raise AppError(400, "用户类型名称不能为空")
                if len(name) > 30 or len(description) > 200:
                    raise AppError(400, "用户类型名称或说明过长")
                duplicate = conn.execute(
                    "SELECT key FROM user_types WHERE active=1 AND lower(name)=lower(?) AND key<>?",
                    (name, type_key),
                ).fetchone()
                if duplicate:
                    raise AppError(400, "用户类型名称已存在")
            participation = self.normalize_user_type_participation(
                type_key,
                data.get("participation"),
                dict(user_type),
            )
            updated = conn.execute(
                """
                UPDATE user_types
                SET name=?, description=?, include_in_members=?, include_in_morning=?,
                    include_in_rules=?, include_in_thanks=?, version=version+1
                WHERE key=? AND version=?
                """,
                (
                    name if type_key != GUEST_USER_TYPE_KEY else user_type["name"],
                    description if type_key != GUEST_USER_TYPE_KEY else user_type["description"],
                    int(participation["members"]),
                    int(participation["morning"]),
                    int(participation["rules"]),
                    int(participation["thanks"]),
                    type_key,
                    user_type["version"],
                ),
            )
            if updated.rowcount != 1:
                raise AppError(409, "该用户类型刚刚被其他管理员修改，请刷新后重试")
            conn.execute("DELETE FROM module_permissions WHERE user_type_key=?", (type_key,))
            for module, actions in normalized.items():
                conn.execute(
                    """
                    INSERT INTO module_permissions(
                        user_type_key, module_key, can_view, can_create, can_edit, can_delete, updated_at
                    ) VALUES(?,?,?,?,?,?,?)
                    """,
                    (
                        type_key,
                        module,
                        int(actions["view"]),
                        int(actions["create"]),
                        int(actions["edit"]),
                        int(actions["delete"]),
                        now_iso(),
                    ),
                )
            write_audit(
                conn,
                admin,
                "user_type.permissions",
                "user_type",
                None,
                "用户类型权限与参与范围已更新",
                {"user_type": type_key, "permissions": normalized, "participation": participation},
                self.client_address[0],
            )
        return {"message": "用户类型权限已更新", **self.list_user_types(), "permissions": permissions_for(admin)}

    def delete_user_type(self, type_key):
        admin = self.require_admin()
        if type_key == GUEST_USER_TYPE_KEY:
            raise AppError(400, "访客权限模板不能删除")
        with connect() as conn:
            user_type = conn.execute(
                "SELECT key, name, locked FROM user_types WHERE key=? AND active=1",
                (type_key,),
            ).fetchone()
            if not user_type:
                raise AppError(404, "用户类型不存在")
            users = conn.execute(
                "SELECT display_name FROM users WHERE user_type=? AND active=1 ORDER BY id LIMIT 4",
                (type_key,),
            ).fetchall()
            if users:
                names = "、".join(row["display_name"] for row in users)
                raise AppError(400, f"该类型仍有用户：{names}。请先将这些用户调整到其他类型")
            remaining = conn.execute(
                "SELECT COUNT(*) FROM user_types WHERE active=1 AND key NOT IN (?,?)",
                (type_key, GUEST_USER_TYPE_KEY),
            ).fetchone()[0]
            if remaining == 0:
                raise AppError(400, "至少保留一个可分配的用户类型，请先新增替代类型")
            conn.execute("DELETE FROM module_permissions WHERE user_type_key=?", (type_key,))
            conn.execute("UPDATE user_types SET active=0, locked=0 WHERE key=?", (type_key,))
            write_audit(conn, admin, "user_type.delete", "user_type", None, "用户类型已删除", {"user_type": type_key, "name": user_type["name"]}, self.client_address[0])
        return {"message": "用户类型已删除", **self.list_user_types()}

    def list_org_units(self):
        self.require_admin()
        with connect() as conn:
            return organization_rows(conn)

    def normalize_org_payload(self, conn, data, current_id=None):
        name = str(data.get("name") or "").strip()
        if not name or len(name) > 60:
            raise AppError(400, "团队名称不能为空且最多 60 个字符")
        slug = normalize_org_slug(data.get("slug") or name)
        visibility_mode = str(data.get("visibility_mode") or "unit").strip().lower()
        if visibility_mode not in ORG_VISIBILITY_MODES:
            raise AppError(400, "团队可见范围不正确")
        parent_id = data.get("parent_id")
        try:
            parent_id = int(parent_id) if parent_id not in (None, "") else None
        except (TypeError, ValueError):
            raise AppError(400, "上级团队参数不正确")
        if parent_id == current_id:
            raise AppError(400, "团队不能将自己设为上级")
        if parent_id and not conn.execute("SELECT id FROM org_units WHERE id=? AND active=1", (parent_id,)).fetchone():
            raise AppError(400, "上级团队不存在")
        if current_id and parent_id:
            rows = organization_rows(conn)
            by_parent = {}
            for row in rows:
                by_parent.setdefault(row.get("parent_id"), []).append(row["id"])
            descendants = {current_id}
            pending = [current_id]
            while pending:
                parent = pending.pop()
                for child in by_parent.get(parent, []):
                    if child not in descendants:
                        descendants.add(child)
                        pending.append(child)
            if parent_id in descendants:
                raise AppError(400, "不能把团队移动到自己的下级")
        duplicate = conn.execute(
            "SELECT id FROM org_units WHERE COALESCE(parent_id,0)=COALESCE(?,0) AND slug=? AND active=1 AND id<>COALESCE(?,0)",
            (parent_id, slug, current_id),
        ).fetchone()
        if duplicate:
            raise AppError(400, "同一上级下已存在相同团队路由")
        default_user_type = str(data.get("default_user_type") or DEFAULT_USER_TYPE_KEY).strip()
        if not conn.execute(
            "SELECT key FROM user_types WHERE key=? AND key<>? AND active=1",
            (default_user_type, GUEST_USER_TYPE_KEY),
        ).fetchone():
            raise AppError(400, "默认用户类型不存在")
        raw_groups = data.get("sso_groups") or []
        if isinstance(raw_groups, str):
            try:
                decoded_groups = json.loads(raw_groups)
                raw_groups = decoded_groups if isinstance(decoded_groups, list) else re.split(r"[,;\n]", raw_groups)
            except json.JSONDecodeError:
                raw_groups = re.split(r"[,;\n]", raw_groups)
        if not isinstance(raw_groups, list):
            raise AppError(400, "SSO 群组格式不正确")
        groups = []
        for value in raw_groups:
            group = str(value).strip()
            if group and group.lower() not in {item.lower() for item in groups}:
                groups.append(group[:160])
        try:
            sort_order = int(data.get("sort_order") or 0)
        except (TypeError, ValueError):
            sort_order = 0
        return {
            "name": name,
            "slug": slug,
            "parent_id": parent_id,
            "visibility_mode": visibility_mode,
            "default_user_type": default_user_type,
            "sso_groups": json.dumps(groups, ensure_ascii=False),
            "sort_order": sort_order,
        }

    def create_org_unit(self):
        admin = self.require_admin()
        data = read_json(self)
        with connect() as conn:
            payload = self.normalize_org_payload(conn, data)
            cursor = conn.execute(
                """
                INSERT INTO org_units(name, slug, parent_id, visibility_mode, default_user_type, sso_groups, sort_order, active, created_at, updated_at)
                VALUES(?,?,?,?,?,?,?,1,?,?)
                """,
                (*payload.values(), now_iso(), now_iso()),
            )
            write_audit(conn, admin, "org_unit.create", "org_unit", cursor.lastrowid, "团队层级已创建", {"name": payload["name"]}, self.client_address[0])
        return {"message": "团队层级已创建", "units": self.list_org_units()}

    def update_org_unit(self, org_unit_id):
        admin = self.require_admin()
        data = read_json(self)
        with connect() as conn:
            current = conn.execute("SELECT * FROM org_units WHERE id=? AND active=1", (org_unit_id,)).fetchone()
            if not current:
                raise AppError(404, "团队层级不存在")
            merged = {**dict(current), **data}
            payload = self.normalize_org_payload(conn, merged, org_unit_id)
            conn.execute(
                """
                UPDATE org_units
                SET name=?, slug=?, parent_id=?, visibility_mode=?, default_user_type=?, sso_groups=?, sort_order=?, updated_at=?
                WHERE id=?
                """,
                (*payload.values(), now_iso(), org_unit_id),
            )
            write_audit(conn, admin, "org_unit.update", "org_unit", org_unit_id, "团队层级已更新", {"name": payload["name"]}, self.client_address[0])
        return {"message": "团队层级已更新", "units": self.list_org_units()}

    def delete_org_unit(self, org_unit_id):
        admin = self.require_admin()
        with connect() as conn:
            unit = conn.execute("SELECT * FROM org_units WHERE id=? AND active=1", (org_unit_id,)).fetchone()
            if not unit:
                raise AppError(404, "团队层级不存在")
            children = conn.execute("SELECT COUNT(*) FROM org_units WHERE parent_id=? AND active=1", (org_unit_id,)).fetchone()[0]
            users = conn.execute("SELECT COUNT(*) FROM users WHERE org_unit_id=? AND active=1", (org_unit_id,)).fetchone()[0]
            if children:
                raise AppError(400, "该团队仍有下级，请先迁移或删除下级团队")
            if users:
                raise AppError(400, f"该团队仍有 {users} 个用户，请先批量迁移用户")
            root_count = conn.execute("SELECT COUNT(*) FROM org_units WHERE parent_id IS NULL AND active=1").fetchone()[0]
            if unit["parent_id"] is None and root_count <= 1:
                raise AppError(400, "至少需要保留一个根团队")
            conn.execute("UPDATE org_units SET active=0, updated_at=? WHERE id=?", (now_iso(), org_unit_id))
            write_audit(conn, admin, "org_unit.delete", "org_unit", org_unit_id, "团队层级已删除", {"name": unit["name"]}, self.client_address[0])
        return {"message": "团队层级已删除", "units": self.list_org_units()}

    def list_users(self):
        self.require_admin()
        with connect() as conn:
            users = rows_to_list(
                conn.execute(
                    """
                    SELECT u.id, u.username, u.employee_id, u.display_name, u.role, u.user_type, u.auth_source,
                           u.classification_pending, u.suggested_org_unit_id, u.sso_groups_json, u.sso_last_login_at,
                           suggested_org.name AS suggested_org_unit_name,
                           COALESCE(t.name, u.user_type) AS user_type_name,
                           COALESCE(t.include_in_members, 1) AS eligible_members,
                           COALESCE(t.include_in_morning, 1) AS eligible_morning,
                           COALESCE(t.include_in_rules, 1) AS eligible_rules,
                           COALESCE(t.include_in_thanks, 1) AS eligible_thanks,
                           u.org_unit_id, o.name AS org_unit_name,
                           u.active, u.created_at
                    FROM users u
                    LEFT JOIN user_types t ON t.key = u.user_type
                    LEFT JOIN org_units o ON o.id=u.org_unit_id
                    LEFT JOIN org_units suggested_org ON suggested_org.id=u.suggested_org_unit_id
                    WHERE u.active=1
                    ORDER BY u.id
                    """
                ).fetchall()
            )
        for user in users:
            try:
                groups = json.loads(user.get("sso_groups_json") or "[]")
            except (TypeError, json.JSONDecodeError):
                groups = []
            user["sso_groups"] = [str(group).strip() for group in groups if str(group).strip()]
            user.pop("sso_groups_json", None)
        return users

    def list_participating_users(self, scope, viewer=None, collaboration=False):
        if scope not in PARTICIPATION_SCOPES:
            raise AppError(400, "参与范围不正确")
        column = PARTICIPATION_SCOPES[scope][0]
        with connect() as conn:
            if collaboration:
                org_where, org_params = self.organization_collaboration_user_filter(conn, "u", viewer)
            else:
                org_where, org_params = self.organization_current_user_filter(conn, "u", viewer)
            return rows_to_list(
                conn.execute(
                    f"""
                    SELECT u.id, u.username, u.display_name, u.user_type,
                           COALESCE(t.name, u.user_type) AS user_type_name,
                           u.org_unit_id, o.name AS org_unit_name
                    FROM users u
                    LEFT JOIN user_types t ON t.key=u.user_type
                    LEFT JOIN org_units o ON o.id=u.org_unit_id
                    WHERE u.active=1 AND COALESCE(t.{column}, 1)=1 AND {org_where}
                    ORDER BY o.sort_order, o.name, t.sort_order, u.display_name
                    """,
                    org_params,
                ).fetchall()
            )

    def list_current_organization_users(self, viewer=None):
        with connect() as conn:
            org_where, org_params = self.organization_current_user_filter(conn, "u", viewer)
            return rows_to_list(
                conn.execute(
                    f"""
                    SELECT u.id, u.username, u.display_name, u.user_type,
                           COALESCE(t.name, u.user_type) AS user_type_name,
                           u.org_unit_id, o.name AS org_unit_name
                    FROM users u
                    LEFT JOIN user_types t ON t.key=u.user_type
                    LEFT JOIN org_units o ON o.id=u.org_unit_id
                    WHERE u.active=1 AND {org_where}
                    ORDER BY t.sort_order, u.display_name, u.id
                    """,
                    org_params,
                ).fetchall()
            )

    def bulk_update_user_type(self, admin):
        self.require_admin()
        data = read_json(self)
        raw_user_ids = data.get("user_ids") or []
        if not isinstance(raw_user_ids, list):
            raise AppError(400, "批量用户列表格式不正确")
        user_ids = []
        for raw_id in raw_user_ids:
            try:
                user_id = int(raw_id)
            except (TypeError, ValueError):
                continue
            if user_id not in user_ids:
                user_ids.append(user_id)
        if not user_ids:
            raise AppError(400, "请至少选择一个账号")
        if len(user_ids) > 200:
            raise AppError(400, "单次最多调整 200 个账号")
        user_type = str(data.get("user_type") or "").strip()
        if not user_type or user_type == GUEST_USER_TYPE_KEY:
            raise AppError(400, "请选择可分配的用户类型")
        placeholders = ",".join("?" for _ in user_ids)
        with connect() as conn:
            target_type = conn.execute(
                "SELECT key, name FROM user_types WHERE key=? AND active=1",
                (user_type,),
            ).fetchone()
            if not target_type:
                raise AppError(404, "目标用户类型不存在")
            users = rows_to_list(
                conn.execute(
                    f"SELECT id, display_name FROM users WHERE active=1 AND id IN ({placeholders})",
                    user_ids,
                ).fetchall()
            )
            if len(users) != len(user_ids):
                raise AppError(400, "部分账号不存在或已停用，请刷新后重试")
            conn.execute(
                f"UPDATE users SET user_type=?, classification_pending=0 WHERE active=1 AND id IN ({placeholders})",
                [user_type, *user_ids],
            )
            for user_id in user_ids:
                sync_member_for_user(conn, user_id)
            write_audit(
                conn,
                admin,
                "user.bulk_type",
                "user",
                None,
                "批量调整用户类型",
                {
                    "user_ids": user_ids,
                    "user_names": [item["display_name"] for item in users],
                    "user_type": user_type,
                    "user_type_name": target_type["name"],
                },
                self.client_address[0],
            )
        return {"message": f"已调整 {len(user_ids)} 个账号", "users": self.list_users()}

    def bulk_update_user_org(self, admin):
        self.require_admin()
        data = read_json(self)
        raw_ids = data.get("user_ids") or []
        try:
            user_ids = list(dict.fromkeys(int(value) for value in raw_ids))
            org_unit_id = int(data.get("org_unit_id"))
        except (TypeError, ValueError):
            raise AppError(400, "用户或团队参数不正确")
        if not user_ids:
            raise AppError(400, "请至少选择一个账号")
        placeholders = ",".join("?" for _ in user_ids)
        with connect() as conn:
            unit = conn.execute("SELECT id, name FROM org_units WHERE id=? AND active=1", (org_unit_id,)).fetchone()
            if not unit:
                raise AppError(404, "目标团队不存在")
            count = conn.execute(f"SELECT COUNT(*) FROM users WHERE id IN ({placeholders}) AND active=1", user_ids).fetchone()[0]
            if count != len(user_ids):
                raise AppError(400, "部分账号不存在或已停用")
            conn.execute(
                f"UPDATE users SET org_unit_id=?, suggested_org_unit_id=NULL WHERE id IN ({placeholders})",
                [org_unit_id, *user_ids],
            )
            write_audit(conn, admin, "user.bulk_org", "user", None, "批量调整所属团队", {"user_ids": user_ids, "org_unit_id": org_unit_id, "org_unit_name": unit["name"]}, self.client_address[0])
        return {"message": f"已调整 {len(user_ids)} 个账号所属团队", "users": self.list_users()}

    def bulk_apply_suggested_org(self, admin):
        self.require_admin()
        data = read_json(self)
        raw_ids = data.get("user_ids") or []
        try:
            user_ids = list(dict.fromkeys(int(value) for value in raw_ids))
        except (TypeError, ValueError):
            raise AppError(400, "用户参数不正确")
        if not user_ids:
            raise AppError(400, "请至少选择一个账号")
        if len(user_ids) > 200:
            raise AppError(400, "单次最多调整 200 个账号")
        placeholders = ",".join("?" for _ in user_ids)
        with connect() as conn:
            assignments = rows_to_list(
                conn.execute(
                    f"""
                    SELECT u.id, u.display_name, u.suggested_org_unit_id, o.name AS suggested_org_name
                    FROM users u
                    JOIN org_units o ON o.id=u.suggested_org_unit_id AND o.active=1
                    WHERE u.active=1 AND u.id IN ({placeholders})
                    """,
                    user_ids,
                ).fetchall()
            )
            if not assignments:
                raise AppError(400, "所选账号没有可采用的 SSO 建议团队")
            for assignment in assignments:
                conn.execute(
                    "UPDATE users SET org_unit_id=?, suggested_org_unit_id=NULL WHERE id=?",
                    (assignment["suggested_org_unit_id"], assignment["id"]),
                )
            write_audit(
                conn,
                admin,
                "user.bulk_suggested_org",
                "user",
                None,
                "批量采用 SSO 建议团队",
                {
                    "assignments": [
                        {
                            "user_id": item["id"],
                            "display_name": item["display_name"],
                            "org_unit_id": item["suggested_org_unit_id"],
                            "org_unit_name": item["suggested_org_name"],
                        }
                        for item in assignments
                    ],
                    "skipped_user_ids": [user_id for user_id in user_ids if user_id not in {item["id"] for item in assignments}],
                },
                self.client_address[0],
            )
        return {
            "message": f"已采用 {len(assignments)} 个账号的 SSO 建议团队",
            "applied": len(assignments),
            "skipped": len(user_ids) - len(assignments),
            "users": self.list_users(),
        }

    def bulk_delete_users(self, admin):
        self.require_admin()
        data = read_json(self)
        raw_ids = data.get("user_ids") or []
        if not isinstance(raw_ids, list):
            raise AppError(400, "批量用户列表格式不正确")
        try:
            user_ids = list(dict.fromkeys(int(value) for value in raw_ids))
        except (TypeError, ValueError):
            raise AppError(400, "用户参数不正确")
        if not user_ids:
            raise AppError(400, "请至少选择一个账号")
        if len(user_ids) > 200:
            raise AppError(400, "单次最多删除 200 个账号")
        if int(admin["id"]) in user_ids:
            raise AppError(400, "不能删除当前登录账号")
        placeholders = ",".join("?" for _ in user_ids)
        deleted_at = now_iso()
        with connect() as conn:
            users = rows_to_list(
                conn.execute(
                    f"SELECT id, username, display_name FROM users WHERE active=1 AND id IN ({placeholders})",
                    user_ids,
                ).fetchall()
            )
            if len(users) != len(user_ids):
                raise AppError(400, "部分账号不存在或已删除，请刷新后重试")
            for target in users:
                add_recycle_record(
                    conn,
                    "user",
                    target["id"],
                    target["display_name"] or target["username"],
                    admin,
                    {"username": target["username"]},
                )
            conn.execute(f"UPDATE users SET active=0 WHERE id IN ({placeholders})", user_ids)
            conn.execute(f"UPDATE members SET active=0 WHERE user_id IN ({placeholders})", user_ids)
            conn.execute(
                f"UPDATE auth_sessions SET revoked_at=? WHERE user_id IN ({placeholders}) AND revoked_at IS NULL",
                [deleted_at, *user_ids],
            )
            write_audit(
                conn,
                admin,
                "user.bulk_delete",
                "user",
                None,
                "批量删除用户",
                {"user_ids": user_ids, "user_names": [target["display_name"] for target in users]},
                self.client_address[0],
            )
        return {"message": f"已删除 {len(user_ids)} 个账号", "users": self.list_users()}

    def create_user(self):
        admin = self.require_admin()
        data = read_json(self)
        username = str(data.get("username") or "").strip()
        employee_id = str(data.get("employee_id") or username).strip()
        display_name = str(data.get("display_name") or username).strip()
        role = data.get("role") or "user"
        user_type = str(data.get("user_type") or "").strip()
        try:
            org_unit_id = int(data.get("org_unit_id"))
        except (TypeError, ValueError):
            raise AppError(400, "新增用户时必须指定所属团队")
        if not username or not employee_id or not display_name:
            raise AppError(400, "账号、工号和姓名不能为空")
        if role not in ("admin", "user"):
            raise AppError(400, "账号授权方式不正确")
        if not user_type or user_type == GUEST_USER_TYPE_KEY:
            raise AppError(400, "新增用户时必须指定有效用户类型")
        salt, password_hash = make_hash(data.get("password") or "123456")
        with connect() as conn:
            if not conn.execute("SELECT key FROM user_types WHERE key=? AND active=1", (user_type,)).fetchone():
                raise AppError(400, "用户类型不存在，请先创建用户类型")
            if not conn.execute("SELECT id FROM org_units WHERE id=? AND active=1", (org_unit_id,)).fetchone():
                raise AppError(400, "所属团队不存在")
            if conn.execute("SELECT id FROM users WHERE LOWER(employee_id)=LOWER(?)", (employee_id,)).fetchone():
                raise AppError(400, "工号已关联其他用户")
            cursor = conn.execute(
                "INSERT INTO users(username, employee_id, salt, password_hash, display_name, role, user_type, org_unit_id, active, created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (username, employee_id, salt, password_hash, display_name, role, user_type, org_unit_id, 1, now_iso()),
            )
            sync_member_for_user(conn, cursor.lastrowid)
            write_audit(conn, admin, "user.create", "user", cursor.lastrowid, "用户已创建", {"username": username, "role": role, "user_type": user_type}, self.client_address[0])
        return {"message": "用户已创建", "users": self.list_users()}

    def update_user(self, user_id):
        admin = self.require_admin()
        data = read_json(self)
        fields = []
        values = []
        if "username" in data:
            username = (data.get("username") or "").strip()
            if not username:
                raise AppError(400, "账号不能为空")
            fields.append("username=?")
            values.append(username)
        if "employee_id" in data:
            employee_id = (data.get("employee_id") or "").strip()
            if not employee_id:
                raise AppError(400, "工号不能为空")
            fields.append("employee_id=?")
            values.append(employee_id)
        for key in ("display_name", "role", "active", "user_type", "org_unit_id"):
            if key in data:
                fields.append(f"{key}=?")
                values.append(data[key])
        if "user_type" in data:
            fields.append("classification_pending=0")
        if data.get("password"):
            salt, password_hash = make_hash(data["password"])
            fields.extend(["salt=?", "password_hash=?"])
            values.extend([salt, password_hash])
        if not fields:
            raise AppError(400, "没有可更新字段")
        values.append(user_id)
        with connect() as conn:
            if "username" in data:
                duplicate = conn.execute(
                    "SELECT id FROM users WHERE username=? AND id<>?",
                    ((data.get("username") or "").strip(), user_id),
                ).fetchone()
                if duplicate:
                    raise AppError(400, "账号已存在")
            if "employee_id" in data:
                duplicate = conn.execute(
                    "SELECT id FROM users WHERE LOWER(employee_id)=LOWER(?) AND id<>?",
                    ((data.get("employee_id") or "").strip(), user_id),
                ).fetchone()
                if duplicate:
                    raise AppError(400, "工号已关联其他用户")
            if "role" in data and data.get("role") not in ("admin", "user"):
                raise AppError(400, "账号授权方式不正确")
            if "user_type" in data:
                if data.get("user_type") == GUEST_USER_TYPE_KEY or not conn.execute("SELECT key FROM user_types WHERE key=? AND active=1", (data.get("user_type"),)).fetchone():
                    raise AppError(400, "用户类型不存在")
            if "org_unit_id" in data:
                try:
                    org_unit_id = int(data.get("org_unit_id"))
                except (TypeError, ValueError):
                    raise AppError(400, "所属团队参数不正确")
                if not conn.execute("SELECT id FROM org_units WHERE id=? AND active=1", (org_unit_id,)).fetchone():
                    raise AppError(400, "所属团队不存在")
                current_org = conn.execute("SELECT org_unit_id FROM users WHERE id=?", (user_id,)).fetchone()
                if current_org and current_org["org_unit_id"] != org_unit_id:
                    fields.append("suggested_org_unit_id=NULL")
            conn.execute(f"UPDATE users SET {', '.join(fields)} WHERE id=?", values)
            sync_member_for_user(conn, user_id)
            write_audit(conn, admin, "user.update", "user", user_id, "用户已更新", {"fields": list(data.keys())}, self.client_address[0])
        return {"message": "用户已更新", "users": self.list_users()}

    def delete_user(self, user_id, current_user):
        self.require_admin()
        if user_id == current_user["id"]:
            raise AppError(400, "不能删除当前登录账号")
        with connect() as conn:
            user = conn.execute("SELECT id, username, display_name, active FROM users WHERE id=?", (user_id,)).fetchone()
            if not user:
                raise AppError(404, "用户不存在")
            if user["active"] == 0:
                return {"message": "用户已删除", "users": self.list_users()}
            add_recycle_record(
                conn,
                "user",
                user_id,
                user["display_name"] or user["username"],
                current_user,
                {"username": user["username"]},
            )
            conn.execute("UPDATE users SET active=0 WHERE id=?", (user_id,))
            conn.execute("UPDATE members SET active=0 WHERE user_id=?", (user_id,))
            conn.execute("UPDATE auth_sessions SET revoked_at=? WHERE user_id=? AND revoked_at IS NULL", (now_iso(), user_id))
            write_audit(conn, current_user, "user.delete", "user", user_id, "用户已删除", {}, self.client_address[0])
        return {"message": "用户已删除", "users": self.list_users()}

    def list_members(self, viewer=None):
        with connect() as conn:
            org_where, org_params = self.organization_user_filter(conn, "u", viewer)
            members = rows_to_list(
                conn.execute(
                    f"""
                    SELECT m.*, u.display_name AS linked_user, u.username AS account
                    FROM members m
                    JOIN users u ON u.id = m.user_id
                    LEFT JOIN user_types t ON t.key=u.user_type
                    WHERE m.active=1 AND u.active=1 AND COALESCE(t.include_in_members, 1)=1 AND {org_where}
                    ORDER BY CASE WHEN m.sort_order=0 THEN m.id ELSE m.sort_order END, m.id
                    """,
                    org_params,
                ).fetchall()
            )
            posts = rows_to_list(
                conn.execute(
                    """
                    SELECT p.*, u.display_name
                    FROM member_posts p
                    JOIN users u ON u.id = p.user_id
                    ORDER BY p.created_at DESC
                    """
                ).fetchall()
            )
        post_map = {}
        for post in posts:
            post_map.setdefault(post["member_id"], []).append(post)
        for member in members:
            member["tags"] = json.loads(member["tags"] or "[]")
            member["skills"] = json.loads(member["skills"] or "[]")
            member["machine_scope"] = json.loads(member["machine_scope"] or "[]")
            member["posts"] = post_map.get(member["id"], [])
        return members

    def update_member_order(self):
        admin = self.require_admin()
        data = read_json(self)
        member_ids = data.get("member_ids") or []
        if not isinstance(member_ids, list):
            raise AppError(400, "成员排序格式不正确")
        try:
            member_ids = [int(member_id) for member_id in member_ids]
        except (TypeError, ValueError):
            raise AppError(400, "成员排序包含无效成员")
        if len(member_ids) != len(set(member_ids)):
            raise AppError(400, "成员排序不能包含重复成员")
        with connect() as conn:
            org_where, org_params = self.organization_user_filter(conn, "u", admin)
            active_ids = {
                row["id"]
                for row in conn.execute(
                    f"""
                    SELECT m.id
                    FROM members m
                    JOIN users u ON u.id=m.user_id
                    LEFT JOIN user_types t ON t.key=u.user_type
                    WHERE m.active=1
                      AND u.active=1
                      AND COALESCE(t.include_in_members, 1)=1
                      AND {org_where}
                    """,
                    org_params,
                ).fetchall()
            }
            if set(member_ids) != active_ids:
                raise AppError(400, "成员排序列表与当前团队成员不一致，请刷新后重试")
            for index, member_id in enumerate(member_ids, start=1):
                conn.execute("UPDATE members SET sort_order=? WHERE id=?", (index, member_id))
            write_audit(
                conn,
                admin,
                "member.order",
                "member",
                None,
                "团队成员卡片顺序已更新",
                {"member_ids": member_ids},
                self.client_address[0],
            )
        return {"message": "成员顺序已更新", "members": self.list_members(admin)}

    def create_member(self):
        self.require_admin()
        data = read_json(self)
        tags = data.get("tags") or []
        if isinstance(tags, str):
            tags = [item.strip() for item in tags.split(",") if item.strip()]
        with connect() as conn:
            conn.execute(
                "INSERT INTO members(user_id, name, avatar_url, title, responsibilities, tags, comment, created_at) VALUES(?,?,?,?,?,?,?,?)",
                (data.get("user_id") or None, data.get("name"), data.get("avatar_url") or "", data.get("title") or "", data.get("responsibilities") or "", json.dumps(tags, ensure_ascii=False), data.get("comment") or "", now_iso()),
            )
        return {"message": "成员档案已创建", "members": self.list_members()}

    def update_member(self, member_id):
        user = self.current_user()
        data = read_json(self)
        with connect() as conn:
            member = conn.execute("SELECT * FROM members WHERE id=?", (member_id,)).fetchone()
            if not member:
                raise AppError(404, "成员不存在")
            if user["role"] != "admin" and member["user_id"] != user["id"]:
                raise AppError(403, "无权修改该成员档案")
            fields = []
            values = []
            allowed = ("name", "avatar_url", "title", "responsibilities", "comment", "user_id", "expertise", "backup_owner", "contact")
            for key in allowed:
                if key in data:
                    fields.append(f"{key}=?")
                    values.append(data[key] or None if key == "user_id" else data[key])
            for json_key in ("tags", "skills", "machine_scope"):
                if json_key in data:
                    items = data.get(json_key) or []
                    if isinstance(items, str):
                        items = [item.strip() for item in items.split(",") if item.strip()]
                    fields.append(f"{json_key}=?")
                    values.append(json.dumps(items, ensure_ascii=False))
            if not fields:
                raise AppError(400, "没有可更新字段")
            values.append(member_id)
            conn.execute(f"UPDATE members SET {', '.join(fields)} WHERE id=?", values)
            if member["user_id"] and "name" in data:
                conn.execute("UPDATE users SET display_name=? WHERE id=?", (data["name"], member["user_id"]))
            write_audit(conn, user, "member.update", "member", member_id, "成员画像已更新", {"fields": list(data.keys())}, self.client_address[0])
        return {"message": "成员档案已更新", "members": self.list_members()}

    def create_member_post(self, member_id, user):
        data = read_json(self)
        kind = data.get("kind") if data.get("kind") in ("comment", "roast") else "comment"
        content = (data.get("content") or "").strip()
        if not content:
            raise AppError(400, "内容不能为空")
        with connect() as conn:
            conn.execute(
                "INSERT INTO member_posts(member_id, user_id, kind, content, created_at) VALUES(?,?,?,?,?)",
                (member_id, user["id"], kind, content, now_iso()),
            )
        return {"message": "已发布", "members": self.list_members()}


