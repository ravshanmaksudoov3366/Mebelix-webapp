import os, sys, unittest
from datetime import datetime, timedelta, timezone
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from metaapi import MetaApi, drop_unclosed, iso, parse_time  # noqa: E402

UTC = timezone.utc
END = datetime(2026, 10, 21, 12, 0, tzinfo=UTC)
ALL = [{"time": iso(END - timedelta(minutes=15 * i)), "open": 1, "high": 2, "low": 0.5, "close": 1.5,
        "spread": 30} for i in range(2500)]  # eng yangisi birinchi


class Paging(unittest.TestCase):
    def test_candles_paging(self):
        api = MetaApi("t", "acc")
        api.region = "london"
        api.set_point(0.01)
        calls = []

        def fake_req(method, url, **kw):
            calls.append(kw["params"])
            lim = kw["params"]["limit"]
            st = parse_time(kw["params"]["startTime"]) if "startTime" in kw["params"] else END
            older = [c for c in ALL if parse_time(c["time"]) <= st][:lim]
            return list(reversed(older))  # tartib qanday bo'lmasin — saralanadi
        api._req = fake_req
        out = api.candles("GOLD", "15m", 2200)
        self.assertEqual(len(out), 2200)
        self.assertEqual(len(calls), 3)
        times = [c["time"] for c in out]
        self.assertEqual(times, sorted(times))
        self.assertEqual(len(set(times)), len(times))
        self.assertEqual(out[-1]["time"], END)
        self.assertAlmostEqual(out[0]["spread"], 0.30)
        self.assertIn("london", "https://mt-market-data-client-api-v1.london.agiliumtrade.ai")
        closed = drop_unclosed(out, "15m", now=END + timedelta(minutes=5))
        self.assertEqual(closed[-1]["time"], END - timedelta(minutes=15))

    def test_runs_out_of_history(self):
        api = MetaApi("t", "acc"); api.region = "x"
        api._req = lambda m, u, **kw: [c for c in ALL if parse_time(c["time"]) <= parse_time(kw["params"].get("startTime", iso(END)))][:kw["params"]["limit"]]
        self.assertEqual(len(api.candles("GOLD", "15m", 5000)), 2500)


class Quoting(unittest.TestCase):
    def test_symbol_with_hash_is_escaped(self):
        api = MetaApi("t", "acc"); api.region = "london"
        urls = []
        api._req = lambda m, u, **kw: urls.append(u) or {}
        api.spec("GOLD#"); api.price("GOLD#")
        self.assertTrue(all("GOLD%23" in u for u in urls), urls)


if __name__ == "__main__":
    unittest.main()
