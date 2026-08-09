"""Pooled outbound HTTP client for OAuth2/OIDC identity providers."""

import http.client
import base64
import json
import re
import threading
import time
from urllib.parse import urlencode, urljoin, urlparse, urlunparse
from urllib.request import getproxies, proxy_bypass

from .common import AppError
from .config import (
    SSO_DISCOVERY_CACHE_SECONDS,
    SSO_HTTP_IDLE_SECONDS,
    SSO_HTTP_POOL_SIZE,
    SSO_HTTP_TIMEOUT_SECONDS,
)


SSO_MAX_RESPONSE_BYTES = 1024 * 1024
SSO_REDIRECT_STATUSES = {301, 302, 303, 307, 308}


def validate_sso_url(value, label):
    parsed = urlparse(value or "")
    local_hosts = {"127.0.0.1", "localhost", "::1"}
    if not parsed.hostname or parsed.scheme not in ("http", "https"):
        raise AppError(400, f"{label}不是合法的 HTTP 地址")
    if parsed.scheme != "https" and parsed.hostname.lower() not in local_hosts:
        raise AppError(400, f"{label}必须使用 HTTPS")
    if parsed.username or parsed.password:
        raise AppError(400, f"{label}不能包含账号或密码")
    return value


def provider_error_message(payload):
    try:
        data = json.loads(payload.decode("utf-8", errors="replace"))
    except json.JSONDecodeError:
        return ""
    if not isinstance(data, dict):
        return ""
    for key in ("error_description", "error_msg", "message", "error"):
        value = data.get(key)
        if isinstance(value, (str, int)) and str(value).strip():
            return re.sub(r"[\x00-\x1f\x7f]+", " ", str(value)).strip()[:240]
    return ""


class SsoHttpConnectionPool:
    """A bounded, thread-safe keep-alive pool grouped by provider origin."""

    def __init__(self, max_per_origin=SSO_HTTP_POOL_SIZE, idle_seconds=SSO_HTTP_IDLE_SECONDS):
        self.max_per_origin = max_per_origin
        self.idle_seconds = idle_seconds
        self._condition = threading.Condition()
        self._idle = {}
        self._open_counts = {}

    @staticmethod
    def origin(parsed):
        default_port = 443 if parsed.scheme == "https" else 80
        return parsed.scheme, parsed.hostname.lower(), parsed.port or default_port

    @staticmethod
    def proxy_for(parsed):
        if proxy_bypass(parsed.hostname):
            return None
        proxy_url = getproxies().get(parsed.scheme)
        if not proxy_url:
            return None
        if "://" not in proxy_url:
            proxy_url = f"http://{proxy_url}"
        proxy = urlparse(proxy_url)
        if proxy.scheme != "http" or not proxy.hostname:
            raise OSError("Only HTTP forward proxies are supported for SSO")
        return proxy

    @classmethod
    def connection_key(cls, parsed):
        origin = cls.origin(parsed)
        proxy = cls.proxy_for(parsed)
        if not proxy:
            return (*origin, None)
        return (
            *origin,
            (
                proxy.hostname.lower(),
                proxy.port or 80,
                proxy.username or "",
                proxy.password or "",
            ),
        )

    @staticmethod
    def proxy_authorization(proxy):
        if not proxy or not proxy[2]:
            return ""
        credentials = base64.b64encode(f"{proxy[2]}:{proxy[3]}".encode("utf-8")).decode("ascii")
        return f"Basic {credentials}"

    @classmethod
    def create_connection(cls, connection_key, timeout):
        scheme, host, port, proxy = connection_key
        if proxy:
            proxy_host, proxy_port, _, _ = proxy
            if scheme == "https":
                connection = http.client.HTTPSConnection(proxy_host, proxy_port, timeout=timeout)
                tunnel_headers = {}
                proxy_authorization = cls.proxy_authorization(proxy)
                if proxy_authorization:
                    tunnel_headers["Proxy-Authorization"] = proxy_authorization
                connection.set_tunnel(host, port, headers=tunnel_headers)
                return connection
            return http.client.HTTPConnection(proxy_host, proxy_port, timeout=timeout)
        connection_class = http.client.HTTPSConnection if scheme == "https" else http.client.HTTPConnection
        return connection_class(host, port, timeout=timeout)

    def _discard_locked(self, origin, connection):
        try:
            connection.close()
        finally:
            self._open_counts[origin] = max(0, self._open_counts.get(origin, 1) - 1)

    def _prune_locked(self, origin, now):
        retained = []
        for last_used, connection in self._idle.get(origin, []):
            if now - last_used > self.idle_seconds:
                self._discard_locked(origin, connection)
            else:
                retained.append((last_used, connection))
        self._idle[origin] = retained

    def acquire(self, parsed, timeout=SSO_HTTP_TIMEOUT_SECONDS):
        origin = self.connection_key(parsed)
        deadline = time.monotonic() + timeout
        with self._condition:
            while True:
                self._prune_locked(origin, time.monotonic())
                idle = self._idle.setdefault(origin, [])
                if idle:
                    return origin, idle.pop()[1]
                if self._open_counts.get(origin, 0) < self.max_per_origin:
                    self._open_counts[origin] = self._open_counts.get(origin, 0) + 1
                    break
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("SSO connection pool is busy")
                self._condition.wait(remaining)
        try:
            return origin, self.create_connection(origin, timeout)
        except Exception:
            with self._condition:
                self._open_counts[origin] = max(0, self._open_counts.get(origin, 1) - 1)
                self._condition.notify()
            raise

    def release(self, origin, connection, reusable):
        with self._condition:
            if reusable:
                self._idle.setdefault(origin, []).append((time.monotonic(), connection))
            else:
                self._discard_locked(origin, connection)
            self._condition.notify()

    def close_idle(self):
        with self._condition:
            for origin, entries in list(self._idle.items()):
                for _, connection in entries:
                    self._discard_locked(origin, connection)
            self._idle.clear()
            self._condition.notify_all()

    def stats(self):
        with self._condition:
            origins = set(self._open_counts) | set(self._idle)
            return {
                "max_per_origin": self.max_per_origin,
                "origins": len(origins),
                "open_connections": sum(self._open_counts.values()),
                "idle_connections": sum(len(entries) for entries in self._idle.values()),
            }


