"""Bot siklini soxta broker (FakeApi) va soxta Telegram bilan sinash."""
import os
import sys
import unittest
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bot as botmod  # noqa: E402
from metaapi import MetaApiError, parse_time  # noqa: E402
from strategy import Signal  # noqa: E402

UTC = timezone.utc
MAGIC = 770077


class FakeTg:
    def __init__(self):
        self.sent = []

    def send(self, text, keyboard=True):
        self.sent.append(text)

    def updates(self):
        return []


class FakeApi:
    def __init__(self):
        self.region = "london"
        self.trades = []
        self.pos = []
        self.deals = []
        self.balance = 10000.0
        self.equity = 10000.0
        self.reject = None

    def ensure_connected(self):
        return {"server": "XMGlobal-MT5 6", "login": 123}

    def symbols(self):
        return ["EURUSD", "GOLDEUR", "GOLD", "SILVER"]

    def spec(self, s):
        return {"symbol": s, "digits": 2, "contractSize": 100, "minVolume": 0.01, "maxVolume": 50,
                "volumeStep": 0.01, "stopsLevel": 0}

    def set_point(self, p):
        self.point = p

    def account_info(self):
        return {"balance": self.balance, "equity": self.equity, "currency": "USD"}

    def positions(self):
        return list(self.pos)

    def price(self, s):
        return {"bid": 2000.0, "ask": 2000.3}

    def candles(self, *a, **k):
        return []

    def trade(self, body):
        if self.reject:
            raise MetaApiError(self.reject)
        self.trades.append(body)
        return {"stringCode": "TRADE_RETCODE_DONE", "positionId": "P1", "orderId": "O1"}

    def deals_between(self, a, b):
        return [d for d in self.deals if a <= parse_time(d["time"]) <= b]

    def deals_for_position(self, pid):
        return [d for d in self.deals if d["positionId"] == pid]


def make(auto_start=True, **env):
    os.environ.update({"RISK_PERCENT": "5", "AUTO_START": "1" if auto_start else "0", **env})
    cfg = botmod.Config()
    api, tg = FakeApi(), FakeTg()
    b = botmod.Bot(cfg, api, tg)
    b.setup()
    return b, api, tg


def add_closed(api, pid, profit, t):
    api.deals += [
        {"positionId": pid, "magic": MAGIC, "entryType": "DEAL_ENTRY_IN", "time": t, "profit": 0},
        {"positionId": pid, "magic": 0, "entryType": "DEAL_ENTRY_OUT", "time": t, "profit": profit,
         "commission": 0, "swap": 0},
    ]


WED_10 = datetime(2026, 10, 21, 10, 0, 5, tzinfo=UTC)


