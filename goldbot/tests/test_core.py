import math
import os
import random
import sys
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import backtest  # noqa: E402
from indicators import adx, atr, ema, rsi  # noqa: E402
from risk import lot_size  # noqa: E402
from strategy import Params, Signal, evaluate, in_session, managed_stop  # noqa: E402

UTC = timezone.utc


def synth(n_m15, seed=1, start=datetime(2025, 1, 6, tzinfo=UTC), price=2000.0):
    """Trend almashinadigan sintetik oltin narxi (M15), hamda undan yig'ilgan H1."""
    rnd = random.Random(seed)
    m15, drift, t = [], 0.0, start
    for i in range(n_m15):
        if i % 400 == 0:
            drift = rnd.choice([-0.6, -0.3, 0.0, 0.3, 0.6])
        o = price
        moves = [rnd.gauss(drift / 4, 1.2) for _ in range(4)]
        path = [o]
        for m in moves:
            path.append(path[-1] + m)
        c = path[-1]
        m15.append({"time": t, "open": o, "high": max(path) + abs(rnd.gauss(0, 0.3)),
                    "low": min(path) - abs(rnd.gauss(0, 0.3)), "close": c, "spread": 0.25})
        price, t = c, t + timedelta(minutes=15)
    h1 = []
    for i in range(0, len(m15) - 3, 4):
        g = m15[i:i + 4]
        h1.append({"time": g[0]["time"], "open": g[0]["open"], "high": max(x["high"] for x in g),
                   "low": min(x["low"] for x in g), "close": g[-1]["close"], "spread": 0.25})
    return h1, m15


class Indicators(unittest.TestCase):
    def test_ema_matches_pandas(self):
        import pandas as pd
        vals = [random.Random(3).uniform(90, 110) for _ in range(300)]
        vals = [100 + math.sin(i / 7) * 5 + i * 0.05 for i in range(300)]
        ours = ema(vals, 21)
        s = pd.Series(vals)
        seed = s.iloc[:21].mean()
        ref = pd.concat([pd.Series([seed]), s.iloc[21:]]).ewm(span=21, adjust=False).mean().tolist()
        for a, b in zip(ours[20:], ref):
            self.assertAlmostEqual(a, b, places=8)
        self.assertIsNone(ours[19])

    def test_rsi_extremes_and_range(self):
        up = [100 + i for i in range(50)]
        self.assertEqual(rsi(up)[-1], 100.0)
        down = [100 - i for i in range(50)]
        self.assertAlmostEqual(rsi(down)[-1], 0.0)
        _, m15 = synth(500)
        r = [x for x in rsi([c["close"] for c in m15]) if x is not None]
        self.assertTrue(all(0 <= x <= 100 for x in r))

    def test_atr_constant_range(self):
        h = [11.0] * 40
        lo = [9.0] * 40
        c = [10.0] * 40
        self.assertAlmostEqual(atr(h, lo, c, 14)[-1], 2.0)

    def test_adx_trend_vs_flat(self):
        n = 200
        trend_h = [100 + i + 0.5 for i in range(n)]
        trend_l = [100 + i - 0.5 for i in range(n)]
        trend_c = [100 + i for i in range(n)]
        self.assertGreater(adx(trend_h, trend_l, trend_c)[-1], 60)
        flat_c = [100 + (1 if i % 2 else -1) for i in range(n)]
        flat_h = [c + 0.5 for c in flat_c]
        flat_l = [c - 0.5 for c in flat_c]
        self.assertLess(adx(flat_h, flat_l, flat_c)[-1], 20)


class Risk(unittest.TestCase):
    def test_exact_risk(self):
        # 10 000$ hisob, 5% = 500$, stop 5$ uzoqda, 1 lot = 100 unsiya -> 1 lotda 500$ -> 1.00 lot
        vol, money, _ = lot_size(10000, 5, 5.0, 100, 0.01, 50, 0.01)
        self.assertEqual(vol, 1.0)
        self.assertAlmostEqual(money, 500.0)

    def test_rounds_down(self):
        vol, money, _ = lot_size(1000, 5, 7.0, 100, 0.01, 50, 0.01)  # 50/700 = 0.0714 -> 0.07
        self.assertEqual(vol, 0.07)
        self.assertLessEqual(money, 50.0)

    def test_small_account_refuses_oversized_min_lot(self):
        vol, need, note = lot_size(100, 2, 10.0, 100, 0.01, 50, 0.01)  # min lot = 10$ xavf, ko'zlangan 2$
        self.assertEqual(vol, 0.0)
        self.assertIn("kichik", note)

    def test_min_lot_within_tolerance(self):
        vol, _, _ = lot_size(150, 5, 10.0, 100, 0.01, 50, 0.01)  # 7.5$ ko'zlangan, min lot 10$ (<= 1.5x)
        self.assertEqual(vol, 0.01)

    def test_max_cap(self):
        vol, _, _ = lot_size(10_000_000, 10, 1.0, 100, 0.01, 50, 0.01)
        self.assertEqual(vol, 50)