_SSO_HTTP_POOL = SsoHttpConnectionPool()
_DISCOVERY_CACHE = {}
_DISCOVERY_CACHE_LOCK = threading.Lock()


def _request_path(parsed):
    return urlunparse(("", "", parsed.path or "/", parsed.params, parsed.query, ""))


def _fetch_once(url, method, body, headers):
    parsed = urlparse(url)
    connection_key, connection = _SSO_HTTP_POOL.acquire(parsed)
    request_headers = dict(headers)
    proxy = connection_key[3]
    if proxy and parsed.scheme == "http":
        request_target = url
        request_headers.setdefault("Host", parsed.netloc)
        proxy_authorization = SsoHttpConnectionPool.proxy_authorization(proxy)
        if proxy_authorization:
            request_headers.setdefault("Proxy-Authorization", proxy_authorization)
    else:
        request_target = _request_path(parsed)
    reusable = False
    try:
        connection.request(method, request_target, body=body, headers=request_headers)
        response = connection.getresponse()
        payload = response.read(SSO_MAX_RESPONSE_BYTES + 1)
        reusable = not response.will_close and len(payload) <= SSO_MAX_RESPONSE_BYTES
        return response.status, dict(response.getheaders()), payload
    finally:
        _SSO_HTTP_POOL.release(connection_key, connection, reusable)


