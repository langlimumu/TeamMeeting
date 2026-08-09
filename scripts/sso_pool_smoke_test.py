import concurrent.futures
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class IdentityProviderHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    lock = threading.Lock()
    connection_count = 0
    active_connections = 0
    peak_connections = 0
    discovery_requests = 0

    def setup(self):
        super().setup()
        with self.lock:
            type(self).connection_count += 1
            type(self).active_connections += 1
            type(self).peak_connections = max(type(self).peak_connections, type(self).active_connections)

    def finish(self):
        try:
            super().finish()
        finally:
            with self.lock:
                type(self).active_connections -= 1

    def log_message(self, *_args):
        return

    def do_GET(self):
        if self.path == "/.well-known/openid-configuration":
            with self.lock:
                type(self).discovery_requests += 1
            origin = f"http://127.0.0.1:{self.server.server_port}"
            payload = {
                "issuer": origin,
                "authorization_endpoint": f"{origin}/authorize",
                "token_endpoint": f"{origin}/token",
                "userinfo_endpoint": f"{origin}/userinfo",
            }
        elif self.path == "/userinfo":
            time.sleep(0.03)
            payload = {"sub": "pool-user", "preferred_username": "E90001", "name": "Pool User"}
        else:
            self.send_error(404)
            return
        body = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        self.wfile.write(body)
        self.wfile.flush()


class ForwardProxyHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    requested_targets = []

    def log_message(self, *_args):
        return

    def do_GET(self):
        type(self).requested_targets.append(self.path)
        body = json.dumps({"sub": "proxied-user"}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        self.wfile.write(body)
        self.wfile.flush()


def main():
    os.environ["TEAM_LOOP_SSO_HTTP_POOL_SIZE"] = "4"
    os.environ["TEAM_LOOP_SSO_DISCOVERY_CACHE_SECONDS"] = "300"
    sys.path.insert(0, str(ROOT))
    import server as app
    import team_loop.sso_http as sso_http

    provider = ThreadingHTTPServer(("127.0.0.1", 0), IdentityProviderHandler)
    thread = threading.Thread(target=provider.serve_forever, daemon=True)
    thread.start()
    issuer = f"http://127.0.0.1:{provider.server_port}"
    config = {"mode": "discovery", "issuer_url": issuer}
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
            discoveries = list(executor.map(lambda _: app.load_oidc_discovery(config), range(20)))
        if len(discoveries) != 20 or IdentityProviderHandler.discovery_requests != 1:
            raise RuntimeError(f"Discovery cache stampede detected: {IdentityProviderHandler.discovery_requests}")

        with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
            claims = list(executor.map(
                lambda _: app.fetch_json(f"{issuer}/userinfo", purpose="Pool smoke UserInfo"),
                range(20),
            ))
        if len(claims) != 20 or any(item.get("sub") != "pool-user" for item in claims):
            raise RuntimeError("Pooled UserInfo responses are incomplete")
        stats = app.sso_http_pool_stats()
        if stats["max_per_origin"] != 4 or IdentityProviderHandler.peak_connections > 4:
            raise RuntimeError({"pool": stats, "peak_connections": IdentityProviderHandler.peak_connections})

        proxy = ThreadingHTTPServer(("127.0.0.1", 0), ForwardProxyHandler)
        proxy_thread = threading.Thread(target=proxy.serve_forever, daemon=True)
        proxy_thread.start()
        original_proxy = os.environ.get("HTTP_PROXY")
        original_no_proxy = os.environ.get("NO_PROXY")
        original_proxy_bypass = sso_http.proxy_bypass
        try:
            os.environ["HTTP_PROXY"] = f"http://127.0.0.1:{proxy.server_port}"
            os.environ["NO_PROXY"] = ""
            sso_http.proxy_bypass = lambda _host: False
            app.clear_sso_http_state()
            target_url = "http://localhost:65530/userinfo"
            proxied = app.fetch_json(target_url, purpose="Proxy smoke UserInfo")
            if proxied.get("sub") != "proxied-user" or ForwardProxyHandler.requested_targets != [target_url]:
                raise RuntimeError({"proxied": proxied, "targets": ForwardProxyHandler.requested_targets})
        finally:
            sso_http.proxy_bypass = original_proxy_bypass
            if original_proxy is None:
                os.environ.pop("HTTP_PROXY", None)
            else:
                os.environ["HTTP_PROXY"] = original_proxy
            if original_no_proxy is None:
                os.environ.pop("NO_PROXY", None)
            else:
                os.environ["NO_PROXY"] = original_no_proxy
            app.clear_sso_http_state()
            proxy.shutdown()
            proxy_thread.join(timeout=5)
            proxy.server_close()
        print(json.dumps({
            "status": "ok",
            "requests": 40,
            "discovery_requests": IdentityProviderHandler.discovery_requests,
            "connections_created": IdentityProviderHandler.connection_count,
            "peak_connections": IdentityProviderHandler.peak_connections,
            "http_proxy": True,
            "pool": stats,
        }, ensure_ascii=False))
    finally:
        app.clear_sso_http_state()
        provider.shutdown()
        thread.join(timeout=5)
        provider.server_close()


if __name__ == "__main__":
    main()