class BotTests(unittest.TestCase):
    def setUp(self):
        self._sleep = botmod.time.sleep
        botmod.time.sleep = lambda s: None
        self._orig = botmod.evaluate
        botmod.evaluate = lambda h1, m15, p: Signal("buy", 2000.0, 1994.0, 2012.0, 4.0, "test")

    def tearDown(self):
        botmod.evaluate = self._orig
        botmod.time.sleep = self._sleep

    def test_picks_gold_symbol(self):
        b, _, tg = make()
        self.assertEqual(b.symbol, "GOLD")
        self.assertIn("ulandi", tg.sent[0])
        self.assertEqual(botmod.find_symbol(["XAUUSD.m", "XAUEUR"]), "XAUUSD.m")
        self.assertEqual(botmod.find_symbol(["XAUUSD", "GOLD"]), "XAUUSD")
        self.assertIsNone(botmod.find_symbol(["EURUSD"]))

    def test_opens_trade_with_correct_size(self):
        b, api, tg = make()
        b.tick(WED_10)
        self.assertEqual(len(api.trades), 1)
        t = api.trades[0]
        self.assertEqual(t["actionType"], "ORDER_TYPE_BUY")
        self.assertEqual(t["symbol"], "GOLD")
        self.assertEqual(t["magic"], MAGIC)
        self.assertEqual(t["stopLoss"], 1994.0)
        self.assertEqual(t["takeProfit"], 2012.9)  # haqiqiy kirish 2000.3 + 2 × 6.3
        # 5% * 10000 = 500$, haqiqiy kirish ask 2000.3 -> stop masofasi 6.3$, 1 lot = 630$ -> 0.79 lot
        self.assertEqual(t["volume"], 0.79)
        self.assertIn("SOTIB OLDIM", tg.sent[-1])
        b.tick(WED_10)  # xuddi shu sham — ikkinchi marta kirmaydi
        self.assertEqual(len(api.trades), 1)

    def test_paused_does_not_trade(self):
        b, api, _ = make(auto_start=False)
        b.tick(WED_10)
        self.assertEqual(api.trades, [])
        b.handle("▶️ Boshlash")
        b.last_bar_eval = None
        b.tick(WED_10)
        self.assertEqual(len(api.trades), 1)

    def test_outside_session(self):
        b, api, _ = make()
        b.tick(datetime(2026, 10, 21, 3, 0, 5, tzinfo=UTC))
        self.assertEqual(api.trades, [])

    def test_stops_after_consecutive_losses(self):
        b, api, tg = make()
        for i in range(5):
            add_closed(api, f"L{i}", -100, f"2026-10-21T{i + 5:02d}:00:00.000Z")
        b.tick(WED_10)
        self.assertEqual(api.trades, [])
        self.assertIn("ketma-ket 5", b.status_line)

    def test_win_resets_streak(self):
        b, api, _ = make()
        for i in range(4):
            add_closed(api, f"L{i}", -100, f"2026-10-21T0{i + 5}:00:00.000Z")
        add_closed(api, "W", 200, "2026-10-21T09:00:00.000Z")
        add_closed(api, "L9", -100, "2026-10-21T09:30:00.000Z")
        b.tick(WED_10)
        self.assertEqual(len(api.trades), 1)

    def test_yesterdays_losses_do_not_count(self):
        b, api, _ = make()
        for i in range(5):
            add_closed(api, f"Y{i}", -100, f"2026-10-20T1{i}:00:00.000Z")
        b.tick(WED_10)
        self.assertEqual(len(api.trades), 1)

    def test_breakeven_and_close_notice(self):
        b, api, tg = make()
        api.pos = [{"id": "P1", "symbol": "GOLD", "magic": MAGIC, "type": "POSITION_TYPE_BUY", "volume": 0.5,
                    "openPrice": 2000.0, "stopLoss": 1994.0, "takeProfit": 2012.0, "currentPrice": 2006.5,
                    "profit": 325}]
        b.tick(WED_10)
        mod = [t for t in api.trades if t["actionType"] == "POSITION_MODIFY"]
        self.assertEqual(len(mod), 1)
        self.assertAlmostEqual(mod[0]["stopLoss"], 2000.6)
        self.assertEqual(mod[0]["takeProfit"], 2012.0)
        self.assertFalse(any(t["actionType"].startswith("ORDER_TYPE") for t in api.trades))  # ochiq bor — yangi yo'q
        api.pos = []
        add_closed(api, "P1", 600, "2026-10-21T10:10:00.000Z")
        b.tick(datetime(2026, 10, 21, 10, 15, 5, tzinfo=UTC))
        self.assertFalse(any("Savdo yopildi" in s for s in tg.sent))  # bir marta yo'q — hali ishonmaymiz
        b.tick(datetime(2026, 10, 21, 10, 15, 20, tzinfo=UTC))
        self.assertTrue(any("Savdo yopildi" in s and "+600.00" in s for s in tg.sent))

    def test_ignores_foreign_positions(self):
        b, api, _ = make()
        api.pos = [{"id": "X", "symbol": "GOLD", "magic": 0, "type": "POSITION_TYPE_BUY", "volume": 1,
                    "openPrice": 2000.0, "stopLoss": 1990, "takeProfit": 2020, "currentPrice": 2019}]
        b.tick(WED_10)
        self.assertFalse(any(t["actionType"] == "POSITION_MODIFY" for t in api.trades))
        self.assertEqual(len([t for t in api.trades if t["actionType"] == "ORDER_TYPE_BUY"]), 1)

    def test_drawdown_pauses(self):
        b, api, tg = make(MAX_DRAWDOWN_PCT="40")
        api.equity = 5900
        b.tick(WED_10)
        self.assertTrue(b.paused)
        self.assertEqual(api.trades, [])
        self.assertTrue(any("pasaydi" in s for s in tg.sent))

    def test_friday_close(self):
        b, api, _ = make()
        api.pos = [{"id": "P1", "symbol": "GOLD", "magic": MAGIC, "type": "POSITION_TYPE_BUY", "volume": 0.5,
                    "openPrice": 2000.0, "stopLoss": 1994.0, "takeProfit": 2012.0, "currentPrice": 2001}]
        b.tick(datetime(2026, 10, 23, 20, 31, tzinfo=UTC))
        self.assertEqual(api.trades[-1], {"actionType": "POSITION_CLOSE_ID", "positionId": "P1"})

    def test_broker_reject_is_reported(self):
        b, api, tg = make()
        api.reject = "broker rad etdi: TRADE_RETCODE_NO_MONEY"
        b.tick(WED_10)
        self.assertIn("rad etdi", tg.sent[-1])

    def test_modify_not_repeated(self):
        b, api, tg = make()
        pos = {"id": "P1", "symbol": "GOLD", "magic": MAGIC, "type": "POSITION_TYPE_SELL", "volume": 0.5,
               "openPrice": 2000.0, "stopLoss": 2006.0, "takeProfit": 1988.0, "currentPrice": 1993.5}
        api.pos = [pos]
        b.tick(WED_10)
        b.tick(WED_10)  # broker ro'yxati hali eski stopni ko'rsatyapti
        mods = [t for t in api.trades if t["actionType"] == "POSITION_MODIFY"]
        self.assertEqual(len(mods), 1)
        self.assertAlmostEqual(mods[0]["stopLoss"], 1999.4)

    def test_recent_entry_blocks_second_instance(self):
        b, api, _ = make()
        api.deals.append({"positionId": "Z", "magic": MAGIC, "entryType": "DEAL_ENTRY_IN",
                          "time": "2026-10-21T09:55:00.000Z"})
        b.tick(WED_10)
        self.assertEqual(api.trades, [])
        self.assertIn("15 daqiqada", b.status_line)

    def test_timeout_but_position_opened(self):
        b, api, tg = make()

        def flaky(body):
            api.pos = [{"id": "P9", "symbol": "GOLD", "magic": MAGIC, "type": "POSITION_TYPE_BUY",
                        "volume": 0.79, "openPrice": 2000.3, "stopLoss": 1994, "takeProfit": 2012.9,
                        "currentPrice": 2000.2}]
            raise MetaApiError("tarmoq xatosi: Read timed out <urllib3 object>")
        api.trade = flaky
        b.tick(WED_10)
        self.assertFalse(any("rad etdi" in s for s in tg.sent))
        self.assertIn("SOTIB OLDIM", tg.sent[-1])

    def test_error_text_is_escaped(self):
        self.assertEqual(botmod.esc("<a & b>"), "&lt;a &amp; b&gt;")

    def test_commands(self):
        b, api, tg = make()
        b.handle("risk 10")
        self.assertEqual(b.risk, 10)
        b.handle("risk 25")
        self.assertEqual(b.risk, 10)
        b.handle("seriya 3")
        self.assertEqual(b.max_consec, 3)
        b.handle("⏸ To'xtatish")
        self.assertTrue(b.paused)
        b.handle("📊 Holat")
        self.assertIn("PAUZA", tg.sent[-1])
        api.pos = [{"id": "P1", "symbol": "GOLD", "magic": MAGIC, "type": "POSITION_TYPE_SELL", "volume": 0.1,
                    "openPrice": 2000.0, "stopLoss": 2006, "takeProfit": 1988, "currentPrice": 1999, "profit": 10}]
        b.handle("❌ Hammasini yopish")
        self.assertFalse(any(t["actionType"] == "POSITION_CLOSE_ID" for t in api.trades))
        b.handle("ha yopish")
        self.assertTrue(any(t["actionType"] == "POSITION_CLOSE_ID" for t in api.trades))
        b.handle("📜 Tarix")
        b.handle("salom")
        self.assertIn("tugmalardan", tg.sent[-1])


if __name__ == "__main__":
    unittest.main()
