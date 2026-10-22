"""MetaApi REST mijoz (MT5 hisobiga bulut orqali ulanish). Faqat `requests` ishlatiladi."""
import logging
import time
from urllib.parse import quote
from datetime import datetime, timedelta, timezone

import requests

log = logging.getLogger("metaapi")
PROVISIONING = "https://mt-provisioning-api-v1.agiliumtrade.agiliumtrade.ai"
TF_DELTA = {"15m": timedelta(minutes=15), "1h": timedelta(hours=1)}


class MetaApiError(Exception):
    pass


def parse_time(s):
    if isinstance(s, datetime):
        return s if s.tzinfo else s.replace(tzinfo=timezone.utc)
    s = s.replace("Z", "+00:00")
    if "." in s:  # mikrosoniyani 6 xonagacha qisqartiramiz (fromisoformat talabi)
        head, rest = s.split(".", 1)
        frac = rest[:len(rest) - len(rest.lstrip("0123456789"))]  # faqat boshidagi raqamlar
        tz = rest[len(frac):]
        s = f"{head}.{frac[:6].ljust(6, '0')}{tz}"
    dt = datetime.fromisoformat(s)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def iso(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


class MetaApi:
    def __init__(self, token, account_id, timeout=25):
        self.token, self.account_id, self.timeout = token, account_id, timeout
        self.session = requests.Session()
        self.session.headers.update({"auth-token": token, "Accept": "application/json"})
        self.region = None
        self._point = None

    # --- past daraja ---
    def _req(self, method, url, retries=2, **kw):
        last = None
        for attempt in range(retries):
            try:
                r = self.session.request(method, url, timeout=self.timeout, **kw)
            except requests.RequestException as e:
                last = f"tarmoq xatosi: {e}"
            else:
                if r.status_code < 300:
                    return r.json() if r.content else None
                body = r.text[:300]
                last = f"HTTP {r.status_code}: {body}"
                if r.status_code in (400, 401, 403, 404):
                    break  # takrorlash foyda bermaydi
            time.sleep(2 * (attempt + 1))
        raise MetaApiError(last)

    @property
    def _client(self):
        return f"https://mt-client-api-v1.{self.region}.agiliumtrade.ai/users/current/accounts/{self.account_id}"

    @property
    def _market(self):
        return (f"https://mt-market-data-client-api-v1.{self.region}.agiliumtrade.ai"
                f"/users/current/accounts/{self.account_id}")

    # --- hisob holati ---
    def account(self):
        return self._req("GET", f"{PROVISIONING}/users/current/accounts/{self.account_id}")

    def ensure_connected(self, wait_s=300):
        acc = self.account()
        self.region = acc.get("region") or "new-york"
        if acc.get("state") in ("UNDEPLOYED", "UNDEPLOYING"):
            log.info("MetaApi hisobi o'chirilgan — yoqyapman (deploy)")
            self._req("POST", f"{PROVISIONING}/users/current/accounts/{self.account_id}/deploy")
        deadline = time.time() + wait_s
        while time.time() < deadline:
            acc = self.account()
            if acc.get("state") == "DEPLOYED" and acc.get("connectionStatus") == "CONNECTED":
                return acc
            time.sleep(10)
        raise MetaApiError(f"hisob ulanmadi: holat={acc.get('state')}, aloqa={acc.get('connectionStatus')}")

    def account_info(self):
        return self._req("GET", f"{self._client}/account-information")

    def positions(self):
        return self._req("GET", f"{self._client}/positions") or []

    def symbols(self):
        return self._req("GET", f"{self._client}/symbols") or []

    def spec(self, symbol):
        return self._req("GET", f"{self._client}/symbols/{quote(symbol, safe='')}/specification")

    def price(self, symbol):
        return self._req("GET", f"{self._client}/symbols/{quote(symbol, safe='')}/current-price")

    def trade(self, body):
        res = self._req("POST", f"{self._client}/trade", retries=1, json=body)
        code = (res or {}).get("stringCode", "")
        if code not in ("TRADE_RETCODE_DONE", "TRADE_RETCODE_PLACED", "TRADE_RETCODE_DONE_PARTIAL"):
            raise MetaApiError(f"broker rad etdi: {code} {(res or {}).get('message', '')}")
        return res

    def deals_between(self, start, end):
        return self._req("GET", f"{self._client}/history-deals/time/{iso(start)}/{iso(end)}") or []

    def deals_for_position(self, position_id):
        return self._req("GET", f"{self._client}/history-deals/position/{position_id}") or []

    # --- narx tarixi ---
    def candles(self, symbol, tf, limit=500, before=None):
        """Eskidan yangiga tartiblangan shamlar (oxirgisi tugamagan bo'lishi mumkin)."""
        out = {}
        start = before
        while len(out) < limit:
            n = min(1000, limit - len(out))
            params = {"limit": n}
            if start is not None:
                params["startTime"] = iso(start)
            batch = self._req("GET", f"{self._market}/historical-market-data/symbols/{quote(symbol, safe='')}"
                                     f"/timeframes/{tf}/candles", params=params) or []
            if not batch:
                break
            new = 0
            for c in batch:
                t = parse_time(c["time"])
                if t not in out:
                    out[t] = c
                    new += 1
            if new == 0:
                break
            start = min(out) - TF_DELTA.get(tf, timedelta(minutes=1))
            if len(batch) < n:
                break
        return [self._norm(out[t], t) for t in sorted(out)][-limit:]

    def set_point(self, point):
        self._point = point

    def _norm(self, c, t):
        spread_pts = c.get("spread") or 0
        return {"time": t, "open": float(c["open"]), "high": float(c["high"]), "low": float(c["low"]),
                "close": float(c["close"]), "spread": float(spread_pts) * (self._point or 0.0)}


def drop_unclosed(candles, tf, now=None):
    now = now or datetime.now(timezone.utc)
    d = TF_DELTA[tf]
    return [c for c in candles if c["time"] + d <= now]
