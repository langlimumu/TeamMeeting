import threading
from http.server import ThreadingHTTPServer

from .config import HTTP_MAX_WORKERS, HTTP_REQUEST_QUEUE_SIZE


class BoundedThreadingHTTPServer(ThreadingHTTPServer):
    """Thread-per-request server with a bounded number of active workers."""

    daemon_threads = True
    allow_reuse_address = True
    request_queue_size = HTTP_REQUEST_QUEUE_SIZE

    def __init__(self, server_address, request_handler_class, max_workers=None):
        self.max_workers = max_workers or HTTP_MAX_WORKERS
        self._worker_slots = threading.BoundedSemaphore(self.max_workers)
        super().__init__(server_address, request_handler_class)

    def process_request(self, request, client_address):
        self._worker_slots.acquire()
        try:
            super().process_request(request, client_address)
        except Exception:
            self._worker_slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._worker_slots.release()
