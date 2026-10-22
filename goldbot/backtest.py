"""Strategiyani o'tgan narxlarda sinash (backtest).

Bot bilan bir xil `strategy.evaluate` ishlatiladi. Kirish — signal shamidan keyingi sham ochilishida,
spred hisobga olinadi; bitta shamda ham stop, ham take-profit bo'lsa — yomon holat (stop) olinadi.
Natija R birliklarida (1R = bitta savdodagi risk), keyin turli risk foizlari uchun hisob o'sishi.
"""
from dataclasses import dataclass, field
from datetime import timedelta

from strategy import Params, evaluate, in_session, managed_stop, trend

M15 = timedelta(minutes=15)
H1 = timedelta(hours=1)
WIN_M15, WIN_H1 = 300, 500


@dataclass
class Trade:
    side: str
    open_time: object
    entry: float
    sl0: float
    tp: float
    exit_time: object = None
    exit: float = 0.0
    r: float = 0.0
    why: str = ""


@dataclass
class Limits:
    max_trades_per_day: int = 10
    max_consec_losses_per_day: int = 5  # bir kunda ketma-ket shuncha yutqazsa — o'sha kuni savdo yo'q


@dataclass
class Result:
    trades: list = field(default_factory=list)
    start: object = None
    end: object = None


def run(h1, m15, p: Params = Params(), lim: Limits = Limits()) -> Result:
    res = Result(start=m15[0]["time"] if m15 else None, end=m15[-1]["time"] if m15 else None)
    if len(m15) < WIN_M15 or len(h1) < 210:
        return res
    hi = 0             # h1[:hi] — m15 shami yopilgan paytgacha yopilgan H1 shamlar
    trend_cache = {}
    pos = None         # ochiq Trade + joriy stop
    cur_sl = None
    day, day_trades, day_losses = None, 0, 0

    def close_pos(t, price, why):
        nonlocal pos, day_losses
        sign = 1 if pos.side == "buy" else -1
        pos.exit_time, pos.exit, pos.why = t, price, why
        pos.r = (price - pos.entry) * sign / abs(pos.entry - pos.sl0)
        day_losses = day_losses + 1 if pos.r < 0 else 0  # ketma-ket yutqazishlar (yutuq nolga qaytaradi)
        res.trades.append(pos)
        pos = None

    for i in range(WIN_M15 - 1, len(m15)):
        bar = m15[i]
        t_open = bar["time"]
        spread = bar.get("spread", 0.0)
        if t_open.date() != day:
            day, day_trades, day_losses = t_open.date(), 0, 0

        # 1) ochiq pozitsiya: shu sham ichida stop / take-profit
        if pos is not None:
            if t_open.weekday() == 4 and (t_open.hour, t_open.minute) >= (20, 30):
                bid = bar["open"]
                close_pos(t_open, bid if pos.side == "buy" else bid + spread, "juma yopish")
            elif pos.side == "buy":
                if bar["open"] <= cur_sl:
                    close_pos(t_open, bar["open"], "stop (gap)")
                elif bar["low"] <= cur_sl:
                    close_pos(t_open, cur_sl, "stop")
                elif bar["high"] >= pos.tp:
                    close_pos(t_open, pos.tp, "take-profit")
            else:
                if bar["open"] + spread >= cur_sl:
                    close_pos(t_open, bar["open"] + spread, "stop (gap)")
                elif bar["high"] + spread >= cur_sl:
                    close_pos(t_open, cur_sl, "stop")
                elif bar["low"] + spread <= pos.tp:
                    close_pos(t_open, pos.tp, "take-profit")
            if pos is not None:  # sham oxirida stopni boshqarish (keyingi shamdan amal qiladi)
                best = bar["high"] if pos.side == "buy" else bar["low"] + spread
                ns = managed_stop(pos.side, pos.entry, cur_sl, pos.tp, best, p)
                if ns is not None:
                    cur_sl = ns

        # 2) yangi signal — sham yopilganda
        t_close = t_open + M15
        while hi < len(h1) and h1[hi]["time"] + H1 <= t_close:
            hi += 1
        if pos is not None or i + 1 >= len(m15):
            continue
        if not in_session(t_close, p) or day_trades >= lim.max_trades_per_day \
                or day_losses >= lim.max_consec_losses_per_day:
            continue
        if hi not in trend_cache:
            trend_cache[hi] = trend(h1[max(0, hi - WIN_H1):hi], p)
        if trend_cache[hi] is None:
            continue
        sig = evaluate(h1[max(0, hi - WIN_H1):hi], m15[i + 1 - WIN_M15:i + 1], p)
        if sig is None:
            continue
        if spread > p.max_spread_frac * sig.sl_dist:
            continue
        nxt = m15[i + 1]
        entry = nxt["open"] + (nxt.get("spread", spread) if sig.side == "buy" else 0.0)
        if (entry - sig.sl) * (1 if sig.side == "buy" else -1) <= 0:
            continue
        dist = abs(entry - sig.sl)
        tp = entry + p.rr * dist if sig.side == "buy" else entry - p.rr * dist  # bot kabi: haqiqiy narxdan
        pos = Trade(sig.side, nxt["time"], entry, sig.sl, tp)
        cur_sl = sig.sl
        day_trades += 1
    return res