def fetch_json(url, method="GET", form=None, headers=None, purpose="企业身份平台", _redirects=0):
    validate_sso_url(url, f"{purpose}地址")
    method = method.upper()
    request_headers = {"Accept": "application/json", "User-Agent": "TeamLoop-OIDC/1.1", **(headers or {})}
    body = None
    if form is not None:
        body = urlencode(form).encode("utf-8")
        request_headers.setdefault("Content-Type", "application/x-www-form-urlencoded")
    request_headers.setdefault("Content-Length", str(len(body or b"")))

    attempts = 2 if method == "GET" else 1
    last_error = None
    for _ in range(attempts):
        try:
            status, response_headers, payload = _fetch_once(url, method, body, request_headers)
            break
        except TimeoutError as exc:
            last_error = exc
            break
        except (http.client.HTTPException, OSError) as exc:
            last_error = exc
    else:
        detail = re.sub(r"[\x00-\x1f\x7f]+", " ", str(last_error or "")).strip()[:160]
        suffix = f"：{detail}" if detail else ""
        raise AppError(502, f"无法连接{purpose}，请检查地址、DNS、代理和防火墙{suffix}") from last_error

    if status in SSO_REDIRECT_STATUSES:
        location = response_headers.get("Location") or response_headers.get("location")
        if not location or _redirects >= 3:
            raise AppError(502, f"{purpose}返回了无效或过多的重定向")
        redirected_url = urljoin(url, location)
        validate_sso_url(redirected_url, f"{purpose}重定向地址")
        if SsoHttpConnectionPool.origin(urlparse(redirected_url)) != SsoHttpConnectionPool.origin(urlparse(url)):
            raise AppError(502, f"{purpose}不允许跨域重定向")
        if method != "GET":
            raise AppError(502, f"{purpose}不允许重定向 POST 请求")
        return fetch_json(
            redirected_url,
            method=method,
            headers=headers,
            purpose=purpose,
            _redirects=_redirects + 1,
        )

    if status < 200 or status >= 300:
        detail = provider_error_message(payload[:16 * 1024])
        suffix = f"：{detail}" if detail else ""
        raise AppError(502, f"{purpose}请求失败（HTTP {status}）{suffix}")
    if len(payload) > SSO_MAX_RESPONSE_BYTES:
        raise AppError(502, f"{purpose}响应过大")
    try:
        data = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AppError(502, f"{purpose}返回的不是有效 JSON") from exc
    if not isinstance(data, dict):
        raise AppError(502, f"{purpose}响应必须是 JSON 对象")
    return data


def load_oidc_discovery(config, force_refresh=False):
    if config.get("mode") == "manual":
        endpoints = {
            "authorization_endpoint": config.get("authorization_url"),
            "token_endpoint": config.get("token_url"),
            "userinfo_endpoint": config.get("userinfo_url"),
        }
        for key, value in endpoints.items():
            if not value:
                raise AppError(400, "手动 OAuth2 模式必须填写授权、Token 和用户信息地址")
            validate_sso_url(value, key)
        endpoints["issuer"] = (config.get("issuer_url") or "").rstrip("/")
        endpoints["token_endpoint_auth_methods_supported"] = ["client_secret_post"]
        return endpoints

    issuer = validate_sso_url(config.get("issuer_url"), "OIDC Issuer 地址").rstrip("/")
    cache_key = issuer
    with _DISCOVERY_CACHE_LOCK:
        cached = _DISCOVERY_CACHE.get(cache_key)
        if not force_refresh and cached and cached[0] > time.monotonic():
            return dict(cached[1])
        discovery = fetch_json(f"{issuer}/.well-known/openid-configuration", purpose="OIDC Discovery")
        discovered_issuer = str(discovery.get("issuer") or "").rstrip("/")
        if discovered_issuer and discovered_issuer != issuer:
            raise AppError(502, "OIDC Discovery 返回的 Issuer 与系统配置不一致")
        for key in ("authorization_endpoint", "token_endpoint", "userinfo_endpoint"):
            if not discovery.get(key):
                raise AppError(502, f"OIDC Discovery 缺少 {key}")
            validate_sso_url(discovery[key], key)
        if SSO_DISCOVERY_CACHE_SECONDS:
            _DISCOVERY_CACHE[cache_key] = (
                time.monotonic() + SSO_DISCOVERY_CACHE_SECONDS,
                dict(discovery),
            )
        return discovery


def clear_sso_http_state():
    with _DISCOVERY_CACHE_LOCK:
        _DISCOVERY_CACHE.clear()
    _SSO_HTTP_POOL.close_idle()


def sso_http_pool_stats():
    stats = _SSO_HTTP_POOL.stats()
    with _DISCOVERY_CACHE_LOCK:
        stats["discovery_cache_entries"] = len(_DISCOVERY_CACHE)
    return stats
