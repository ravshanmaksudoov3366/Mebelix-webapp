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
    name: str = "A"
    score: float = 1.0


@dataclass
class Limits:
    max_trades_per_day: int = 10
    max_consec_losses_per_day: int = 5  # bir kunda ketma-ket shuncha yutqazsa — o'sha kuni savdo yo'q


@dataclass
class Result:
    trades: list = field(default_factory=list)
    start: object = None
    end: object = None


def run(h1, m15, p: Params = Params(), lim: Limits = Limits(), enabled="ABC") -> Result:
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
        sig = evaluate(h1[max(0, hi - WIN_H1):hi], m15[i + 1 - WIN_M15:i + 1], p, enabled)
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
        pos = Trade(sig.side, nxt["time"], entry, sig.sl, tp, name=sig.name, score=sig.score)
        cur_sl = sig.sl
        day_trades += 1
    return res


MAX_RISK = 10.0


def equity_curve(rs, risk_pct, start=100.0, scores=None):
    """Hisob o'sishi. scores berilsa — har savdo riski risk_pct × ball (eng ko'pi 10%)."""
    eq, peak, max_dd, curve = start, start, 0.0, []
    for i, r in enumerate(rs):
        rp = min(MAX_RISK, risk_pct * (scores[i] if scores else 1.0))
        eq *= max(0.0, 1 + r * rp / 100.0)
        peak = max(peak, eq)
        max_dd = max(max_dd, (peak - eq) / peak if peak else 0)
        curve.append(eq)
    return eq, max_dd, curve


def summary(res: Result, risks=(2, 5, 10), trades=None) -> dict:
    trades = res.trades if trades is None else trades
    rs = [t.r for t in trades]
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
    scores = [t.score for t in trades]
    for rp in risks:
        eq, dd, _ = equity_curve(rs, rp)
        eqd, ddd, _ = equity_curve(rs, rp, scores=scores)
        out["by_risk"][rp] = {"return_pct": eq - 100.0, "max_dd_pct": dd * 100,
                              "dyn_return_pct": eqd - 100.0, "dyn_max_dd_pct": ddd * 100}
    return out


def split(res: Result, frac=2 / 3):
    """O'rganish davri (birinchi 2/3) va tekshiruv davri (oxirgi 1/3) savdolari."""
    if not res.start or not res.end:
        return [], []
    cut = res.start + (res.end - res.start) * frac
    return [t for t in res.trades if t.open_time < cut], [t for t in res.trades if t.open_time >= cut]


NAMES = {"A": "A «Qaytish»", "B": "B «Osiyo diapazoni»", "C": "C «Siqilish→portlash»",
         "ABC": "Hammasi birga (A+B+C)"}


def compare(h1, m15, p: Params = Params(), lim: Limits = Limits(), risk=5.0, variants=("A", "B", "C", "ABC")):
    """Har bir usulni alohida va birga sinaydi; o'rganish va tekshiruv davrlarini alohida baholaydi."""
    rows = []
    for v in variants:
        res = run(h1, m15, p, lim, v)
        ins, oos = split(res)
        rows.append({"variant": v, "all": summary(res, (risk,)), "in": summary(res, (risk,), ins),
                     "oos": summary(res, (risk,), oos), "start": res.start, "end": res.end})
    return rows


def _verdict(row):
    i, o = row["in"], row["oos"]
    if o["trades"] < 5:
        return "⚪ savdo kam — xulosa qilib bo'lmaydi"
    if o["total_r"] > 0 and i["total_r"] > 0 and o["profit_factor"] >= 1.15:
        return "🟢 ikkala davrda ham foydali"
    if o["total_r"] > 0:
        return "🟡 tekshiruvda foydali, lekin kuchsiz"
    return "🔴 tekshiruv davrida zarar"


def best_variant(rows):
    good = [r for r in rows if _verdict(r).startswith("🟢")]
    if not good:
        return None
    return max(good, key=lambda r: r["oos"]["total_r"] / max(1.0, r["oos"]["max_losing_streak"]))["variant"]


def format_compare(rows, risk) -> str:
    if not rows:
        return "🧪 Sinov uchun ma'lumot yetarli emas."
    r0 = rows[0]
    cut = r0["start"] + (r0["end"] - r0["start"]) * 2 / 3
    lines = [f"🧪 <b>Strategiyalar sinovi</b> ({r0['start']:%d.%m.%Y} – {r0['end']:%d.%m.%Y})",
             f"O'rganish: {cut:%d.%m.%Y} gacha, <b>tekshiruv (bot ko'rmagan davr)</b>: {cut:%d.%m.%Y} dan keyin",
             f"Hisob natijasi {risk:g}% risk bilan; qavsda — ishonch baliga qarab o'zgaruvchan risk.", ""]
    for row in rows:
        a, i, o = row["all"], row["in"], row["oos"]
        br = a["by_risk"].get(risk) or next(iter(a["by_risk"].values()), None)
        pf = "∞" if o["profit_factor"] == float("inf") else f"{o['profit_factor']:.2f}"
        lines.append(f"<b>{NAMES.get(row['variant'], row['variant'])}</b> — {_verdict(row)}")
        lines.append(f"  O'rganish: {i['trades']} savdo, {i['total_r']:+.1f}R | "
                     f"Tekshiruv: {o['trades']} savdo, {o['total_r']:+.1f}R, yutish {o['win_rate']:.0f}%, "
                     f"foyda omili {pf}")
        if br:
            lines.append(f"  Butun davr: {br['return_pct']:+.0f}% (o'zgaruvchan: {br['dyn_return_pct']:+.0f}%), "
                         f"eng katta pasayish −{br['max_dd_pct']:.0f}% (−{br['dyn_max_dd_pct']:.0f}%), "
                         f"ketma-ket yutqazish: {a['max_losing_streak']}")
        lines.append("")
    best = best_variant(rows)
    if best:
        lines.append(f"✅ Tavsiya: <b>{NAMES.get(best, best)}</b>. Yoqish uchun: <code>strategiya {best}</code>")
    else:
        lines.append("⛔ Hech bir usul ikkala davrda ham ishonchli foyda bermadi — real pulni xavfga qo'ymang.")
    lines.append("⚠️ O'tgan natija kelajakni kafolatlamaydi.")
    return "\n".join(lines)


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