def equity_curve(rs, risk_pct, start=100.0):
    eq, peak, max_dd, curve = start, start, 0.0, []
    for r in rs:
        eq *= max(0.0, 1 + r * risk_pct / 100.0)
        peak = max(peak, eq)
        max_dd = max(max_dd, (peak - eq) / peak if peak else 0)
        curve.append(eq)
    return eq, max_dd, curve


def summary(res: Result, risks=(2, 5, 10)) -> dict:
    rs = [t.r for t in res.trades]
    wins = [r for r in rs if r > 0]
    losses = [r for r in rs if r <= 0]
    streak = best = 0
    for r in rs:
        streak = streak + 1 if r <= 0 else 0
        best = max(best, streak)
    out = {
        "start": res.start, "end": res.end, "trades": len(rs),
        "win_rate": len(wins) / len(rs) * 100 if rs else 0.0,
        "profit_factor": (sum(wins) / -sum(losses)) if losses and sum(losses) < 0 else (float("inf") if wins else 0.0),
        "avg_r": sum(rs) / len(rs) if rs else 0.0,
        "total_r": sum(rs),
        "max_losing_streak": best,
        "by_risk": {},
    }
    for rp in risks:
        eq, dd, _ = equity_curve(rs, rp)
        out["by_risk"][rp] = {"return_pct": eq - 100.0, "max_dd_pct": dd * 100}
    return out


def format_summary(s: dict) -> str:
    if not s["trades"]:
        return "🧪 Sinov: bu davrda strategiya birorta ham savdo ochmadi."
    pf = "∞" if s["profit_factor"] == float("inf") else f"{s['profit_factor']:.2f}"
    lines = [
        f"🧪 <b>Sinov natijasi</b> ({s['start']:%d.%m.%Y} – {s['end']:%d.%m.%Y})",
        f"Savdolar: {s['trades']}, yutganlari: {s['win_rate']:.0f}%",
        f"Foyda omili: {pf} (1 dan katta — foydali)",
        f"O'rtacha natija: {s['avg_r']:+.2f}R, jami {s['total_r']:+.1f}R",
        f"Eng uzun yutqazishlar ketma-ketligi: {s['max_losing_streak']}",
        "",
        "<b>Har savdoda risk → hisob natijasi / eng katta pasayish:</b>",
    ]
    for rp, v in s["by_risk"].items():
        lines.append(f"• {rp}% → {v['return_pct']:+.0f}% / −{v['max_dd_pct']:.0f}%")
    lines.append("")
    lines.append("⚠️ O'tgan natija kelajakni kafolatlamaydi.")
    return "\n".join(lines)
