from .config import *

def now_iso():
    return dt.datetime.now().replace(microsecond=0).isoformat()


def today_iso():
    return dt.date.today().isoformat()


def is_past_date(value):
    return dt.date.fromisoformat(value) < dt.date.today()


def previous_workday(value):
    current = dt.date.fromisoformat(value) if isinstance(value, str) else value
    current -= dt.timedelta(days=1)
    while current.weekday() >= 5:
        current -= dt.timedelta(days=1)
    return current.isoformat()


def week_start(value=None):
    if value:
        date = dt.date.fromisoformat(value)
    else:
        date = dt.date.today()
    return (date - dt.timedelta(days=date.weekday())).isoformat()


def date_range(start, end, max_days=62):
    start_date = dt.date.fromisoformat(start)
    end_date = dt.date.fromisoformat(end or start)
    if end_date < start_date:
        raise AppError(400, "结束日期不能早于开始日期")
    days = (end_date - start_date).days + 1
    if days > max_days:
        raise AppError(400, f"一次最多批量处理 {max_days} 天")
    return [(start_date + dt.timedelta(days=offset)).isoformat() for offset in range(days)]


def normalize_recurrence(data):
    rule = data.get("recurrence_rule") or ""
    recurrence_type = data.get("recurrence_type") or "weekly"
    recurrence_value = str(data.get("recurrence_value") or data.get("recurrence_weeks") or "1")
    if rule:
        if ":" in rule:
            recurrence_type, recurrence_value = rule.split(":", 1)
        else:
            recurrence_type, recurrence_value = "weekly", rule
    if recurrence_type == "monthly_week":
        if recurrence_value not in MONTHLY_RECURRENCE_VALUES:
            raise AppError(400, "月度生成规则不合法")
        return recurrence_type, recurrence_value, 1
    recurrence = max(1, min(4, int(recurrence_value or 1)))
    return "weekly", str(recurrence), recurrence


def monthly_week_position(date):
    current = dt.date.fromisoformat(date) if isinstance(date, str) else date
    same_weekday = []
    cursor = current.replace(day=1)
    while cursor.month == current.month:
        if cursor.weekday() == current.weekday():
            same_weekday.append(cursor)
        cursor += dt.timedelta(days=1)
    ordinal = same_weekday.index(current) + 1 if current in same_weekday else 0
    reverse = len(same_weekday) - ordinal + 1 if ordinal else 0
    return ordinal, reverse


def recurrence_matches(option, offset, meeting_date):
    recurrence_type = option.get("recurrence_type") or "weekly"
    recurrence_value = str(option.get("recurrence_value") or option.get("recurrence_weeks") or "1")
    if recurrence_type == "monthly_week":
        ordinal, reverse = monthly_week_position(meeting_date)
        return (
            (recurrence_value == "first" and ordinal == 1)
            or (recurrence_value == "second" and ordinal == 2)
            or (recurrence_value == "third" and ordinal == 3)
            or (recurrence_value == "fourth" and ordinal == 4)
            or (recurrence_value == "penultimate" and reverse == 2)
            or (recurrence_value == "last" and reverse == 1)
        )
    recurrence = max(1, min(4, int(option.get("recurrence_weeks") or recurrence_value or 1)))
    return offset % recurrence == 0


def link_meeting_topic(conn, meeting_id, type_id, created_by=None):
    if not type_id:
        return
    topic = conn.execute(
        """
        SELECT t.id, t.sort_order
        FROM meeting_topic_types t
        JOIN meetings m ON m.id=? AND m.org_unit_id=t.org_unit_id
        WHERE t.id=? AND t.active=1
        """,
        (meeting_id, type_id),
    ).fetchone()
    if not topic:
        return
    conn.execute(
        """
        INSERT OR IGNORE INTO meeting_topic_links(
            meeting_id, type_id, sort_order, created_by, created_at
        ) VALUES(?,?,?,?,?)
        """,
        (meeting_id, topic["id"], topic["sort_order"] or 0, created_by, now_iso()),
    )


@contextmanager
def connect():
    conn = sqlite3.connect(DB_PATH, timeout=SQLITE_BUSY_TIMEOUT_MS / 1000)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute(f"PRAGMA busy_timeout = {SQLITE_BUSY_TIMEOUT_MS}")
    conn.execute("PRAGMA synchronous = NORMAL")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def make_hash(password, salt=None):
    salt = salt or secrets.token_hex(16)
    hashed = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 120000)
    return salt, hashed.hex()


def verify_password(password, salt, password_hash):
    _, hashed = make_hash(password, salt)
    return hmac.compare_digest(hashed, password_hash)


def token_digest(token):
    return hashlib.sha256((token or "").encode("utf-8")).hexdigest()


def parse_iso_datetime(value):
    try:
        return dt.datetime.fromisoformat(value) if value else None
    except (TypeError, ValueError):
        return None


def row_to_dict(row):
    return dict(row) if row else None


def rows_to_list(rows):
    return [dict(row) for row in rows]


def read_json(handler):
    length = int(handler.headers.get("Content-Length") or 0)
    if length == 0:
        return {}
    raw = handler.rfile.read(length).decode("utf-8")
    return json.loads(raw or "{}")


def decode_team_moment_image(value, index=0):
    if not isinstance(value, dict):
        raise AppError(400, "图片数据格式不正确")
    data_url = str(value.get("data_url") or "")
    match = re.fullmatch(r"data:([^;,]+);base64,(.+)", data_url, re.DOTALL)
    if not match or match.group(1).lower() not in TEAM_MOMENT_IMAGE_TYPES:
        raise AppError(400, "团队时刻仅支持 JPG、PNG 或 WebP 图片")
    mime_type = match.group(1).lower()
    try:
        content = base64.b64decode(match.group(2), validate=True)
    except (ValueError, TypeError) as exc:
        raise AppError(400, "图片内容不是有效的 Base64 数据") from exc
    if not content or len(content) > TEAM_MOMENT_MAX_IMAGE_BYTES:
        raise AppError(400, "单张图片不能超过 5 MB")
    signature, extension = TEAM_MOMENT_IMAGE_TYPES[mime_type]
    if not content.startswith(signature) or (mime_type == "image/webp" and content[8:12] != b"WEBP"):
        raise AppError(400, "图片内容与文件类型不一致")
    original_name = Path(str(value.get("name") or f"moment-{index + 1}{extension}")).name
    stem = re.sub(r"[^a-zA-Z0-9._-]+", "-", Path(original_name).stem).strip(".-") or f"moment-{index + 1}"
    return {
        "filename": f"{stem[:80]}{extension}",
        "mime_type": mime_type,
        "data": content,
    }


def parse_cookies(header):
    cookies = {}
    if not header:
        return cookies
    for part in header.split(";"):
        if "=" in part:
            key, value = part.strip().split("=", 1)
            cookies[key] = value
    return cookies




class AppError(Exception):
    def __init__(self, status, message):
        self.status = status
        self.message = message