class Strategy(unittest.TestCase):
    def test_session(self):
        p = Params()
        self.assertTrue(in_session(datetime(2026, 10, 21, 10, 0, tzinfo=UTC), p))   # chorshanba
        self.assertFalse(in_session(datetime(2026, 10, 21, 3, 0, tzinfo=UTC), p))
        self.assertFalse(in_session(datetime(2026, 10, 23, 19, 0, tzinfo=UTC), p))  # juma kech
        self.assertFalse(in_session(datetime(2026, 10, 24, 10, 0, tzinfo=UTC), p))  # shanba

    def test_managed_stop(self):
        # sotib olish: kirish 100, TP 110 (RR 2 -> R=5)
        self.assertIsNone(managed_stop("buy", 100, 95, 110, 104))
        self.assertAlmostEqual(managed_stop("buy", 100, 95, 110, 105), 100.5)
        self.assertAlmostEqual(managed_stop("buy", 100, 100.5, 110, 107.5), 102.5)
        self.assertIsNone(managed_stop("buy", 100, 102.5, 110, 108))  # allaqachon qulflangan
        # sotish: kirish 100, TP 90
        self.assertAlmostEqual(managed_stop("sell", 100, 105, 90, 95), 99.5)
        self.assertIsNone(managed_stop("sell", 100, 99.5, 90, 96))

    def test_signal_geometry_on_synthetic(self):
        h1, m15 = synth(6000, seed=7)
        found = 0
        for i in range(400, len(m15)):
            t_close = m15[i]["time"] + timedelta(minutes=15)
            hh = [x for x in h1 if x["time"] + timedelta(hours=1) <= t_close][-500:]
            s = evaluate(hh, m15[i - 299:i + 1])
            if s is None:
                continue
            found += 1
            self.assertIsInstance(s, Signal)
            if s.side == "buy":
                self.assertLess(s.sl, s.entry)
                self.assertGreater(s.tp, s.entry)
            else:
                self.assertGreater(s.sl, s.entry)
                self.assertLess(s.tp, s.entry)
            self.assertAlmostEqual(abs(s.tp - s.entry), 2 * abs(s.entry - s.sl), places=6)
            self.assertGreaterEqual(abs(s.entry - s.sl), s.atr * 1.0 - 1e-9)
            self.assertLessEqual(abs(s.entry - s.sl), s.atr * 2.5 + 1e-9)
            if found > 40:
                break
        self.assertGreater(found, 0, "sintetik trendlarda birorta signal topilmadi")


class Backtest(unittest.TestCase):
    def test_runs_and_is_consistent(self):
        h1, m15 = synth(20000, seed=11)
        res = backtest.run(h1, m15)
        self.assertGreater(len(res.trades), 5)
        prev_exit = None
        for tr in res.trades:
            self.assertIsNotNone(tr.exit_time)
            self.assertGreaterEqual(tr.exit_time, tr.open_time)
            if prev_exit is not None:
                self.assertGreaterEqual(tr.open_time, prev_exit)  # bir vaqtda bitta savdo
            prev_exit = tr.exit_time
            self.assertLessEqual(tr.r, 2.0 + 1e-6)              # TP dan ko'p yutib bo'lmaydi
            if tr.why == "stop":
                self.assertGreaterEqual(tr.r, -1.0 - 1e-6)      # oddiy stopda 1R dan ko'p yo'qotilmaydi
        s = backtest.summary(res)
        self.assertEqual(s["trades"], len(res.trades))
        text = backtest.format_summary(s)
        self.assertIn("Sinov natijasi", text)
        self.assertIn("10%", text)

    def test_daily_consecutive_loss_limit(self):
        h1, m15 = synth(20000, seed=5)
        res = backtest.run(h1, m15, Params(), backtest.Limits(max_trades_per_day=10, max_consec_losses_per_day=1))
        by_day = {}
        for tr in res.trades:
            by_day.setdefault(tr.open_time.date(), []).append(tr)
        for day, trs in by_day.items():
            closed_today = [t for t in trs if t.exit_time.date() == day]
            for a, b in zip(closed_today, closed_today[1:]):
                self.assertGreaterEqual(a.r, 0, f"{day}: yutqazishdan keyin savdo ochilmasligi kerak edi")

    def test_equity_curve(self):
        eq, dd, _ = backtest.equity_curve([-1] * 7, 10)
        self.assertAlmostEqual(eq, 100 * 0.9 ** 7)
        self.assertAlmostEqual(dd, 1 - 0.9 ** 7)


if __name__ == "__main__":
    unittest.main()
