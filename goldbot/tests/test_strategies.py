import os
import sys
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import backtest  # noqa: E402
from strategy import Params, Signal, evaluate, evaluate_asia, evaluate_squeeze, score  # noqa: E402
from tests.test_core import synth  # noqa: E402

UTC = timezone.utc
DAY = datetime(2026, 10, 21, tzinfo=UTC)  # chorshanba


def h1_trend(direction=1, n=260, end=DAY):
    out = []
    t = end - timedelta(hours=n)
    for i in range(n):
        base = 2000 + direction * i * 2.0
        wob = 0.6 if i % 2 else -0.6
        o, c = base - direction * 0.8 + wob, base + direction * 0.8 + wob
        out.append({"time": t, "open": o, "high": max(o, c) + 0.5, "low": min(o, c) - 0.5, "close": c})
        t += timedelta(hours=1)
    return out


def m15_flat(start, n, price, amp):
    out, t = [], start
    for i in range(n):
        o = price + (amp if i % 2 else -amp) * 0.5
        c = price - (amp if i % 2 else -amp) * 0.5
        out.append({"time": t, "open": o, "high": max(o, c) + amp * 0.3, "low": min(o, c) - amp * 0.3,
                    "close": c, "spread": 0.2})
        t += timedelta(minutes=15)
    return out


class Asia(unittest.TestCase):
    def setUp(self):
        self.h1 = h1_trend(+1)
        self.price = self.h1[-1]["close"]
        # kechagi faol savdo (ATR uchun) + bugun 00:00–07:00 tor diapazon
        self.m15 = m15_flat(DAY - timedelta(hours=30), 120, self.price, 3.0) + m15_flat(DAY, 28, self.price, 3.0)

    def bar(self, t, o, c, hi=None, lo=None):
        return {"time": t, "open": o, "close": c, "high": hi or max(o, c) + 0.2, "low": lo or min(o, c) - 0.2,
                "spread": 0.2}

    def test_breakout_up_in_uptrend(self):
        hi_r = max(x["high"] for x in self.m15[-28:])
        brk = self.bar(DAY + timedelta(hours=7), self.price, hi_r + 3.0)
        s = evaluate_asia(self.h1, self.m15 + [brk])
        self.assertIsNotNone(s)
        self.assertEqual((s.side, s.name), ("buy", "B"))
        lo_r = min(x["low"] for x in self.m15[-28:])
        self.assertLess(s.sl, (hi_r + lo_r) / 2)          # stop diapazon o'rtasidan pastda
        self.assertAlmostEqual(s.tp - s.entry, 2 * (s.entry - s.sl))

    def test_no_trade_against_trend(self):
        lo_r = min(x["low"] for x in self.m15[-28:])
        brk = self.bar(DAY + timedelta(hours=7), self.price, lo_r - 3.0)
        self.assertIsNone(evaluate_asia(self.h1, self.m15 + [brk]))

    def test_no_trade_outside_window(self):
        hi_r = max(x["high"] for x in self.m15[-28:])
        extra = m15_flat(DAY + timedelta(hours=7), 20, self.price, 3.0)
        brk = self.bar(DAY + timedelta(hours=12), self.price, hi_r + 3.0)
        self.assertIsNone(evaluate_asia(self.h1, self.m15 + extra + [brk]))


class Squeeze(unittest.TestCase):
    def test_squeeze_breakout(self):
        h1 = h1_trend(+1)
        p0 = h1[-1]["close"]
        start = DAY + timedelta(hours=9) - timedelta(minutes=15 * 130)
        m15 = m15_flat(start, 122, p0, 4.0) + m15_flat(start + timedelta(minutes=15 * 122), 8, p0, 0.6)
        t = m15[-1]["time"] + timedelta(minutes=15)
        box_h = max(x["high"] for x in m15[-8:])
        brk = {"time": t, "open": p0, "close": box_h + 6.0, "high": box_h + 6.2, "low": p0 - 0.2, "spread": 0.2}
        s = evaluate_squeeze(h1, m15 + [brk])
        self.assertIsNotNone(s)
        self.assertEqual((s.side, s.name), ("buy", "C"))
        self.assertLess(s.sl, min(x["low"] for x in m15[-8:]) + 1e-9 + s.atr * 1.0)

    def test_no_squeeze_no_signal(self):
        h1 = h1_trend(+1)
        p0 = h1[-1]["close"]
        start = DAY + timedelta(hours=9) - timedelta(minutes=15 * 130)
        import math
        m15 = m15_flat(start, 130, p0, 4.0)
        for i, x in enumerate(m15):  # narx katta to'lqinda yuradi — siqilish yo'q
            off = 12 * math.sin(i / 3)
            for k in ("open", "high", "low", "close"):
                x[k] += off
        brk = {"time": m15[-1]["time"] + timedelta(minutes=15), "open": p0, "close": p0 + 9, "high": p0 + 9.2,
               "low": p0 - 0.2, "spread": 0.2}
        self.assertIsNone(evaluate_squeeze(h1, m15 + [brk]))


class Scoring(unittest.TestCase):
    def test_score_bounds_and_conflict(self):
        h1 = h1_trend(+1)
        a = Signal("buy", 1, 0, 3, 1, "", "A")
        b = Signal("buy", 1, 0, 3, 1, "", "B")
        c = Signal("sell", 1, 2, -1, 1, "", "C")
        s_agree = score(a, h1, [a, b])
        s_alone = score(a, h1, [a])
        s_conflict = score(a, h1, [a, c])
        self.assertGreater(s_agree, s_alone)
        self.assertLess(s_conflict, s_alone)
        for v in (s_agree, s_alone, s_conflict):
            self.assertTrue(0.5 <= v <= 1.5)

    def test_dynamic_equity_capped(self):
        eq, _, _ = backtest.equity_curve([-1], 10, scores=[1.5])
        self.assertAlmostEqual(eq, 90.0)  # 15% emas, 10% bilan cheklangan
        eq, _, _ = backtest.equity_curve([2], 4, scores=[1.5])
        self.assertAlmostEqual(eq, 112.0)


class Compare(unittest.TestCase):
    def test_compare_runs_all_variants(self):
        h1, m15 = synth(16000, seed=21)
        rows = backtest.compare(h1, m15, risk=5)
        self.assertEqual([r["variant"] for r in rows], ["A", "B", "C", "ABC"])
        for r in rows:
            self.assertEqual(r["in"]["trades"] + r["oos"]["trades"], r["all"]["trades"])
        names = {t.name for t in backtest.run(h1, m15, enabled="ABC").trades}
        self.assertTrue(names <= {"A", "B", "C"})
        text = backtest.format_compare(rows, 5)
        self.assertIn("tekshiruv", text)
        self.assertIn("Siqilish", text)


if __name__ == "__main__":
    unittest.main()
