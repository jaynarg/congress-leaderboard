"""Thin Congress.gov API client with throttling, retries, pagination, and a run deadline."""
import time
import requests

from . import config


class BudgetExhausted(Exception):
    """Raised when the run's time budget is used up; the runner saves progress and exits cleanly."""


class CongressAPI:
    def __init__(self, api_key, deadline, session=None):
        if not api_key:
            raise RuntimeError("CONGRESS_API_KEY is not set")
        self.api_key = api_key
        self.deadline = deadline
        self.session = session or requests.Session()
        self.min_interval = 3600.0 / config.MAX_CALLS_PER_HOUR
        self._last_call = 0.0
        self.calls = 0

    def get(self, path, params=None):
        """GET a path like '/bill/119/hr'. Returns parsed JSON, or None on 404."""
        url = path if path.startswith("http") else config.API_BASE + path
        query = {"format": "json", "api_key": self.api_key}
        query.update(params or {})

        for attempt in range(6):
            if time.time() > self.deadline:
                raise BudgetExhausted()
            wait = self.min_interval - (time.time() - self._last_call)
            if wait > 0:
                time.sleep(wait)
            self._last_call = time.time()
            self.calls += 1
            try:
                resp = self.session.get(url, params=query, timeout=60)
            except requests.RequestException as exc:
                print(f"  network error ({exc}); retrying")
                time.sleep(5 * 2 ** attempt)
                continue
            if resp.status_code == 404:
                return None
            if resp.status_code == 429:
                print("  rate limited (429); backing off")
                time.sleep(60 * (attempt + 1))
                continue
            if resp.status_code >= 500:
                print(f"  server error {resp.status_code}; retrying")
                time.sleep(5 * 2 ** attempt)
                continue
            resp.raise_for_status()
            return resp.json()
        raise RuntimeError(f"Giving up on {url} after repeated failures")

    def paginate(self, path, key, params=None, page_size=250):
        """Yield every item under `key` across all pages."""
        offset = 0
        while True:
            query = {"limit": page_size, "offset": offset}
            query.update(params or {})
            data = self.get(path, query)
            if not data:
                return
            items = data.get(key) or []
            yield from items
            total = (data.get("pagination") or {}).get("count")
            offset += page_size
            if not items or len(items) < page_size or (total is not None and offset >= total):
                return
